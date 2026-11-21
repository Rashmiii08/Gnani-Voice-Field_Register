"""Conservative safety keyword checks. This is not a diagnostic tool."""

DANGER_KEYWORDS = {
    "urgent": [
        "severe pain",
        "high fever",
        "difficulty breathing",
        "chest pain",
        "unconscious",
        "heavy bleeding",
        "तेज दर्द",
        "तेज बुखार",
        "सांस लेने में कठिनाई",
        "सीने में दर्द",
        "बेहोश",
    ],
    "emergency": [
        "emergency",
        "medical emergency",
        "आपातकाल",
        "आपातकालीन स्थिति",
    ],
}


def check_danger(form=None, transcript_text="", llm_candidates=None):
    """Return safety flags when configured keywords are found."""
    text = str(transcript_text or "").lower()

    if isinstance(form, dict):
        text += " " + " ".join(
            str(value) for value in form.values() if value is not None
        ).lower()

    flags = []

    for level, keywords in DANGER_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            flags.append(level)

    if isinstance(llm_candidates, (list, tuple, set)):
        for candidate in llm_candidates:
            if candidate in ("urgent", "emergency") and candidate not in flags:
                flags.append(candidate)

    return flags
