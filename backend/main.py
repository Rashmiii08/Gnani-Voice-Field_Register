import os
import json
import base64
import asyncio
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.gnani_adapter import (
    open_prisma_connection,
    send_prisma_audio,
    commit_prisma_utterance,
    synthesize_speech,
)
from backend.dialogue import create_session, handle_turn

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")


app = FastAPI(title="Gnani Voice Field Register")

@app.get("/")
async def home():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/health")
async def health():
    return {"status": "running"}


@app.websocket("/ws/voice")
async def voice_websocket(client: WebSocket):
    await client.accept()

    stt = None
    session = None
    language = "en"
    session_id = None

    try:
        start_message = await client.receive_json()

        if start_message.get("type") != "start":
            await client.send_json({
                "type": "error",
                "code": "START_REQUIRED",
                "message": "Start the session first."
            })
            return

        language = start_message.get("language", "en")
        if language not in ("en", "hi"):
            language = "en"

        session_id = start_message.get("session_id", "demo-session")
        session = create_session(language=language)

        stt = await open_prisma_connection(language)

        await client.send_json({
            "type": "ready",
            "session_id": session_id
        })

        async def receive_transcripts():
            async for message in stt:
                if isinstance(message, bytes):
                    continue

                event = json.loads(message)

                if event.get("type") == "error":
                    await client.send_json({
                        "type": "error",
                        "code": "STT_ERROR",
                        "message": event.get("message", "Speech recognition failed.")
                    })
                    continue

                if event.get("type") == "transcript":
                    transcript = event.get("text", "")
                    is_final = event.get("is_final", False)

                    await client.send_json({
                        "type": "transcript",
                        "text": transcript,
                        "final": is_final
                    })

                    if is_final and transcript.strip():
                        replies = handle_turn(session, transcript)

                        for reply in replies:
                            if isinstance(reply, dict):
                                reply_text = reply.get("text", "") if reply.get("type") == "say" else ""
                            else:
                                reply_text = str(reply)

                            if reply_text:
                                await client.send_json({
                                    "type": "response_text",
                                    "text": reply_text
                                })

                                async for audio_chunk in synthesize_speech(
                                    reply_text,
                                    language
                                ):
                                    await client.send_json({
                                        "type": "audio",
                                        "data": base64.b64encode(
                                            audio_chunk
                                        ).decode("ascii")
                                    })

                        await client.send_json({
                            "type": "update",
                            "state": session.get("state"),
                            "form": session.get("form", {}),
                            "danger_flag": bool(session.get("danger_flags")),
                            "follow_ups": session.get("follow_ups", [])
                        })

        receiver = asyncio.create_task(receive_transcripts())

        while True:
            message = await client.receive_json()
            message_type = message.get("type")

            if message_type == "audio":
                audio_data = base64.b64decode(message.get("data", ""))
                for offset in range(0, len(audio_data), 1024):
                    frame = audio_data[offset:offset + 1024]

                    if len(frame) == 1024:
                        await send_prisma_audio(stt, frame)

            elif message_type == "end_utterance":
                await commit_prisma_utterance(stt)

            elif message_type == "interrupt":
                await client.send_json({
                    "type": "interrupted"
                })

            elif message_type == "close":
                break

    except WebSocketDisconnect:
        pass

    except Exception as error:
        try:
            await client.send_json({
                "type": "error",
                "code": "BACKEND_ERROR",
                "message": str(error)
            })
        except Exception:
            pass

    finally:
        if stt is not None:
            await stt.close()

        if "receiver" in locals():
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)


app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

