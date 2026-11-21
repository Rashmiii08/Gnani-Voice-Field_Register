from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from backend.db import delete_all_records, get_records, save_record
from backend.live import create_live_app


class ScriptedSpeech:
    def __init__(self, transcripts):
        self.transcripts = iter(transcripts)
        self.replies = []

    async def transcribe(self, audio, language):
        assert b"".join([part async for part in audio]) == b"\x01\x00"
        return next(self.transcripts)

    async def synthesize(self, text, language):
        self.replies.append((language, text))
        yield b"\x01\x00"


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_KEY", Fernet.generate_key().decode())
    return tmp_path / "synthetic.sqlite3"


def login(client):
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("operator", "synthetic-test")).status_code == 200


def turn(socket, sequence):
    socket.send_json({"type": "audio", "data": "AQA=", "seq": sequence})
    socket.send_json({"type": "end_utterance"})
    assert socket.receive_json()["type"] == "transcript"
    update = socket.receive_json()
    assert update["type"] == "update"
    assert socket.receive_json()["type"] == "update"
    assert socket.receive_json()["type"] == "audio"
    return update


def test_live_app_confirms_correction_and_encrypts_once(storage):
    speech = ScriptedSpeech([
        "Routine visit for Demo one two three. Weight 55 kilograms.",
        "Actually weight 56 kilograms.", "okay", "Weight 56 kilograms.",
        "Yes.", "Yes.",
    ])
    app = create_live_app(provider=speech, password="synthetic-test", db_path=storage)
    with TestClient(app) as client:
        login(client)
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"type": "start", "language": "en", "session_id": "test-visit"})
            assert socket.receive_json() == {"type": "ready", "session_id": "test-visit"}
            assert socket.receive_json()["type"] == "audio"
            update = turn(socket, 1)
            assert update["state"] == "CONFIRMING"
            assert update["form"]["beneficiary_id"] == "DEMO-123"
            # Readback and confirmation are separate provider outputs.
            assert socket.receive_json()["type"] == "audio"
            update = turn(socket, 2)
            assert update["form"]["weight_kg"] == 56
            assert socket.receive_json()["type"] == "audio"
            assert turn(socket, 3)["state"] == "LISTENING"
            assert not storage.exists()
            assert turn(socket, 4)["state"] == "CONFIRMING"
            assert socket.receive_json()["type"] == "audio"
            assert turn(socket, 5)["state"] == "SAVED"
            assert turn(socket, 6)["state"] == "SAVED"
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"type": "resume", "session_id": "test-visit", "draft_version": 1})
            assert socket.receive_json()["type"] == "ready"
            assert socket.receive_json()["state"] == "SAVED"
        client.cookies.clear()
        login(client)
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"type": "resume", "session_id": "test-visit", "draft_version": 1})
            assert socket.receive_json()["code"] == "SESSION_NOT_RESUMABLE"
    rows = get_records(storage)
    assert len(rows) == 1 and rows[0]["form"]["weight_kg"] == 56
    assert "Weight 55 kilograms" in rows[0]["transcript"]
    assert b"DEMO-123" not in storage.read_bytes()
    assert b"Weight 55" not in storage.read_bytes()
    assert delete_all_records(storage) == 1
    assert get_records(storage) == []


def test_live_access_and_referral_preempt_confirmation(storage):
    speech = ScriptedSpeech(["नवजात को बुखार है।", "हाँ।"])
    app = create_live_app(provider=speech, password="synthetic-test", db_path=storage)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws"):
                pass
        login(client)
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"type": "start", "language": "hi", "session_id": "danger"})
            assert socket.receive_json()["type"] == "ready"
            assert socket.receive_json()["type"] == "audio"
            assert turn(socket, 1)["danger_flag"] is True
            assert "संपर्क" in speech.replies[-1][1]
            assert turn(socket, 2)["state"] == "LISTENING"
        assert not storage.exists()


def test_simultaneous_retries_write_only_one_row(storage):
    def save():
        return save_record("Synthetic visit", {"beneficiary_id": "DEMO-123"},
                           storage, visit_key="same-visit")

    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = list(executor.map(lambda _: save(), range(4)))
    assert len(set(ids)) == 1
    assert len(get_records(storage)) == 1


def test_hindi_identity_and_number_extraction():
    from backend.extract import extract_fields

    result = extract_fields("सामान्य विज़िट डेमो १२३। वज़न ५५ किलो।", None, None, None)
    assert result.patch == {"beneficiary_id": "DEMO-123", "visit_type": "other", "weight_kg": 55}
