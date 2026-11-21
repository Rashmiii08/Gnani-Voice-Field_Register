import asyncio
import base64
import json
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from backend.gnani_adapter import GnaniSpeech, SpeechError
from backend.main import TurnResult, app, create_app


def test_start_receives_exact_ready_handshake() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_json(
                {"type": "start", "language": "hi", "session_id": "demo-session"}
            )

            assert websocket.receive_json() == {
                "type": "ready",
                "session_id": "demo-session",
            }


class MockSpeech:
    async def transcribe(self, audio, language):
        pcm = b"".join([chunk async for chunk in audio])
        assert pcm == b"\x01\x00"
        return "Synthetic visit"

    async def synthesize(self, text, language):
        yield b"\x01\x00"


def start(socket):
    socket.send_json({"type": "start", "language": "hi", "session_id": "demo-session"})
    assert socket.receive_json() == {"type": "ready", "session_id": "demo-session"}


def send_utterance(socket):
    socket.send_json({"type": "audio", "data": "AQA=", "seq": 1})
    socket.send_json({"type": "audio", "data": "AQA=", "seq": 1})  # duplicate
    socket.send_json({"type": "end_utterance"})


def test_streaming_turn_and_resume_restore_dialogue_update():
    calls = []

    async def handle_turn(session, text):
        calls.append((session, text))
        return TurnResult("CONFIRMING", {"visit_type": "other"}, False, [], ["Readback"])

    app = create_app(MockSpeech(), session_factory=lambda sid, lang: (sid, lang),
                     handle_turn=handle_turn)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            start(socket)
            assert socket.receive_json() == {
                "type": "audio", "data": "AQA=", "is_first_chunk": True, "turn_id": 0,
            }
            send_utterance(socket)
            assert socket.receive_json() == {
                "type": "transcript", "text": "Synthetic visit", "final": True,
            }
            assert socket.receive_json()["latency_ms"] is None
            update = socket.receive_json()
            assert update["state"] == "CONFIRMING"
            assert isinstance(update["latency_ms"], int)
            assert socket.receive_json() == {
                "type": "audio", "data": "AQA=", "is_first_chunk": True, "turn_id": 1,
            }
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"type": "resume", "session_id": "demo-session", "draft_version": 1})
            assert socket.receive_json() == {"type": "ready", "session_id": "demo-session"}
            assert socket.receive_json() == update
        assert calls == [(("demo-session", "hi"), "Synthetic visit")]


def test_interrupt_cancels_audio_and_next_turn_has_new_id():
    cancelled = []

    class InterruptibleSpeech(MockSpeech):
        async def synthesize(self, text, language):
            if text == "Readback":
                try:
                    yield b"\x01\x00"
                    await asyncio.Future()
                finally:
                    cancelled.append(text)
            else:
                yield b"\x01\x00"

    async def handle_turn(session, text):
        return TurnResult("LISTENING", {}, False, [], ["Readback"])

    with TestClient(create_app(InterruptibleSpeech(), handle_turn=handle_turn)) as client:
        with client.websocket_connect("/ws") as socket:
            start(socket)
            assert socket.receive_json()["turn_id"] == 0
            send_utterance(socket)
            for kind in ("transcript", "update", "update", "audio"):
                assert socket.receive_json()["type"] == kind
            socket.send_json({"type": "interrupt"})
            socket.send_json({"type": "audio", "data": "AQA=", "seq": 2})
            socket.send_json({"type": "end_utterance"})
            assert socket.receive_json()["type"] == "transcript"
            assert cancelled == ["Readback"]
            assert socket.receive_json()["type"] == "update"
            assert socket.receive_json()["type"] == "update"
            assert socket.receive_json()["turn_id"] == 2


def test_stt_error_allows_retry():
    class UnavailableOnce(MockSpeech):
        attempts = 0

        async def transcribe(self, audio, language):
            self.attempts += 1
            result = await super().transcribe(audio, language)
            if self.attempts == 1:
                raise SpeechError("private upstream detail")
            return result

    with TestClient(create_app(UnavailableOnce())) as client:
        with client.websocket_connect("/ws") as socket:
            start(socket)
            assert socket.receive_json()["turn_id"] == 0
            send_utterance(socket)
            assert socket.receive_json() == {
                "type": "error", "code": "STT_UNAVAILABLE", "message": "Please reconnect or retry",
            }
            socket.send_json({"type": "audio", "data": "AQA=", "seq": 2})
            socket.send_json({"type": "end_utterance"})
            assert socket.receive_json()["type"] == "transcript"


def test_unknown_session_cannot_resume():
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"type": "resume", "session_id": "missing", "draft_version": 1})
            assert socket.receive_json()["code"] == "SESSION_NOT_RESUMABLE"


def test_prisma_v3_wire_frames_and_commit():
    sent = []

    class VendorSocket:
        async def send(self, frame):
            sent.append(frame)
            if isinstance(frame, str):
                self.committed.set()

        async def recv(self):
            if not self.connected:
                self.connected = True
                return json.dumps({"type": "connected"})
            await self.committed.wait()
            if not self.transcripts:
                await asyncio.Future()
            return json.dumps(self.transcripts.pop(0))

    @asynccontextmanager
    async def connect(url, *, additional_headers, **kwargs):
        assert url == "wss://api.vachana.ai/stt/v3/stream"
        assert additional_headers == {
            "x-api-key-id": "test-key", "model": "prisma-v3.0",
            "language_code": "hi-IN", "x-sample-rate": "16000", "format": "transcribe",
        }
        socket = VendorSocket()
        socket.connected = False
        socket.committed = asyncio.Event()
        socket.transcripts = [
            {"type": "processing"},
            {"type": "processing"},
            {"type": "transcript", "text": "Synthetic", "segment_id": "1", "is_final": True},
            {"type": "transcript", "text": "Synthetic", "segment_id": "1", "is_final": True},
            {"type": "transcript", "text": "visit", "segment_id": "2", "is_final": True},
        ]
        yield socket

    async def chunks():
        yield b"\x01\x00" * 600
        yield b"\x02\x00" * 100

    provider = GnaniSpeech("test-key", connector=connect)
    assert asyncio.run(provider.transcribe(chunks(), "hi")) == "Synthetic visit"
    assert sent[0] == b"\x01\x00" * 512
    assert sent[1] == b"\x01\x00" * 88 + b"\x02\x00" * 100 + bytes(648)
    assert json.loads(sent[2]) == {"type": "commit"}


def test_timbre_v3_wire_requests_raw_pcm_and_decodes_vendor_chunks():
    class VendorSocket:
        async def send(self, frame):
            assert json.loads(frame) == {
                "text": "Synthetic readback", "voice": "Shivani",
                "model": "timbre-v3.0", "language": "en-IN",
                "audio_config": {
                    "sample_rate": 16000, "num_channels": 1, "sample_width": 2,
                    "encoding": "pcm_s16le", "container": "raw",
                },
            }

        async def recv(self):
            return json.dumps(next(self.events))

    @asynccontextmanager
    async def connect(url, *, additional_headers, **kwargs):
        assert url == "wss://api.vachana.ai/api/v1/tts"
        assert additional_headers == {"X-API-Key-ID": "test-key"}
        socket = VendorSocket()
        socket.events = iter([
            {"type": "start", "request_id": "test-request"},
            {"type": "audio", "data": {
                "audio": base64.b64encode(b"\x01\x00").decode(),
                "chunk_index": 1, "is_final": False,
            }},
            {"type": "complete", "data": {"audio": "", "is_final": True}},
        ])
        yield socket

    async def collect():
        provider = GnaniSpeech("test-key", connector=connect)
        return [chunk async for chunk in provider.synthesize("Synthetic readback", "en")]

    assert asyncio.run(collect()) == [b"\x01\x00"]


def test_tts_failure_reports_error_without_exposing_provider_message():
    class FailingSpeech(MockSpeech):
        async def synthesize(self, text, language):
            async for chunk in super().synthesize(text, language):
                if text != "Readback":
                    yield chunk
            if text == "Readback":
                raise SpeechError("private provider detail")

    async def handle_turn(session, text):
        return TurnResult("LISTENING", {}, False, [], ["Readback"])

    with TestClient(create_app(FailingSpeech(), handle_turn=handle_turn)) as client:
        with client.websocket_connect("/ws") as socket:
            start(socket)
            assert socket.receive_json()["turn_id"] == 0
            send_utterance(socket)
            assert socket.receive_json()["type"] == "transcript"
            assert socket.receive_json()["type"] == "update"
            assert socket.receive_json() == {
                "type": "error", "code": "TTS_UNAVAILABLE", "message": "Please reconnect or retry",
            }
            socket.send_json({"type": "audio", "data": "invalid", "seq": 2})
            assert socket.receive_json()["code"] == "INVALID_AUDIO"


def test_dialogue_failure_keeps_websocket_available():
    async def handle_turn(session, text):
        raise ValueError("private dialogue detail")

    with TestClient(create_app(MockSpeech(), handle_turn=handle_turn)) as client:
        with client.websocket_connect("/ws") as socket:
            start(socket)
            assert socket.receive_json()["turn_id"] == 0
            send_utterance(socket)
            assert socket.receive_json()["type"] == "transcript"
            assert socket.receive_json() == {
                "type": "error", "code": "DIALOGUE_UNAVAILABLE", "message": "Please reconnect or retry",
            }
            socket.send_json({"type": "audio", "data": "AQA=", "seq": 2})
            socket.send_json({"type": "end_utterance"})
            assert socket.receive_json()["type"] == "transcript"


def test_browser_websocket_accepts_same_origin_and_rejects_other_origins():
    from fastapi import WebSocketDisconnect
    import pytest

    with TestClient(create_app()) as client:
        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect("/ws", headers={"origin": "https://outside.example"}):
                pass
        assert rejected.value.code == 1008
        with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as socket:
            start(socket)


def test_local_frontend_serves_same_origin_and_discloses_demo_mode():
    from backend.demo import app as demo_app

    with TestClient(demo_app) as client:
        assert client.get("/runtime-mode").json() == {"demo": True}
        assert client.get("/").status_code == 200
        assert client.get("/audio-worklet.js").status_code == 200
        assert client.get("/.env").status_code == 404
        assert client.get("/backend/main.py").status_code == 404
    with TestClient(create_app()) as client:
        assert client.get("/runtime-mode").json() == {"demo": False}


def test_gnani_upgrade_failure_logs_status_without_response_data(caplog):
    import pytest
    from websockets.datastructures import Headers
    from websockets.exceptions import InvalidStatus
    from websockets.http11 import Response

    @asynccontextmanager
    async def rejected(url, **kwargs):
        assert kwargs["additional_headers"]["x-api-key-id"] == "synthetic-secret"
        raise InvalidStatus(Response(401, "Unauthorized", Headers(), bytearray(b"private data")))
        yield  # async contextmanager on the failure path

    async def chunks():
        yield bytes(1024)

    with pytest.raises(SpeechError):
        asyncio.run(GnaniSpeech(" synthetic-secret ", connector=rejected).transcribe(chunks(), "en"))
    assert "Prisma phase=upgrade error_type=InvalidStatus http_status=401" in caplog.text
    assert "synthetic-secret" not in caplog.text
    assert "private data" not in caplog.text


def test_timbre_error_event_is_logged_without_vendor_text(caplog):
    import pytest

    class VendorSocket:
        async def send(self, frame):
            pass

        async def recv(self):
            return json.dumps({"type": "error", "message": "private vendor text"})

    @asynccontextmanager
    async def connect(url, **kwargs):
        yield VendorSocket()

    async def collect():
        return [chunk async for chunk in GnaniSpeech("test-key", connector=connect)
                .synthesize("Synthetic", "en")]

    with pytest.raises(SpeechError):
        asyncio.run(collect())
    assert "Timbre phase=synthesis error_type=ProviderErrorFrame" in caplog.text
    assert "private vendor text" not in caplog.text


def test_prisma_initialization_reports_allowlisted_code_without_sending_audio(caplog):
    import pytest

    class VendorSocket:
        async def recv(self):
            return json.dumps({
                "type": "error", "code": "SCOPE_NOT_ALLOWED",
                "message": "private vendor text",
            })

    @asynccontextmanager
    async def connect(url, *, additional_headers, **kwargs):
        assert additional_headers == {
            "x-api-key-id": "test-key", "model": "prisma-v3.0",
            "language_code": "en-IN", "x-sample-rate": "16000",
        }
        yield VendorSocket()

    with pytest.raises(SpeechError):
        asyncio.run(GnaniSpeech("test-key", connector=connect)
                    .check_prisma_initialization("en", minimal=True))
    assert "http_status=101" in caplog.text
    assert "provider_code=SCOPE_NOT_ALLOWED" in caplog.text
    assert "private vendor text" not in caplog.text


def test_prisma_error_classification_does_not_print_unknown_codes():
    from backend.gnani_adapter import _prisma_error_code

    assert _prisma_error_code({"code": "SYNTHETIC_SECRET"}) == "UNCLASSIFIED"
    assert _prisma_error_code({"message": "STT engine failed to initialize"}) == "ENGINE_INIT_FAILED"
    assert _prisma_error_code({"detail": {"error_code": "SCOPE_NOT_ALLOWED"}}) == "SCOPE_NOT_ALLOWED"
