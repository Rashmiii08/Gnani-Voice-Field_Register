"""Check the two real Gnani WebSockets with a synthetic phrase in memory."""

import argparse
import asyncio
import logging
import os

from backend.gnani_adapter import GnaniSpeech, SpeechError


async def main(*, prisma_init_only: bool = False) -> int:
    api_key = os.getenv("GNANI_API_KEY", "").strip()
    if not api_key:
        print("GNANI_API_KEY is missing in this terminal.")
        return 2
    speech = GnaniSpeech(api_key, os.getenv("GNANI_TTS_VOICE", "Shivani"))
    if prisma_init_only:
        status = 0
        for language in ("en", "hi"):
            print(f"Prisma {language}: checking configured headers.", flush=True)
            try:
                await speech.check_prisma_initialization(language)
            except SpeechError:
                status = 1
                print(f"Prisma {language}: checking minimum documented headers.", flush=True)
                try:
                    await speech.check_prisma_initialization(language, minimal=True)
                except SpeechError:
                    continue
                print(f"Prisma {language}: minimum headers accepted; configured headers rejected.")
            else:
                print(f"Prisma {language}: initialized successfully.")
                continue
        return status
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prisma-init-only", action="store_true",
                        help="Probe English and Hindi initialization without sending audio or using Timbre.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(prisma_init_only=args.prisma_init_only)))
