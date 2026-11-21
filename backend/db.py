"""Encrypted SQLite storage for explicitly confirmed demo visits."""

import json
import os
import sqlite3
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "./data/visits.db"))


def _cipher():
    key = os.getenv("APP_SECRET_KEY", "")
    if not key or key == "replace_with_a_secure_random_key":
        raise RuntimeError(
            "Set APP_SECRET_KEY in your private .env file before saving records."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "APP_SECRET_KEY must be a valid Fernet key."
        ) from exc


def _connect():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS visits (
            id TEXT PRIMARY KEY,
            encrypted_record BLOB NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def save_confirmed_visit(session, transcript):
    """Save a visit only when the caller explicitly confirms it."""
    if not isinstance(session, dict) or session.get("confirmed") is not True:
        raise PermissionError("Visit has not been explicitly confirmed.")

    record = {
        "session": session,
        "transcript": str(transcript or ""),
    }
    encrypted = _cipher().encrypt(
        json.dumps(record, ensure_ascii=False).encode("utf-8")
    )
    record_id = str(uuid.uuid4())

    with _connect() as connection:
        connection.execute(
            "INSERT INTO visits (id, encrypted_record) VALUES (?, ?)",
            (record_id, encrypted),
        )

    return record_id


def read_confirmed_visits():
    """Read and decrypt stored visits for authorized local review."""
    cipher = _cipher()
    with _connect() as connection:
        rows = connection.execute(
            "SELECT id, encrypted_record, created_at FROM visits ORDER BY created_at"
        ).fetchall()

    results = []
    for record_id, encrypted, created_at in rows:
        try:
            record = json.loads(cipher.decrypt(encrypted).decode("utf-8"))
        except (InvalidToken, ValueError):
            continue
        results.append({
            "id": record_id,
            "created_at": created_at,
            "record": record,
        })
    return results


def delete_all_visits():
    """Delete all saved visit records."""
    with _connect() as connection:
        connection.execute("DELETE FROM visits")
    return True
