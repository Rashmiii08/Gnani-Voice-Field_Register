"""Team B dialogue and state machine for Gnani Voice Field Register."""

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any
from uuid import uuid4

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
    require_identity: bool = False
    visit_key: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class Say:
    text: str
    kind: str = "prompt"


SUPPORTED_LANGUAGES = {"en", "hi"}

MESSAGES = {'en': {'disclosure': 'I am an AI assistant. I will help record your visit information.',
        'confirm': 'Please confirm whether these visit details are correct. Say yes or no.',
        'yes': 'The visit has been saved.',
        'no': 'Okay. Please tell me what needs to be corrected.',
        'saved': 'This visit has already been confirmed.',
        'retry': 'I could not understand that information. Please repeat it.',
        'empty': 'Please provide the beneficiary visit details.',
        'referral': 'Please contact your nearest Primary Health Centre for assistance.',
        'correct': 'Please tell me which information needs correction.'},
 'hi': {'disclosure': 'मैं एक एआई सहायक हूँ।',
        'confirm': 'क्या ये विवरण सही हैं? सहेजने के लिए हाँ कहें, या सुधार के लिए नहीं कहें।',
        'yes': 'विज़िट सहेजी गई।',
        'no': 'कृपया बताएं कि क्या बदलना है।',
        'saved': 'यह विज़िट पहले ही सहेजी गई है।',
        'retry': 'यह जानकारी समझ में नहीं आई। कृपया दोहराएँ।',
        'empty': 'कृपया विज़िट का विवरण बताएं।',
        'referral': 'कृपया निकटतम प्राथमिक स्वास्थ्य केंद्र से संपर्क करें।',
        'correct': 'कृपया बताएं कि क्या बदलना है।'}}

FIELD_LABELS = {'en': {'beneficiary_id': 'Beneficiary ID',
        'visit_type': 'Visit type',
        'weight_kg': 'Weight in kilograms',
        'vaccinations_due': 'Vaccinations due',
        'next_visit_date': 'Next visit date',
        'temperature_c': 'Temperature in Celsius',
        'bp_systolic': 'Blood pressure systolic',
        'bp_diastolic': 'Blood pressure diastolic'},
 'hi': {'beneficiary_id': 'लाभार्थी आईडी',
        'visit_type': 'विज़िट का प्रकार',
        'weight_kg': 'वज़न किलोग्राम में',
        'vaccinations_due': 'बाकी टीके',
        'next_visit_date': 'अगली विज़िट की तारीख',
        'temperature_c': 'तापमान सेल्सियस में',
        'bp_systolic': 'सिस्टोलिक रक्तचाप',
        'bp_diastolic': 'डायस्टोलिक रक्तचाप'}}

YES_WORDS = {'en': {'confirm save', 'yes', 'yes save'}, 'hi': {'han', 'हाँ', 'हां', 'haan', 'yes'}}

NO_WORDS = {'en': {'nope', 'no', 'incorrect', 'wrong'}, 'hi': {'नही', 'nahin', 'नहीं', 'nahi', 'no'}}


def normalize_confirmation(text: str, language: str) -> str | None:
    """Recognize simple yes/no confirmation."""

    language = language if language in SUPPORTED_LANGUAGES else "en"
    cleaned = text.strip().lower().rstrip(".,!?।").strip()

    if cleaned in YES_WORDS[language]:
        return "yes"

    if cleaned in NO_WORDS[language]:
        return "no"

    return None


def _normalize_llm_result(raw: Any) -> LLMResult:
    if isinstance(raw, LLMResult):
        return raw
    return validate_llm_result(raw)


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


def _build_follow_ups(form: VisitForm, language: str) -> list[str]:
    """Use only information explicitly recorded in the visit form."""

    items = []

    if form.next_visit_date:
        label = "अगली विज़िट" if language == "hi" else "Next visit"
        items.append(f"{label}: {form.next_visit_date}")

    for vaccination in form.vaccinations_due:
        label = "बाकी टीका" if language == "hi" else "Vaccination recorded as due"
        items.append(f"{label}: {vaccination}")

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

    if session.state == "SAVED":
        return replies + [Say(messages["saved"], "saved")]

    # Keep the complete spoken conversation for the saved record.
    session.last_transcript = text
    if len(session.transcript_history) >= 32:
        session.transcript_history.pop(0)
    session.transcript_history.append(text[:4000])

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
                        "विज़िट सहेजी नहीं गई। कृपया दोबारा कोशिश करें।" if language == "hi"
                        else "The visit could not be saved. Please try again.",
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
                        "विज़िट सहेजी नहीं गई। कृपया दोबारा कोशिश करें।" if language == "hi"
                        else "The visit could not be saved. Please try again.",
                        "error",
                    )
                ]

            # Mark as saved only after the database confirms success.
            session.state = "SAVED"
            session.follow_ups = _build_follow_ups(session.form, language)
            session.last_transcript = ""
            session.transcript_history.clear()

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
        session.state = "LISTENING"
        return replies + [Say(messages["retry"], "prompt")]

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
        proposed = VisitForm(**{**asdict(session.form), **result.patch})
        if session.form.beneficiary_id and proposed.beneficiary_id != session.form.beneficiary_id:
            session.state = "LISTENING"
            return replies + [Say(
                "नई लाभार्थी आईडी के लिए नई विज़िट शुरू करें।" if language == "hi"
                else "Start a new visit for a different beneficiary ID."
            )]
        try:
            proposed_danger = _check_danger(danger_fn, proposed, text, [])[0]
        except Exception:
            proposed_danger = True
        if proposed_danger:
            session.danger_flag = True
            session.follow_ups = []
            session.state = "LISTENING"
            return replies + [Say(messages["referral"], "referral")]
        session.form = proposed

    if session.require_identity:
        if not session.form.beneficiary_id:
            return replies + [Say("कृपया डेमो लाभार्थी आईडी बताएं।" if language == "hi"
                                  else "Please say the synthetic beneficiary ID, such as Demo one two three.")]
        if not session.form.visit_type:
            return replies + [Say("कृपया विज़िट का प्रकार बताएं।" if language == "hi"
                                  else "Please say the visit type, such as routine visit.")]

    if not result.patch and session.require_identity:
        # Require a fresh readback after an unsupported correction.
        session.state = "LISTENING"
        return replies + [Say(messages["retry"], "prompt")]

    if not _has_information(session.form):
        return replies + [
            Say(messages["empty"], "prompt")
        ]

    readback = _build_readback(session.form, language)

    session.state = "CONFIRMING"
    session.follow_ups = _build_follow_ups(session.form, language)

    return replies + [
        Say(readback, "readback"),
        Say(messages["confirm"], "prompt"),
    ]