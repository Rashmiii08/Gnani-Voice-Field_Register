"""
SQLite persistence with Fernet encryption for transcripts and form payloads.

Set DATA_KEY in .env. Generate one with:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

This demo encrypts the sensitive payload columns. Database metadata such as
record IDs and timestamps remain visible. Protect database files and backups too.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "gnani_records.sqlite3"


def _load_cipher() -> Fernet:
    load_dotenv(PROJECT_ROOT / ".env")
    key = os.getenv("DATA_KEY")
    if not key:
        raise RuntimeError(
            "DATA_KEY is missing. Create a .env file and set DATA_KEY to a "
            "Fernet key. See .env.example and README.md."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("DATA_KEY is not a valid Fernet key.") from exc


def _connect(db_path: Optional[str | Path] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: Optional[str | Path] = None) -> None:
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visit_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                transcript_encrypted BLOB NOT NULL,
                form_encrypted BLOB NOT NULL
            )
            """
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS visit_confirmations (
                visit_key TEXT PRIMARY KEY,
                record_id INTEGER NOT NULL REFERENCES visit_records(id) ON DELETE CASCADE
            )"""
        )
        conn.commit()


def save_record(
    transcript: str,
    form: Dict[str, Any],
    db_path: Optional[str | Path] = None,
    *,
    visit_key: str | None = None,
) -> int:
    """Encrypt transcript and form JSON before writing them to SQLite."""
    cipher = _load_cipher()
    transcript_token = cipher.encrypt((transcript or "").encode("utf-8"))
    form_json = json.dumps(form or {}, ensure_ascii=False, separators=(",", ":"))
    form_token = cipher.encrypt(form_json.encode("utf-8"))
    created_at = datetime.now(timezone.utc).isoformat()

    init_db(db_path)
    with closing(_connect(db_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        if visit_key is not None:
            existing = conn.execute(
                "SELECT record_id FROM visit_confirmations WHERE visit_key = ?", (visit_key,)
            ).fetchone()
            if existing:
                return int(existing["record_id"])
        cursor = conn.execute(
            """
            INSERT INTO visit_records
                (created_at, transcript_encrypted, form_encrypted)
            VALUES (?, ?, ?)
            """,
            (created_at, transcript_token, form_token),
        )
        record_id = int(cursor.lastrowid)
        if visit_key is not None:
            conn.execute(
                "INSERT INTO visit_confirmations VALUES (?, ?)", (visit_key, record_id)
            )
        return record_id


def get_records(db_path: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    """Decrypt records for an authorized UI/application caller."""
    cipher = _load_cipher()
    init_db(db_path)
    with closing(_connect(db_path)) as conn, conn:
        rows = conn.execute(
            """
            SELECT id, created_at, transcript_encrypted, form_encrypted
            FROM visit_records ORDER BY id DESC
            """
        ).fetchall()

    records: List[Dict[str, Any]] = []
    for row in rows:
        try:
            transcript = cipher.decrypt(row["transcript_encrypted"]).decode("utf-8")
            form_data = cipher.decrypt(row["form_encrypted"]).decode("utf-8")
            records.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "transcript": transcript,
                "form": json.loads(form_data),
            })
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            # Do not return corrupt or undecryptable patient data as plaintext.
            raise RuntimeError(f"Could not decrypt record ID {row['id']}.") from exc
    return records


def delete_all_records(db_path: Optional[str | Path] = None) -> int:
    """Delete both encrypted payload columns and their confirmation keys."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    if not path.is_file():
        return 0
    init_db(path)
    with closing(_connect(path)) as conn:
        conn.execute("PRAGMA secure_delete = ON")
        with conn:
            count = conn.execute("DELETE FROM visit_records").rowcount
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
    return count


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at: {DEFAULT_DB_PATH}")
