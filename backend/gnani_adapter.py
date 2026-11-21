"""Gnani WebSocket transport for the Section 6 PCM contract.

https://docs.gnani.ai/api/STT/stt-websocket
https://docs.gnani.ai/api/TTS/tts-websocket
"""

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from typing import Protocol

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

PRISMA_URL = "wss://api.vachana.ai/stt/v3/stream"
TIMBRE_URL = "wss://api.vachana.ai/api/v1/tts"
PCM_FRAME_BYTES = 1024
LANGUAGE_CODES = {"hi": "hi-IN", "en": "en-IN"}


class SpeechProvider(Protocol):
    async def transcribe(self, audio: AsyncIterator[bytes], language: str) -> str: ...

    def synthesize(self, text: str, language: str) -> AsyncIterator[bytes]: ...


class SpeechError(Exception):
    """An upstream failure safe to map to a generic client error."""


async def _event(socket) -> dict:
    message = json.loads(await socket.recv())
    if not isinstance(message, dict) or message.get("type") == "error":
        raise SpeechError()
    return message


async def _send_audio(socket, audio: AsyncIterator[bytes]) -> None:
    pending = bytearray()
    loop = asyncio.get_running_loop()
    next_frame = loop.time()

    async def send_frame(frame: bytes) -> None:
        nonlocal next_frame
        await asyncio.sleep(max(0, next_frame - loop.time()))
        next_frame = loop.time() + 0.032
        await socket.send(frame)

    async for chunk in audio:
        pending.extend(chunk)
        while len(pending) >= PCM_FRAME_BYTES:
            await send_frame(bytes(pending[:PCM_FRAME_BYTES]))
            del pending[:PCM_FRAME_BYTES]
    if pending:
        await send_frame(bytes(pending).ljust(PCM_FRAME_BYTES, b"\0"))
    await socket.send(json.dumps({"type": "commit"}))


async def _receive_transcript(socket) -> str:
    while True:
        event = await _event(socket)
        if event.get("type") == "transcript":
            return event["text"].strip()


class GnaniSpeech:
    def __init__(self, api_key: str, voice: str = "Shivani", *, connector=connect):
        self._api_key = api_key
        self._voice = voice
        self._connect = connector

    async def transcribe(self, audio: AsyncIterator[bytes], language: str) -> str:
        other_language = "en" if language == "hi" else "hi"
        headers = {
            "x-api-key-id": self._api_key,
            "model": "prisma-v3.0",
            "language_code": f"{LANGUAGE_CODES[language]},{LANGUAGE_CODES[other_language]}",
            "x-sample-rate": "16000",
            "format": "codemix",
        }
        try:
            async with self._connect(PRISMA_URL, additional_headers=headers,
                                     open_timeout=5, close_timeout=1) as socket:
                if (await asyncio.wait_for(_event(socket), 5)).get("type") != "connected":
                    raise SpeechError()
                sender = asyncio.create_task(_send_audio(socket, audio))
                receiver = asyncio.create_task(_receive_transcript(socket))
                try:
                    await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
                    if sender.done():
                        sender.result()
                        return await asyncio.wait_for(receiver, 8)
                    return receiver.result()
                finally:
                    sender.cancel()
                    receiver.cancel()
                    await asyncio.gather(sender, receiver, return_exceptions=True)
        except (OSError, TimeoutError, WebSocketException, ValueError, KeyError, AttributeError) as exc:
            raise SpeechError() from exc

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
        try:
            async with self._connect(TIMBRE_URL, additional_headers=headers,
                                     open_timeout=5, close_timeout=1) as socket:
                await socket.send(json.dumps(request))
                while True:
                    event = await asyncio.wait_for(_event(socket), 8)
                    if event.get("type") == "complete":
                        return
                    if event.get("type") == "audio":
                        pcm = base64.b64decode(event["data"]["audio"], validate=True)
                        if len(pcm) % 2:
                            raise SpeechError()
                        if pcm:
                            yield pcm
        except (OSError, TimeoutError, WebSocketException, ValueError, KeyError, TypeError) as exc:
            raise SpeechError() from exc
