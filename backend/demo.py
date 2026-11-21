"""Explicit, scripted synthetic demo. PCM tones exercise playback without a vendor key."""

import asyncio
import itertools
import math
import struct

from backend.main import TurnResult, create_app

PATIENTS = itertools.cycle(("DEMO-001", "DEMO-002"))


def new_session(session_id, language):
    return next(PATIENTS)


class DemoSpeech:
    async def transcribe(self, audio, language):
        received = 0
        async for chunk in audio:
            received += len(chunk)
        if not received:
            return ""
        name = "आशा शर्मा" if language == "hi" else "Asha Sharma"
        return f"[Synthetic fixture] {name}"

    async def synthesize(self, text, language):
        for frequency in (440, 554, 660, 554, 440, 554):
            yield struct.pack("<1600h", *(
                round(2000 * math.sin(2 * math.pi * frequency * sample / 16000))
                for sample in range(1600)
            ))
            await asyncio.sleep(0.1)


async def preview(identifier, transcript):
    return TurnResult(
        "CONFIRMING",
        {"beneficiary_id": identifier, "visit_type": "other",
         "weight_kg": 52 if identifier == "DEMO-001" else 61},
        False,
        [],
        ["Synthetic preview"],
    )


app = create_app(DemoSpeech(), session_factory=new_session, handle_turn=preview, demo_mode=True)
