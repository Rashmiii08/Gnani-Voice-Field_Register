"""Gnani WebSocket transport for the Section 6 PCM contract.

https://docs.gnani.ai/api/STT/stt-websocket
https://docs.gnani.ai/api/TTS/tts-websocket
"""

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK, InvalidStatus, WebSocketException

logger = logging.getLogger("uvicorn.error").getChild("gnani")
wire_logger = logging.getLogger(__name__ + ".wire")
wire_logger.setLevel(logging.WARNING)

PRISMA_URL = "wss://api.vachana.ai/stt/v3/stream"
TIMBRE_URL = "wss://api.vachana.ai/api/v1/tts"
PCM_FRAME_BYTES = 1024
PCM_SAMPLE_RATE = 16000
PRISMA_TAIL_FRAMES = 16  # 512 ms, matching the successful synthetic-audio check.
LANGUAGE_CODES = {"hi": "hi-IN", "en": "en-IN"}


class SpeechProvider(Protocol):
    async def transcribe(self, audio: AsyncIterator[bytes], language: str) -> str: ...

    def synthesize(self, text: str, language: str) -> AsyncIterator[bytes]: ...


class SpeechError(Exception):
    """An upstream failure safe to map to a generic client error."""


class ProviderErrorFrame(SpeechError):
    """The upstream sent its documented error event."""


class UnexpectedEvent(SpeechError):
    """An upstream message did not match the expected schema."""


class TranscriptTimeout(SpeechError):
    """Speech was detected but its final transcript did not arrive."""


# Only known codes and locally assigned categories are safe to print.
SAFE_ERROR_CODES = {
    "MISSING_API_KEY", "INVALID_API_KEY", "SCOPE_NOT_ALLOWED", "RATE_LIMITED",
    "INVALID_LANGUAGE_CODE", "INVALID_FORMAT", "INVALID_MODEL", "MODEL_NOT_AVAILABLE",
    "MODEL_NOT_ALLOWED", "TRANSCRIPTION_FAILED",
}
ERROR_MESSAGES = {
    "stt engine failed to initialize": "ENGINE_INIT_FAILED",
    "service 'stt' not in allowed scopes": "SCOPE_NOT_ALLOWED",
}


def _prisma_error_code(event: dict) -> str:
    for payload in (event, event.get("detail"), event.get("error")):
        if not isinstance(payload, dict):
            continue
        for field in ("error_code", "code", "type"):
            value = payload.get(field)
            if isinstance(value, str) and value in SAFE_ERROR_CODES:
                return value
        message = payload.get("message")
        if isinstance(message, str):
            code = ERROR_MESSAGES.get(message.strip().casefold().rstrip("."))
            if code:
                return code
    return "UNCLASSIFIED"


def _log_failure(service: str, phase: str, exc: Exception) -> None:
    # Do not interpolate exception messages or vendor payloads. The library's
    # exception string can include headers, close reasons, and response bodies.
    response = getattr(exc, "response", None)
    http_status = getattr(response, "status_code", None)
    closed = exc.rcvd.code if isinstance(exc, ConnectionClosed) and exc.rcvd else None
    if service == "Prisma":
        code = getattr(exc, "provider_code", "UNCLASSIFIED")
        if isinstance(exc, InvalidStatus) and response.body and len(response.body) <= 8192:
            try:
                body = json.loads(response.body)
            except (ValueError, UnicodeError):
                body = None
            if isinstance(body, dict):
                code = _prisma_error_code(body)
        if phase != "upgrade":
            http_status = 101
        logger.warning("Gnani Prisma phase=%s error_type=%s http_status=%s ws_close=%s provider_code=%s",
                       phase, type(exc).__name__, http_status, closed, code)
        return
    logger.warning("Gnani %s phase=%s error_type=%s http_status=%s ws_close=%s",
                   service, phase, type(exc).__name__, http_status, closed)


async def _event(socket) -> dict:
    message = json.loads(await socket.recv())
    if not isinstance(message, dict):
        raise UnexpectedEvent()
    if message.get("type") == "error":
        raise ProviderErrorFrame()
    return message


async def _send_audio(socket, audio: AsyncIterator[bytes]) -> None:
    pending = bytearray()
    loop = asyncio.get_running_loop()
    next_frame = loop.time()
    frames = 0

    async def send_frame(frame: bytes) -> None:
        nonlocal next_frame, frames
        await asyncio.sleep(max(0, next_frame - loop.time()))
        next_frame = loop.time() + 0.032
        await socket.send(frame)
        frames += 1

    async for chunk in audio:
        pending.extend(chunk)
        while len(pending) >= PCM_FRAME_BYTES:
            await send_frame(bytes(pending[:PCM_FRAME_BYTES]))
            del pending[:PCM_FRAME_BYTES]
    if pending:
        await send_frame(bytes(pending).ljust(PCM_FRAME_BYTES, b"\0"))
    if frames:
        # Give VAD the same end-of-speech boundary as the synthetic probe.
        # Pace the padding just like microphone frames and keep receiving.
        for _ in range(PRISMA_TAIL_FRAMES):
            await send_frame(bytes(PCM_FRAME_BYTES))
    await socket.send(json.dumps({"type": "commit"}))
    logger.info("Gnani Prisma audio sample_rate=%d channels=1 frames=%d bytes=%d tail_frames=%d",
                PCM_SAMPLE_RATE, frames, frames * PCM_FRAME_BYTES,
                PRISMA_TAIL_FRAMES if frames else 0)


async def _receive_transcripts(socket, committed: asyncio.Event) -> str:
    segments = []
    seen = set()
    pending = False
    read = asyncio.create_task(_event(socket))
    commit = asyncio.create_task(committed.wait())
    loop = asyncio.get_running_loop()
    try:
        while not commit.done():
            await asyncio.wait((read, commit), return_when=asyncio.FIRST_COMPLETED)
            if read.done():
                pending = _collect_segment(read.result(), segments, seen, pending)
                read = asyncio.create_task(_event(socket))

        # Prisma documents commit but provides no end-of-stream acknowledgment.
        # Allow outstanding transcription to finish, then drain a short quiet window.
        deadline = loop.time() + 8
        while (remaining := deadline - loop.time()) > 0:
            wait = remaining if pending or not segments else min(0.7, remaining)
            done, _ = await asyncio.wait((read,), timeout=wait)
            if not done:
                break
            try:
                event = read.result()
            except ConnectionClosedOK:
                if segments and not pending:
                    break
                raise
            pending = _collect_segment(event, segments, seen, pending)
            read = asyncio.create_task(_event(socket))
        if pending:
            raise TranscriptTimeout()
        return " ".join(text for text in segments if text)
    finally:
        read.cancel()
        commit.cancel()
        await asyncio.gather(read, commit, return_exceptions=True)


def _collect_segment(event, segments, seen, pending):
    kind = event.get("type")
    if kind == "processing":
        # Anonymous status messages don't provide a segment ID and cannot
        # be counted as independent promises of a final transcript.
        return True
    if kind != "transcript" or event.get("is_final") is False:
        return pending
    segment_id = event.get("segment_id")
    if segment_id and segment_id in seen:
        return pending
    if segment_id:
        seen.add(segment_id)
    text = event.get("text")
    if not isinstance(text, str):
        raise UnexpectedEvent()
    segments.append(text.strip())
    return False


class GnaniSpeech:
    def __init__(self, api_key: str, voice: str = "Shivani", *, connector=connect):
        self._api_key = api_key.strip()
        self._voice = voice
        self._connect = connector

    @asynccontextmanager
    async def _prisma_socket(self, language: str, *, minimal: bool = False):
        headers = {
            "x-api-key-id": self._api_key,
            "model": "prisma-v3.0",
            "language_code": LANGUAGE_CODES[language],
            "x-sample-rate": str(PCM_SAMPLE_RATE),
        }
        if not minimal:
            headers["format"] = "transcribe"
        async with self._connect(PRISMA_URL, additional_headers=headers,
                                 open_timeout=10, close_timeout=1, logger=wire_logger) as socket:
            yield socket

    async def _initialize_prisma(self, socket) -> None:
        event = json.loads(await asyncio.wait_for(socket.recv(), 10))
        if isinstance(event, dict) and event.get("type") == "error":
            error = ProviderErrorFrame()
            error.provider_code = _prisma_error_code(event)
            raise error
        if not isinstance(event, dict) or event.get("type") != "connected":
            raise UnexpectedEvent()
        logger.info("Gnani Prisma phase=initialization http_status=101")

    async def check_prisma_initialization(self, language: str, *, minimal: bool = False) -> None:
        phase = "upgrade"
        try:
            async with self._prisma_socket(language, minimal=minimal) as socket:
                phase = "initialization"
                await self._initialize_prisma(socket)
        except (SpeechError, OSError, WebSocketException, ValueError, TypeError) as exc:
            _log_failure("Prisma", phase, exc)
            raise SpeechError() from None

    async def transcribe(self, audio: AsyncIterator[bytes], language: str) -> str:
        phase = "upgrade"
        try:
            async with self._prisma_socket(language) as socket:
                phase = "initialization"
                await self._initialize_prisma(socket)
                phase = "stream"
                committed = asyncio.Event()

                async def send():
                    nonlocal phase
                    await _send_audio(socket, audio)
                    phase = "final_transcript"
                    committed.set()

                sender = asyncio.create_task(send())
                receiver = asyncio.create_task(_receive_transcripts(socket, committed))
                try:
                    await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
                    if sender.done():
                        sender.result()
                        return await receiver
                    return receiver.result()
                finally:
                    sender.cancel()
                    receiver.cancel()
                    await asyncio.gather(sender, receiver, return_exceptions=True)
        except (SpeechError, OSError, TimeoutError, WebSocketException, ValueError, TypeError) as exc:
            _log_failure("Prisma", phase, exc)
            raise SpeechError() from None

    async def synthesize(self, text: str, language: str) -> AsyncIterator[bytes]:
        request = {
            "text": text,
            "model": "timbre-v3.0",
            "voice": self._voice,
            "language": LANGUAGE_CODES[language],
            "audio_config": {
                "sample_rate": 16000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "pcm_s16le",
                "container": "raw",
            },
        }
        headers = {"X-API-Key-ID": self._api_key}
        phase = "upgrade"
        try:
            async with self._connect(TIMBRE_URL, additional_headers=headers,
                                     open_timeout=10, close_timeout=1, logger=wire_logger) as socket:
                logger.info("Gnani Timbre phase=upgrade http_status=101")
                phase = "synthesis"
                await socket.send(json.dumps(request))
                while True:
                    event = await asyncio.wait_for(_event(socket), 8)
                    if event.get("type") == "complete":
                        return
                    if event.get("type") == "audio":
                        pcm = base64.b64decode(event["data"]["audio"], validate=True)
                        if len(pcm) % 2:
                            raise UnexpectedEvent()
                        if pcm:
                            yield pcm
        except (SpeechError, OSError, TimeoutError, WebSocketException, ValueError, KeyError, TypeError) as exc:
            _log_failure("Timbre", phase, exc)
            raise SpeechError() from None
