import json
import sqlite3
import pytest
from cryptography.fernet import Fernet
import backend.db as db


def test_unconfirmed_visit_is_rejected():
    with pytest.raises(PermissionError):
        db.save_confirmed_visit({"confirmed": False}, "test transcript")


def test_confirmed_visit_is_encrypted_and_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setenv("APP_SECRET_KEY", Fernet.generate_key().decode())

    session = {"confirmed": True, "form": {"village": "Demo Village"}}
    record_id = db.save_confirmed_visit(session, "Synthetic test transcript")

    with sqlite3.connect(db.DATABASE_PATH) as connection:
        encrypted = connection.execute(
            "SELECT encrypted_record FROM visits WHERE id = ?",
            (record_id,),
        ).fetchone()[0]

    assert b"Synthetic test transcript" not in encrypted
    assert b"Demo Village" not in encrypted

    records = db.read_confirmed_visits()
    assert len(records) == 1
    assert records[0]["record"]["transcript"] == "Synthetic test transcript"


def test_delete_all_visits(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setenv("APP_SECRET_KEY", Fernet.generate_key().decode())

    db.save_confirmed_visit({"confirmed": True}, "Synthetic test")
    assert db.delete_all_visits() is True
    assert db.read_confirmed_visits() == []
