import os
import json
import base64
from dotenv import load_dotenv
import websockets

load_dotenv()

STT_URL = "wss://api.vachana.ai/stt/v3/stream"
TTS_URL = "wss://api.vachana.ai/api/v1/tts"

STT_MODEL = "prisma-v3.0"
TTS_MODEL = "timbre-v3.0"
TTS_VOICE = "Sunaina"


def get_api_key():
    key = os.getenv("GNANI_API_KEY")
    if not key:
        raise RuntimeError("GNANI_API_KEY is missing from your .env file.")
    return key


async def open_prisma_connection(language="hi"):
    api_key = get_api_key()

    language_code = "en-IN" if language == "en" else "hi-IN,en-IN"

    headers = {
        "x-api-key-id": api_key,
        "model": STT_MODEL,
        "language_code": language_code,
        "x-sample-rate": "16000",
        "format": "transcribe",
        "x-idle-timeout-sec": "300",
    }

    return await websockets.connect(
        STT_URL,
        additional_headers=headers,
        max_size=None,
    )


async def send_prisma_audio(connection, pcm_frame):
    if len(pcm_frame) != 1024:
        raise ValueError("Prisma audio frames must contain exactly 1024 bytes.")

    await connection.send(pcm_frame)


async def commit_prisma_utterance(connection):
    await connection.send(json.dumps({"type": "commit"}))


async def synthesize_speech(text, language="en"):
    api_key = get_api_key()

    language_code = "hi-IN" if language == "hi" else "en-IN"

    headers = {
        "X-API-Key-ID": api_key,
    }

    request = {
        "text": text,
        "voice": TTS_VOICE,
        "model": TTS_MODEL,
        "language": language_code,
        "speed": 1.0,
        "audio_config": {
            "sample_rate": 24000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "raw",
        },
    }

    async with websockets.connect(
        TTS_URL,
        additional_headers=headers,
        max_size=None,
    ) as connection:

        await connection.send(json.dumps(request))

        async for message in connection:
            event = json.loads(message)

            if event.get("type") == "error":
                raise RuntimeError(event.get("message", "Gnani TTS error"))

            if event.get("type") == "audio":
                audio_data = event.get("data", {}).get("audio")

                if audio_data:
                    yield base64.b64decode(audio_data)

            if event.get("type") == "complete":
                break
