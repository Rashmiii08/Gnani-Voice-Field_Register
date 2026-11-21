"""Team B dialogue and state machine for Gnani Voice Field Register."""

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any

from backend.llm import LLMResult, validate_llm_result


@dataclass
class VisitForm:
    beneficiary_id: str | None = None
    visit_type: str | None = None
    weight_kg: float | None = None
    vaccinations_due: list[str] = field(default_factory=list)
    next_visit_date: str | None = None
    temperature_c: float | None = None
    bp_systolic: int | None = None
    bp_diastolic: int | None = None


@dataclass
class Session:
    session_id: str
    language: str = "en"
    state: str = "LISTENING"
    form: VisitForm = field(default_factory=VisitForm)
    danger_flag: bool = False
    follow_ups: list[str] = field(default_factory=list)
    turn_id: int = 0
    disclosure_sent: bool = False
    last_transcript: str = ""
    transcript_history: list[str] = field(default_factory=list)
    record_id: int | None = None


@dataclass
class Say:
    text: str
    kind: str = "prompt"


SUPPORTED_LANGUAGES = {"en", "hi", "kn"}

MESSAGES = {
    "en": {
        "disclosure": "I am an AI assistant. I will help record your visit information.",
        "confirm": "Please confirm whether these visit details are correct. Say yes or no.",
        "yes": "Your confirmation has been received.",
        "no": "Okay. Please tell me what needs to be corrected.",
        "saved": "This visit has already been confirmed.",
        "retry": "I could not understand that information. Please repeat it.",
        "empty": "Please provide the beneficiary visit details.",
        "referral": "Please contact your nearest Primary Health Centre for assistance.",
        "correct": "Please tell me which information needs correction.",
    },
    "hi": {
        "disclosure": "à¤®à¥ˆà¤‚ à¤à¤• AI à¤¸à¤¹à¤¾à¤¯à¤• à¤¹à¥‚à¤à¥¤ à¤®à¥ˆà¤‚ à¤†à¤ªà¤•à¥€ à¤µà¤¿à¤œà¤¼à¤¿à¤Ÿ à¤•à¥€ à¤œà¤¾à¤¨à¤•à¤¾à¤°à¥€ à¤¦à¤°à¥à¤œ à¤•à¤°à¤¨à¥‡ à¤®à¥‡à¤‚ à¤®à¤¦à¤¦ à¤•à¤°à¥‚à¤à¤—à¤¾à¥¤",
        "confirm": "à¤•à¥ƒà¤ªà¤¯à¤¾ à¤¬à¤¤à¤¾à¤à¤‚ à¤•à¤¿ à¤•à¥à¤¯à¤¾ à¤¯à¥‡ à¤¸à¤­à¥€ à¤œà¤¾à¤¨à¤•à¤¾à¤°à¥€ à¤¸à¤¹à¥€ à¤¹à¥ˆà¥¤ à¤¹à¤¾à¤ à¤¯à¤¾ à¤¨à¤¹à¥€à¤‚ à¤•à¤¹à¥‡à¤‚à¥¤",
        "yes": "à¤†à¤ªà¤•à¥€ à¤ªà¥à¤·à¥à¤Ÿà¤¿ à¤ªà¥à¤°à¤¾à¤ªà¥à¤¤ à¤¹à¥‹ à¤—à¤ˆ à¤¹à¥ˆà¥¤",
        "no": "à¤ à¥€à¤• à¤¹à¥ˆà¥¤ à¤•à¥ƒà¤ªà¤¯à¤¾ à¤¬à¤¤à¤¾à¤à¤‚ à¤•à¤¿ à¤•à¥à¤¯à¤¾ à¤¸à¥à¤§à¤¾à¤° à¤•à¤°à¤¨à¤¾ à¤¹à¥ˆà¥¤",
        "saved": "à¤‡à¤¸ à¤µà¤¿à¤œà¤¼à¤¿à¤Ÿ à¤•à¥€ à¤ªà¥à¤·à¥à¤Ÿà¤¿ à¤ªà¤¹à¤²à¥‡ à¤¹à¥€ à¤¹à¥‹ à¤šà¥à¤•à¥€ à¤¹à¥ˆà¥¤",
        "retry": "à¤œà¤¾à¤¨à¤•à¤¾à¤°à¥€ à¤¸à¤®à¤ à¤¨à¤¹à¥€à¤‚ à¤†à¤ˆà¥¤ à¤•à¥ƒà¤ªà¤¯à¤¾ à¤¦à¥‹à¤¬à¤¾à¤°à¤¾ à¤¬à¤¤à¤¾à¤à¤‚à¥¤",
        "empty": "à¤•à¥ƒà¤ªà¤¯à¤¾ à¤²à¤¾à¤­à¤¾à¤°à¥à¤¥à¥€ à¤•à¥€ à¤µà¤¿à¤œà¤¼à¤¿à¤Ÿ à¤•à¥€ à¤œà¤¾à¤¨à¤•à¤¾à¤°à¥€ à¤¬à¤¤à¤¾à¤à¤‚à¥¤",
        "referral": "à¤•à¥ƒà¤ªà¤¯à¤¾ à¤¸à¤¹à¤¾à¤¯à¤¤à¤¾ à¤•à¥‡ à¤²à¤¿à¤ à¤…à¤ªà¤¨à¥‡ à¤¨à¤œà¤¼à¤¦à¥€à¤•à¥€ à¤ªà¥à¤°à¤¾à¤¥à¤®à¤¿à¤• à¤¸à¥à¤µà¤¾à¤¸à¥à¤¥à¥à¤¯ à¤•à¥‡à¤‚à¤¦à¥à¤° à¤¸à¥‡ à¤¸à¤‚à¤ªà¤°à¥à¤• à¤•à¤°à¥‡à¤‚à¥¤",
        "correct": "à¤•à¥ƒà¤ªà¤¯à¤¾ à¤¬à¤¤à¤¾à¤à¤‚ à¤•à¤¿ à¤•à¤¿à¤¸ à¤œà¤¾à¤¨à¤•à¤¾à¤°à¥€ à¤®à¥‡à¤‚ à¤¸à¥à¤§à¤¾à¤° à¤•à¤°à¤¨à¤¾ à¤¹à¥ˆà¥¤",
    },
    "kn": {
        "disclosure": "à²¨à²¾à²¨à³ AI à²¸à²¹à²¾à²¯à²•. à²¨à²¿à²®à³à²® à²­à³‡à²Ÿà²¿à²¯ à²®à²¾à²¹à²¿à²¤à²¿à²¯à²¨à³à²¨à³ à²¦à²¾à²–à²²à²¿à²¸à²²à³ à²¸à²¹à²¾à²¯ à²®à²¾à²¡à³à²¤à³à²¤à³‡à²¨à³†.",
        "confirm": "à²¦à²¯à²µà²¿à²Ÿà³à²Ÿà³ à²ˆ à²­à³‡à²Ÿà²¿à²¯ à²µà²¿à²µà²°à²—à²³à³ à²¸à²°à²¿à²¯à²¾à²—à²¿à²µà³†à²¯à³‡ à²Žà²‚à²¦à³ à²–à²šà²¿à²¤à²ªà²¡à²¿à²¸à²¿. à²¹à³Œà²¦à³ à²…à²¥à²µà²¾ à²‡à²²à³à²² à²Žà²‚à²¦à³ à²¹à³‡à²³à²¿.",
        "yes": "à²¨à²¿à²®à³à²® à²¦à³ƒà²¢à³€à²•à²°à²£ à²¸à³à²µà³€à²•à²°à²¿à²¸à²²à²¾à²—à²¿à²¦à³†.",
        "no": "à²¸à²°à²¿. à²¯à²¾à²µ à²®à²¾à²¹à²¿à²¤à²¿à²¯à²¨à³à²¨à³ à²¤à²¿à²¦à³à²¦à³à²ªà²¡à²¿ à²®à²¾à²¡à²¬à³‡à²•à³ à²Žà²‚à²¦à³ à²¤à²¿à²³à²¿à²¸à²¿.",
        "saved": "à²ˆ à²­à³‡à²Ÿà²¿à²¯à²¨à³à²¨à³ à²ˆà²—à²¾à²—à²²à³‡ à²¦à³ƒà²¢à³€à²•à²°à²¿à²¸à²²à²¾à²—à²¿à²¦à³†.",
        "retry": "à²† à²®à²¾à²¹à²¿à²¤à²¿ à²…à²°à³à²¥à²µà²¾à²—à²²à²¿à²²à³à²². à²¦à²¯à²µà²¿à²Ÿà³à²Ÿà³ à²®à²¤à³à²¤à³Šà²®à³à²®à³† à²¹à³‡à²³à²¿.",
        "empty": "à²¦à²¯à²µà²¿à²Ÿà³à²Ÿà³ à²«à²²à²¾à²¨à³à²­à²µà²¿à²¯ à²­à³‡à²Ÿà²¿à²¯ à²µà²¿à²µà²°à²—à²³à²¨à³à²¨à³ à²¤à²¿à²³à²¿à²¸à²¿.",
        "referral": "à²¦à²¯à²µà²¿à²Ÿà³à²Ÿà³ à²¸à²¹à²¾à²¯à²•à³à²•à²¾à²—à²¿ à²¹à²¤à³à²¤à²¿à²°à²¦ à²ªà³à²°à²¾à²¥à²®à²¿à²• à²†à²°à³‹à²—à³à²¯ à²•à³‡à²‚à²¦à³à²°à²µà²¨à³à²¨à³ à²¸à²‚à²ªà²°à³à²•à²¿à²¸à²¿.",
        "correct": "à²¯à²¾à²µ à²®à²¾à²¹à²¿à²¤à²¿à²¯à²¨à³à²¨à³ à²¤à²¿à²¦à³à²¦à³à²ªà²¡à²¿ à²®à²¾à²¡à²¬à³‡à²•à³ à²Žà²‚à²¦à³ à²¤à²¿à²³à²¿à²¸à²¿.",
    },
}

FIELD_LABELS = {
    "en": {
        "beneficiary_id": "Beneficiary ID",
        "visit_type": "Visit type",
        "weight_kg": "Weight in kilograms",
        "vaccinations_due": "Vaccinations due",
        "next_visit_date": "Next visit date",
        "temperature_c": "Temperature in Celsius",
        "bp_systolic": "Blood pressure systolic",
        "bp_diastolic": "Blood pressure diastolic",
    },
    "hi": {
        "beneficiary_id": "à¤²à¤¾à¤­à¤¾à¤°à¥à¤¥à¥€ à¤†à¤ˆà¤¡à¥€",
        "visit_type": "à¤µà¤¿à¤œà¤¼à¤¿à¤Ÿ à¤•à¤¾ à¤ªà¥à¤°à¤•à¤¾à¤°",
        "weight_kg": "à¤µà¤œà¤¼à¤¨ à¤•à¤¿à¤²à¥‹ à¤®à¥‡à¤‚",
        "vaccinations_due": "à¤¬à¤¾à¤•à¥€ à¤Ÿà¥€à¤•à¤¾à¤•à¤°à¤£",
        "next_visit_date": "à¤…à¤—à¤²à¥€ à¤µà¤¿à¤œà¤¼à¤¿à¤Ÿ à¤•à¥€ à¤¤à¤¾à¤°à¥€à¤–",
        "temperature_c": "à¤¤à¤¾à¤ªà¤®à¤¾à¤¨ à¤¸à¥‡à¤²à¥à¤¸à¤¿à¤¯à¤¸ à¤®à¥‡à¤‚",
        "bp_systolic": "à¤¬à¥à¤²à¤¡ à¤ªà¥à¤°à¥‡à¤¶à¤° à¤¸à¤¿à¤¸à¥à¤Ÿà¥‹à¤²à¤¿à¤•",
        "bp_diastolic": "à¤¬à¥à¤²à¤¡ à¤ªà¥à¤°à¥‡à¤¶à¤° à¤¡à¤¾à¤¯à¤¸à¥à¤Ÿà¥‹à¤²à¤¿à¤•",
    },
    "kn": {
        "beneficiary_id": "à²«à²²à²¾à²¨à³à²­à²µà²¿ à²à²¡à²¿",
        "visit_type": "à²­à³‡à²Ÿà²¿à²¯ à²µà²¿à²§",
        "weight_kg": "à²¤à³‚à²• à²•à³†à²œà²¿à²¯à²²à³à²²à²¿",
        "vaccinations_due": "à²¬à²¾à²•à²¿ à²‡à²°à³à²µ à²²à²¸à²¿à²•à³†à²—à²³à³",
        "next_visit_date": "à²®à³à²‚à²¦à²¿à²¨ à²­à³‡à²Ÿà²¿à²¯ à²¦à²¿à²¨à²¾à²‚à²•",
        "temperature_c": "à²¤à²¾à²ªà²®à²¾à²¨ à²¸à³†à²²à³à²¸à²¿à²¯à²¸à³â€Œà²¨à²²à³à²²à²¿",
        "bp_systolic": "à²°à²•à³à²¤à²¦à³Šà²¤à³à²¤à²¡ à²¸à²¿à²¸à³à²Ÿà³‹à²²à²¿à²•à³",
        "bp_diastolic": "à²°à²•à³à²¤à²¦à³Šà²¤à³à²¤à²¡ à²¡à²¯à²¾à¸³à³à²Ÿà³‹à²²à²¿à²•à³",
    },
}

YES_WORDS = {
    "en": {"yes", "yeah", "correct", "confirm", "okay", "ok"},
    "hi": {"à¤¹à¤¾à¤", "à¤¹à¤¾à¤‚", "à¤œà¥€", "à¤¸à¤¹à¥€", "à¤ à¥€à¤•", "à¤¹à¤¾à¤ à¤œà¥€"},
    "kn": {"à²¹à³Œà²¦à³", "à²¸à²°à²¿", "à²¹à³Œà²¦à²ªà³à²ª", "à²¹à³Œà²¦à³ à²¸à²°à³"},
}

NO_WORDS = {
    "en": {"no", "nope", "incorrect", "wrong"},
    "hi": {"à¤¨à¤¹à¥€à¤‚", "à¤¨à¤¹à¥€", "à¤—à¤²à¤¤", "à¤¨à¤¹à¥€à¤‚ à¤œà¥€"},
    "kn": {"à²‡à²²à³à²²", "à²¤à²ªà³à²ªà³", "à²¬à³‡à²¡"},
}


def normalize_confirmation(text: str, language: str) -> str | None:
    """Recognize simple yes/no confirmation."""

    language = language if language in SUPPORTED_LANGUAGES else "en"
    cleaned = text.strip().lower().rstrip(".,!?à¥¤")

    if cleaned in YES_WORDS[language]:
        return "yes"

    if cleaned in NO_WORDS[language]:
        return "no"

    return None


def _normalize_llm_result(raw: Any) -> LLMResult:
    if isinstance(raw, LLMResult):
        return raw
    return validate_llm_result(raw)


def _apply_patch(form: VisitForm, patch: dict) -> None:
    """Update only fields explicitly returned by the LLM."""

    for key, value in patch.items():
        if hasattr(form, key):
            setattr(form, key, value)


def _has_information(form: VisitForm) -> bool:
    return any(
        value is not None and value != []
        for value in asdict(form).values()
    )


def _build_readback(form: VisitForm, language: str) -> str:
    labels = FIELD_LABELS[language]
    details = []

    for key, value in asdict(form).items():
        if value is not None and value != []:
            if key == "beneficiary_id":
                spoken_value = " ".join(str(value))
            else:
                spoken_value = str(value)

            details.append(f"{labels[key]}: {spoken_value}")

    return "\n".join(details)


def _build_follow_ups(form: VisitForm) -> list[str]:
    """Use only information explicitly recorded in the visit form."""

    items = []

    if form.next_visit_date:
        items.append(f"Next visit: {form.next_visit_date}")

    for vaccination in form.vaccinations_due:
        items.append(f"Vaccination recorded as due: {vaccination}")

    return items


def extract_visit(
    text: str,
    state: str,
    form: VisitForm,
    today: str,
) -> LLMResult:
    """Validate an extraction result.

    The application supplies the actual LLM adapter through handle_turn.
    This function validates a supplied result when used independently.
    """

    return validate_llm_result(text)


def _check_danger(
    danger_fn,
    form: VisitForm,
    transcript: str,
    candidates: list[str],
) -> tuple[bool, list[str]]:
    """Run the injected Team D danger checker."""

    result = danger_fn(asdict(form), transcript, candidates)

    if isinstance(result, bool):
        return result, []

    if isinstance(result, (list, tuple, set)):
        ids = [item for item in result if isinstance(item, str)]
        return bool(ids), ids

    if isinstance(result, dict):
        flagged = bool(
            result.get("danger_flag", result.get("flagged", False))
        )
        ids = result.get("danger_ids", [])
        return flagged, ids if isinstance(ids, list) else []

    flagged = bool(getattr(result, "danger_flag", False))
    ids = getattr(result, "danger_ids", [])
    return flagged, ids if isinstance(ids, list) else []


def handle_turn(
    session: Session,
    text: str,
    llm_fn,
    danger_fn,
    save_fn=None,
) -> list[Say]:
    """Process one user turn; persist only after explicit user confirmation."""

    language = (
        session.language
        if session.language in SUPPORTED_LANGUAGES
        else "en"
    )
    messages = MESSAGES[language]
    text = (text or "").strip()

    if not session.disclosure_sent:
        session.disclosure_sent = True
        if not text:
            return [Say(messages["disclosure"], "disclosure")]
        replies = [Say(messages["disclosure"], "disclosure")]
    else:
        replies = []

    if not text:
        replies.append(Say(messages["empty"], "prompt"))
        return replies

    session.turn_id += 1
    session.last_transcript = text

    if session.state == "SAVED":
        return replies + [Say(messages["saved"], "saved")]

    # Keep the complete spoken conversation for the saved record.
    session.transcript_history.append(text)

    # Danger checking runs before ordinary extraction.
    try:
        danger_flag, danger_ids = _check_danger(
            danger_fn, session.form, text, []
        )
    except Exception:
        # Fail closed if safety checking fails.
        session.danger_flag = True
        session.state = "LISTENING"
        return replies + [Say(messages["referral"], "referral")]

    if danger_flag:
        session.danger_flag = True
        session.follow_ups = []
        session.state = "LISTENING"
        return replies + [Say(messages["referral"], "referral")]

    if session.danger_flag:
        return replies + [Say(messages["referral"], "referral")]

    # Only explicit spoken yes/no can confirm or reject.
    confirmation = normalize_confirmation(text, language)

    if session.state == "CONFIRMING":
        if confirmation == "yes":

            # Prevent repeated saves in the same session.
            if session.record_id is not None:
                session.state = "SAVED"
                return replies + [Say(messages["yes"], "saved")]

            # The application must inject Team D's database function.
            if save_fn is None:
                return replies + [
                    Say(
                        "The visit could not be saved. Please try again.",
                        "error",
                    )
                ]

            try:
                transcript = "\n".join(session.transcript_history)
                form_data = asdict(session.form)

                # Calls Team D's save_record(transcript, form).
                saved_id = save_fn(transcript, form_data)

                if saved_id is None:
                    raise RuntimeError(
                        "Database did not return a record ID"
                    )

                session.record_id = int(saved_id)

            except Exception:
                # Remain in CONFIRMING so the user can retry.
                return replies + [
                    Say(
                        "The visit could not be saved. Please try again.",
                        "error",
                    )
                ]

            # Mark as saved only after the database confirms success.
            session.state = "SAVED"
            session.follow_ups = _build_follow_ups(session.form)

            return replies + [
                Say(messages["yes"], "saved")
            ]

        if confirmation == "no":
            session.state = "LISTENING"
            return replies + [
                Say(messages["no"], "prompt")
            ]

    try:
        raw = llm_fn(
            text,
            session.state,
            session.form,
            date.today().isoformat(),
        )
        result = _normalize_llm_result(raw)

    except Exception:
        return replies + [
            Say(messages["retry"], "prompt")
        ]

    # Team D owns the approved danger-ID allowlist.
    if result.danger_candidates:
        try:
            candidate_flag, candidate_ids = _check_danger(
                danger_fn,
                session.form,
                text,
                result.danger_candidates,
            )

        except Exception:
            session.danger_flag = True
            return replies + [
                Say(messages["referral"], "referral")
            ]

        if candidate_flag:
            session.danger_flag = True
            session.follow_ups = []
            return replies + [
                Say(messages["referral"], "referral")
            ]

    # Confirmation is accepted only from explicit spoken yes/no above.
    if result.intent in ("correction", "provide_info"):
        _apply_patch(session.form, result.patch)

    if not _has_information(session.form):
        return replies + [
            Say(messages["empty"], "prompt")
        ]

    readback = _build_readback(session.form, language)

    session.state = "CONFIRMING"
    session.follow_ups = _build_follow_ups(session.form)

    return replies + [
        Say(readback, "readback"),
        Say(messages["confirm"], "prompt"),
    ]