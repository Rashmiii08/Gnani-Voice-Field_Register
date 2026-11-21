import asyncio
import base64
import json
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.staticfiles import StaticFiles

from backend.gnani_adapter import GnaniSpeech, SpeechError, SpeechProvider

logger = logging.getLogger(__name__)
RETRY = "Please reconnect or retry"
SESSION_TTL = 300
MAX_SESSIONS = 128
MAX_AUDIO_BYTES = 6400
MAX_AUDIO_BASE64 = 4 * ((MAX_AUDIO_BYTES + 2) // 3)
IDLE_TIMEOUT = 120


@dataclass
class TurnResult:
    """Projection of Role B's session and ordered Say items for transport."""

    state: str
    form: dict
    danger_flag: bool
    follow_ups: list
    utterances: list[str]


@dataclass
class Session:
    session_id: str
    language: str
    dialogue: Any
    turn_id: int = 0
    disclosed: bool = False
    update: dict = field(default_factory=lambda: {
        "type": "update", "state": "LISTENING", "form": {},
        "danger_flag": False, "latency_ms": None, "follow_ups": [],
    })
    expiry: asyncio.TimerHandle | None = None


@dataclass
class Utterance:
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=24))
    ended_at: float | None = None
    last_audio_at: float = field(default_factory=monotonic)

    async def chunks(self):
        while (chunk := await self.queue.get()) is not None:
            yield chunk


TurnHandler = Callable[[Any, str], Awaitable[TurnResult]]


def disclosure(language: str) -> str:
    try:
        from backend.phrases import get_phrase
    except ModuleNotFoundError as exc:
        if exc.name != "backend.phrases":
            raise
        return {
            "hi": "मैं एक AI सहायक हूँ।",
            "en": "I am an AI assistant.",
        }[language]
    return get_phrase(language, "disclosure")


async def cancel_task(task: asyncio.Task | None) -> None:
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class Connection:
    def __init__(self, websocket, session, provider, handle_turn):
        self.websocket = websocket
        self.session = session
        self.provider = provider
        self.handle_turn = handle_turn
        self.send_lock = asyncio.Lock()
        self.input_task = None
        self.output_task = None
        self.utterance = None
        self.last_seq = -1
        self.output_generation = 0

    async def send(self, message, generation=None):
        async with self.send_lock:
            if generation is None or generation == self.output_generation:
                await self.websocket.send_json(message)

    async def error(self, code, generation=None):
        await self.send({"type": "error", "code": code, "message": RETRY}, generation)

    def start_disclosure(self):
        if self.provider is not None and not self.session.disclosed:
            self.output_task = asyncio.create_task(self.speak(
                [disclosure(self.session.language)], self.output_generation, 0,
                is_disclosure=True,
            ))

    async def speak(self, texts, generation, turn_id, *, timing=None, is_disclosure=False):
        first = True
        try:
            async with asyncio.timeout(45):
                for text in texts:
                    async with aclosing(self.provider.synthesize(text, self.session.language)) as chunks:
                        async for pcm in chunks:
                            if generation != self.output_generation:
                                return
                            if first and timing is not None:
                                now = monotonic()
                                speech_ms = round((now - timing[0]) * 1000)
                                self.session.update["latency_ms"] = speech_ms
                                logger.info(
                                    "First audio latency in ms estimated_speech_end=%d final_stt=%d",
                                    speech_ms, round((now - timing[1]) * 1000),
                                )
                                await self.send(self.session.update, generation)
                            await self.send({
                                "type": "audio", "data": base64.b64encode(pcm).decode("ascii"),
                                "is_first_chunk": first, "turn_id": turn_id,
                            }, generation)
                            first = False
                if first:
                    raise SpeechError()
                if is_disclosure:
                    self.session.disclosed = True
        except (SpeechError, TimeoutError):
            await self.error("TTS_UNAVAILABLE", generation)

    async def interrupt(self):
        self.output_generation += 1
        await cancel_task(self.output_task)
        self.output_task = None

    async def process_utterance(self, utterance, generation):
        try:
            async with asyncio.timeout(45), aclosing(utterance.chunks()) as chunks:
                text = await self.provider.transcribe(chunks, self.session.language)
            final_at = monotonic()
        except (SpeechError, TimeoutError):
            await self.error("STT_UNAVAILABLE")
            return

        if not text:
            await self.error("NO_SPEECH")
            return
        await self.send({"type": "transcript", "text": text, "final": True})
        if self.handle_turn is None:
            return
        try:
            result = await asyncio.wait_for(self.handle_turn(self.session.dialogue, text), 10)
        except Exception:
            logger.warning("Dialogue handler failed")
            await self.error("DIALOGUE_UNAVAILABLE")
            return

        self.session.turn_id += 1
        self.session.update = {
            "type": "update", "state": result.state, "form": result.form,
            "danger_flag": result.danger_flag, "latency_ms": None,
            "follow_ups": result.follow_ups,
        }
        await self.send(self.session.update)
        if not result.utterances or generation != self.output_generation:
            return
        if self.session.disclosed:
            await cancel_task(self.output_task)
        else:
            if self.output_task is None or self.output_task.done():
                self.start_disclosure()
            await asyncio.shield(asyncio.gather(self.output_task, return_exceptions=True))
        if self.session.disclosed and generation == self.output_generation:
            self.output_task = asyncio.create_task(self.speak(
                result.utterances, generation, self.session.turn_id,
                timing=(utterance.ended_at or utterance.last_audio_at, final_at),
            ))

    async def accept_audio(self, message):
        seq = message.get("seq")
        data = message.get("data")
        if type(seq) is not int or seq < 0 or not isinstance(data, str) or len(data) > MAX_AUDIO_BASE64:
            await self.error("INVALID_AUDIO")
            return
        try:
            pcm = base64.b64decode(data, validate=True)
            if not pcm or len(pcm) % 2 or len(pcm) > MAX_AUDIO_BYTES:
                raise ValueError()
        except ValueError:
            await self.error("INVALID_AUDIO")
            return
        if seq <= self.last_seq:
            return
        if self.provider is None:
            await self.error("STT_UNAVAILABLE")
            return

        if self.input_task is None or self.input_task.done():
            await self.finish_input()
            self.utterance = Utterance()
            self.input_task = asyncio.create_task(
                self.process_utterance(self.utterance, self.output_generation)
            )
        if self.utterance.ended_at is not None:
            await self.error("TURN_IN_PROGRESS")
            return
        try:
            self.utterance.queue.put_nowait(pcm)
        except asyncio.QueueFull:
            await self.finish_input()
            await self.error("AUDIO_BACKPRESSURE")
            return
        self.last_seq = seq
        self.utterance.last_audio_at = monotonic()

    async def end_utterance(self):
        if self.utterance is None or self.utterance.ended_at is not None or self.input_task.done():
            return
        self.utterance.ended_at = monotonic()
        try:
            self.utterance.queue.put_nowait(None)
        except asyncio.QueueFull:
            await self.finish_input()
            await self.error("AUDIO_BACKPRESSURE")

    async def finish_input(self):
        await cancel_task(self.input_task)
        self.input_task = self.utterance = None


def create_app(
    provider: SpeechProvider | None = None,
    *,
    session_factory: Callable[[str, str], Any] | None = None,
    handle_turn: TurnHandler | None = None,
    demo_mode: bool = False,
) -> FastAPI:
    """Inject Role B's session factory and an async turn handler wired to Role D."""
    app = FastAPI()
    sessions: dict[str, Session] = {}

    @app.get("/runtime-mode")
    async def runtime_mode() -> dict[str, bool]:
        return {"demo": demo_mode}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        if origin:
            scheme = "https" if websocket.url.scheme == "wss" else "http"
            if origin != f"{scheme}://{websocket.headers.get('host')}":
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
        await websocket.accept()
        connection = None
        try:
            while True:
                frame = await asyncio.wait_for(websocket.receive(), IDLE_TIMEOUT)
                if frame["type"] == "websocket.disconnect":
                    return
                message = json.loads(frame.get("text") or "")
                if not isinstance(message, dict):
                    raise ValueError()
                kind = message.get("type")
                if connection is None:
                    session_id = message.get("session_id")
                    if not isinstance(session_id, str) or not 0 < len(session_id) <= 128:
                        raise ValueError()
                    session = sessions.get(session_id)
                    if kind == "start" and message.get("language") in ("hi", "en"):
                        if session is not None or len(sessions) >= MAX_SESSIONS:
                            await reject_session(websocket, "SESSION_EXISTS" if session else "SESSION_LIMIT")
                            return
                        language = message["language"]
                        dialogue = session_factory(session_id, language) if session_factory else None
                        session = sessions[session_id] = Session(session_id, language, dialogue)
                    elif kind == "resume":
                        version = message.get("draft_version")
                        if type(version) is not int or version < 0:
                            raise ValueError()
                        if session is None or session.expiry is None:
                            await reject_session(websocket, "SESSION_NOT_RESUMABLE")
                            return
                        session.expiry.cancel()
                        session.expiry = None
                    else:
                        raise ValueError()

                    connection = Connection(websocket, session, provider, handle_turn)
                    await connection.send({"type": "ready", "session_id": session_id})
                    if kind == "resume":
                        await connection.send(session.update)
                    connection.start_disclosure()
                elif kind == "audio":
                    await connection.accept_audio(message)
                elif kind == "end_utterance":
                    await connection.end_utterance()
                elif kind == "interrupt":
                    await connection.interrupt()
                else:
                    await connection.error("INVALID_MESSAGE")
        except TimeoutError:
            await websocket.close(code=status.WS_1001_GOING_AWAY)
        except (WebSocketDisconnect, OSError):
            return
        except ValueError:
            if connection is not None:
                await connection.error("INVALID_MESSAGE")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        finally:
            if connection is not None:
                await connection.finish_input()
                await connection.interrupt()
                connection.session.expiry = asyncio.get_running_loop().call_later(
                    SESSION_TTL, sessions.pop, connection.session.session_id, None
                )

    frontend = Path(__file__).resolve().parents[1] / "frontend"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


async def reject_session(websocket, code):
    await websocket.send_json({"type": "error", "code": code, "message": RETRY})
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


api_key = os.getenv("GNANI_API_KEY")
app = create_app(GnaniSpeech(api_key, os.getenv("GNANI_TTS_VOICE", "Shivani")) if api_key else None)
