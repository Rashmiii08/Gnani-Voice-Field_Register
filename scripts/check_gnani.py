"""Check the two real Gnani WebSockets with a synthetic phrase in memory."""

import asyncio
import logging
import os

from backend.gnani_adapter import GnaniSpeech, SpeechError


async def main() -> int:
    api_key = os.getenv("GNANI_API_KEY", "").strip()
    if not api_key:
        print("GNANI_API_KEY is missing in this terminal.")
        return 2
    speech = GnaniSpeech(api_key, os.getenv("GNANI_TTS_VOICE", "Shivani"))
    audio = bytearray()
    try:
        async with asyncio.timeout(30):
            async for chunk in speech.synthesize("This is a synthetic voice test.", "en"):
                audio.extend(chunk)
    except (SpeechError, TimeoutError) as exc:
        print(f"Timbre: failed ({type(exc).__name__}).")
    else:
        if audio:
            print("Timbre: returned PCM audio.")
        else:
            print("Timbre: completed without audio.")
    has_tts_audio = bool(audio)
    audio.extend(bytes(16000))

    async def chunks():
        for offset in range(0, len(audio), 3200):
            yield bytes(audio[offset:offset + 3200])

    try:
        async with asyncio.timeout(30):
            transcript = await speech.transcribe(chunks(), "en")
    except (SpeechError, TimeoutError) as exc:
        print(f"Prisma: failed ({type(exc).__name__}).")
        return 1
    if has_tts_audio and "test" in transcript.casefold():
        print("Prisma: recognized the synthetic phrase.")
        return 0
    print("Prisma: connected, but recognition of the synthetic phrase was not verified.")
    return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(asyncio.run(main()))
