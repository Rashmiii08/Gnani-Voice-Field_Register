"""Authenticated, single-operator localhost app using live Gnani speech."""

import asyncio
import base64
import binascii
import hmac
import os
import re
import secrets
from dataclasses import asdict

from cryptography.fernet import Fernet
from fastapi import Request
from fastapi.responses import PlainTextResponse

from backend.danger import check_danger
from backend.db import DEFAULT_DB_PATH, save_record
from backend.dialogue import Session, handle_turn
from backend.extract import extract_fields
from backend.gnani_adapter import GnaniSpeech
from backend.main import TurnResult, create_app
from backend.phrases import get_phrase

COOKIE = "field_register_operator"
COOKIE_LIFETIME = 8 * 3600


def create_live_app(*, provider=None, password=None, db_path=None):
    if provider is None:
        key = os.getenv("GNANI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("Set GNANI_API_KEY in the terminal that starts Uvicorn.")
        provider = GnaniSpeech(key, os.getenv("GNANI_TTS_VOICE", "Shivani"))
    password = password if password is not None else os.getenv("FIELD_REGISTER_PASSWORD")
    if not password:
        raise RuntimeError("Set FIELD_REGISTER_PASSWORD for the local operator login.")
    data_key = os.getenv("DATA_KEY")
    try:
        Fernet((data_key or "").encode())
    except ValueError as exc:
        raise RuntimeError("Set DATA_KEY to a valid Fernet key before starting the live app.") from exc
    db_path = db_path or os.getenv("FIELD_REGISTER_DB") or DEFAULT_DB_PATH
    signing_key = secrets.token_bytes(32)

    def signature(identifier):
        return hmac.digest(signing_key, identifier.encode(), "sha256").hex()

    def cookie_owner(connection):
        value = connection.cookies.get(COOKIE, "")
        identifier, _, digest = value.partition(".")
        if re.fullmatch(r"[0-9a-f]{48}", identifier) and re.fullmatch(r"[0-9a-f]{64}", digest):
            if hmac.compare_digest(signature(identifier), digest):
                return identifier
        return None

    def new_session(session_id, language):
        # Role A owns the first spoken AI disclosure.
        return Session(session_id, language, disclosure_sent=True, require_identity=True)

    def run_turn(session, text):
        def save(transcript, form):
            if not re.fullmatch(r"DEMO-[0-9]{3,6}", form.get("beneficiary_id") or ""):
                raise ValueError("Verified synthetic identifier required")
            return save_record(transcript, form, db_path, visit_key=session.visit_key)

        replies = handle_turn(session, text, extract_fields, check_danger, save)
        if session.danger_flag:
            utterances = [get_phrase(session.language, "refer_now")]
        else:
            utterances = [reply.text for reply in replies]
        return TurnResult(session.state, asdict(session.form), session.danger_flag,
                          session.follow_ups, utterances)

    async def process_turn(session, text):
        return await asyncio.to_thread(run_turn, session, text)

    app = create_app(provider, session_factory=new_session, handle_turn=process_turn,
                     authorize=cookie_owner)

    @app.middleware("http")
    async def local_operator(request: Request, call_next):
        if cookie_owner(request):
            return await call_next(request)
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        provided = b""
        if scheme.lower() == "basic":
            try:
                provided = base64.b64decode(token, validate=True)
            except (ValueError, binascii.Error):
                pass
        if not hmac.compare_digest(provided, ("operator:" + password).encode()):
            return PlainTextResponse("Operator login required", status_code=401, headers={
                "WWW-Authenticate": 'Basic realm="Voice Field Register", charset="UTF-8"',
                "Cache-Control": "no-store",
            })
        owner = secrets.token_hex(24)
        response = await call_next(request)
        response.set_cookie(COOKIE, f"{owner}.{signature(owner)}", max_age=COOKIE_LIFETIME,
                            httponly=True, samesite="strict", secure=request.url.scheme == "https")
        return response

    return app
