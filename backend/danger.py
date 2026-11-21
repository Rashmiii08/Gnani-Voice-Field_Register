"""Conservative referral flags for explicitly reported symptoms in synthetic visits.

WHO young infant chart booklet (2019): https://www.who.int/publications/i/item/9789241516365
WHO pregnancy care guide: https://www.who.int/campaigns/world-health-day/2025/key-messages
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

# IDs used by the master spec's LLM output schema.
ALLOWED_DANGER_IDS: Set[str] = {
    "PREG_BLEEDING",
    "NB_FEVER",
}

# Keep patterns deliberately broad to favor recall in this demo.
# Add reviewed local-language variants only after validation.
RULES: Dict[str, List[str]] = {
    "PREG_BLEEDING": [
        r"\b(pregnan(t|cy)|antenatal|गर्भवती|गर्भावस्था)\b.{0,80}\b(bleed(ing)?|रक्तस्राव)\b",
        r"\b(bleed(ing)?|रक्तस्राव)\b.{0,80}\b(pregnan(t|cy)|antenatal|गर्भवती|गर्भावस्था)\b",
        r"\b(vaginal bleeding|bleeding during pregnancy|pregnancy bleeding)\b",
    ],
    "NB_FEVER": [
        r"\b(newborn|new born|neonate|नवजात)\b.{0,80}\b(fever|बुखार)\b",
        r"\b(fever|बुखार)\b.{0,80}\b(newborn|new born|neonate|नवजात)\b",
    ],
}

def _normalise_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _valid_llm_candidates(candidates: Optional[Iterable[str]]) -> Set[str]:
    """Only accept known danger IDs; ignore arbitrary model-generated strings."""
    valid: Set[str] = set()
    for candidate in candidates or []:
        candidate_id = str(candidate).strip().upper()
        if candidate_id in ALLOWED_DANGER_IDS:
            valid.add(candidate_id)
    return valid


def check_danger(
    form: Optional[Mapping[str, Any]] = None,
    transcript_text: str = "",
    llm_candidates: Optional[Iterable[str]] = None,
) -> List[str]:
    """
    Return sorted unique danger IDs from rule hits and
    allow-listed LLM candidates.

    Example:
        check_danger(
            {"temperature_c": 38.0},
            "The newborn has a fever",
            ["NB_FEVER", "UNAPPROVED_ID"],
        )
        -> ["NB_FEVER"]
    """
    del form  # No numeric threshold without measurement context.
    text = _normalise_text(transcript_text)
    # Devanagari vowel marks are not word characters under Python's \b.
    text = text.replace("गर्भवती", " pregnant ").replace("गर्भावस्था", " pregnancy ")
    text = text.replace("रक्तस्राव", " bleeding ").replace("खून आ", " bleeding ").replace("खून बह", " bleeding ")
    text = text.replace("नवजात", " newborn ").replace("बुखार", " fever ")
    detected: Set[str] = set()

    for danger_id, patterns in RULES.items():
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            detected.add(danger_id)

    detected.update(_valid_llm_candidates(llm_candidates))
    return sorted(detected)


if __name__ == "__main__":
    examples = [
        ({}, "The pregnant woman is experiencing bleeding", []),
        ({"temperature_c": 38.0}, "The newborn feels hot", []),
        ({}, "Routine visit, no concern reported", ["NOT_A_VALID_ID"]),
    ]
    for sample_form, transcript, candidates in examples:
        print({
            "transcript": transcript,
            "danger_ids": check_danger(sample_form, transcript, candidates),
        })
