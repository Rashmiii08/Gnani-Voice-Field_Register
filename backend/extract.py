"""Conservative extraction of explicitly named synthetic visit fields."""

import re
import unicodedata
from datetime import date

from backend.llm import validate_llm_result

ID_PATTERN = re.compile(r"(?<![\w-])(?:demo|डेमो)[ -]*((?:[0-9][ -]){1,5}[0-9]|[0-9]{1,6})(?![\w-]|[ -]+[0-9])")
DIGIT_WORDS = {
    word: str(index)
    for index, words in enumerate(zip(
        "zero one two three four five six seven eight nine".split(),
        "शून्य एक दो तीन चार पाँच छह सात आठ नौ".split(),
    ))
    for word in words
}
DIGIT_WORDS["पांच"] = "5"
DIGIT_WORDS["oh"] = "0"
ID_WORDS = re.compile(r"(?<!\w)(?:demo|डेमो)[ -]+(" + "|".join(DIGIT_WORDS) +
                      r")(?=$|[\s,।.])")


def extract_fields(text, state, form, today):
    del state, form, today
    text = unicodedata.normalize("NFKC", text).casefold()
    text = "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in text)
    patch = {}
    ids = {int(re.sub(r"[ -]", "", m[1])) for m in ID_PATTERN.finditer(text)}
    for match in ID_WORDS.finditer(text):
        words = re.findall(r"[^\s,।.]+", text[match.start(1):])
        digits = []
        for word in words:
            if word not in DIGIT_WORDS:
                break
            digits.append(DIGIT_WORDS[word])
        if len(digits) > 6:
            raise ValueError("Beneficiary ID exceeds six digits")
        if digits:
            ids.add(int("".join(digits)))
    if len(ids) > 1:
        raise ValueError("Conflicting beneficiary IDs")
    if ids:
        patch["beneficiary_id"] = f"DEMO-{ids.pop():03d}"

    for visit_type, pattern in {
        "antenatal": r"\bantenatal\b|\bprenatal\b|गर्भावस्था",
        "postnatal": r"\bpostnatal\b|\bpostpartum\b|प्रसव के बाद",
        "newborn": r"\bnew\s?born\b|नवजात",
        "immunisation": r"\bimmuni[sz]ation\b|टीकाकरण",
        "other": r"\b(?:routine|other) visit\b|सामान्य विज़िट",
    }.items():
        if re.search(pattern, text):
            if "visit_type" in patch:
                raise ValueError("Conflicting visit types")
            patch["visit_type"] = visit_type

    number = r"([0-9]{1,3}(?:\.[0-9]{1,2})?)"
    for field, label, unit in (
        ("weight_kg", r"weight|वजन|वज़न", r"kilograms?|kgs?|किलो|किग्रा"),
        ("temperature_c", r"temperature|तापमान", r"(?:degrees?\s*)?celsius|°c|सेल्सियस"),
    ):
        match = re.search(rf"(?:{label})\s*(?:is|to|है|:)?\s*{number}\s*(?:{unit})(?!\w)", text)
        if match:
            patch[field] = float(match[1])

    bp = re.search(r"(?:blood pressure|\bbp\b|बीपी)\D{0,8}(\d{2,3})\s*(?:/|over|बटा)\s*(\d{2,3})", text)
    if bp:
        patch["bp_systolic"], patch["bp_diastolic"] = map(int, bp.groups())

    next_date = re.search(r"(?:next visit|अगली विज़िट)(?:\s+date)?\s*(?:is|on|:)?\s*(\d{4}-\d\d-\d\d)", text)
    if next_date:
        patch["next_visit_date"] = date.fromisoformat(next_date[1]).isoformat()

    vaccine = re.search(r"(?:vaccines? due|vaccinations? due|बाकी टीके)\s*(?:are|:)?\s*([\w -]+)", text)
    if vaccine:
        named = {"bcg", "opv", "ipv", "hepatitis b", "pentavalent", "rotavirus"}
        values = re.split(r"\s+(?:and|और)\s+", vaccine[1].strip())
        if all(value in named for value in values):
            patch["vaccinations_due"] = values

    return validate_llm_result({"intent": "provide_info" if patch else "other", "patch": patch})
