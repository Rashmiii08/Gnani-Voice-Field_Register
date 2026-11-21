"""
Safety-first danger-sign detection for the Gnani Voice Hackathon.

IMPORTANT:
- This module is a demo safety aid, not a diagnostic system.
- Rules and thresholds must be reviewed by qualified public-health/clinical
  personnel against the exact local guideline before field use.
- The master spec explicitly gives temperature >= 37.5 C as an example vital
  rule and requires rule hits + valid LLM candidates to be combined.
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
        r"\b(pregnan(t|cy)|antenatal|गर्भवती|गर्भावस्था)\b.{0,80}\b(bleed(ing)?|blood|खून|रक्तस्राव)\b",
        r"\b(bleed(ing)?|blood|खून|रक्तस्राव)\b.{0,80}\b(pregnan(t|cy)|antenatal|गर्भवती|गर्भावस्था)\b",
        r"\b(vaginal bleeding|bleeding during pregnancy|pregnancy bleeding)\b",
    ],
    "NB_FEVER": [
        r"\b(newborn|new born|neonate|नवजात)\b.{0,80}\b(fever|temperature|hot|बुखार|ताप)\b",
        r"\b(fever|बुखार|ताप)\b.{0,80}\b(newborn|new born|neonate|नवजात)\b",
    ],
}

# Thresholds are demo examples from the supplied master spec.
# Validate thresholds and age/context applicability with a qualified reviewer.
VITAL_RULES = {
    "NB_FEVER": {
        "field": "temperature_c",
        "operator": "gte",
        "threshold": 37.5,
    }
}


def _normalise_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _safe_number(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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
    Return sorted unique danger IDs from rule hits, vital thresholds and
    allow-listed LLM candidates.

    Example:
        check_danger(
            {"temperature_c": 38.0},
            "The newborn has a fever",
            ["NB_FEVER", "UNAPPROVED_ID"],
        )
        -> ["NB_FEVER"]
    """
    form = form or {}
    text = _normalise_text(transcript_text)
    detected: Set[str] = set()

    for danger_id, patterns in RULES.items():
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            detected.add(danger_id)

    for danger_id, rule in VITAL_RULES.items():
        value = _safe_number(form.get(rule["field"]))
        if value is None:
            continue
        if rule["operator"] == "gte" and value >= float(rule["threshold"]):
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
