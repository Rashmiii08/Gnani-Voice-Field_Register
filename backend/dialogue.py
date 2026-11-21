from backend.llm import extract_visit, VISIT_FIELDS
from backend.danger import check_danger
from backend.phrases import get_referral_phrase
from backend.db import save_confirmed_visit

REQUIRED_FIELDS = VISIT_FIELDS

QUESTIONS = {
    "visit_date": {
        "en": "What is the visit date?",
        "hi": "????? ?? ????? ???? ???",
    },
    "village": {
        "en": "Which village is this visit in?",
        "hi": "?? ????? ??? ???? ??? ???",
    },
    "household_id": {
        "en": "What is the household ID?",
        "hi": "?????? ?? ???? ???? ???",
    },
    "person_name": {
        "en": "What is the person's name?",
        "hi": "??????? ?? ??? ???? ???",
    },
    "age": {
        "en": "What is the person's age?",
        "hi": "??????? ?? ???? ???? ???",
    },
    "main_concern": {
        "en": "What is the main concern reported?",
        "hi": "????? ?????? ???? ???? ?? ???",
    },
    "notes": {
        "en": "Are there any additional notes? If not, say no additional notes.",
        "hi": "???? ??? ???????? ??????? ??? ??? ????, ?? ???? ?? ??? ???????? ??????? ???? ???",
    },
}


def create_session(language="en"):
    return {
        "language": language if language in ("en", "hi") else "en",
        "state": "LISTENING",
        "form": {field: "" for field in VISIT_FIELDS},
        "transcript": [],
        "confirmed": False,
        "saved_id": None,
        "danger_flags": [],
    }


def handle_turn(session, text, llm_fn=None, danger_fn=None):
    if not isinstance(session, dict):
        raise ValueError("Invalid session.")

    text = str(text or "").strip()
    language = session.get("language", "en")

    if not text:
        return [{"type": "say", "text": "Please speak or enter your response."}]

    session.setdefault("transcript", []).append(text)

    if session.get("state") == "AWAITING_CONFIRMATION":
        answer = " ".join(text.casefold().replace(",", " ").replace(".", " ").replace("!", " ").replace("?", " ").split())

        if answer in ("yes", "yes i confirm", "i confirm", "???", "???", "??", "??? ??"):
            session["confirmed"] = True
            session["state"] = "CONFIRMED"

            try:
                record_id = save_confirmed_visit(
                    session,
                    "\n".join(session.get("transcript", [])),
                )
                session["saved_id"] = record_id
                return [{
                    "type": "say",
                    "text": "The confirmed visit has been saved."
                    if language == "en"
                    else "?????? ?? ?? ??????? ???????? ?? ?? ?? ???",
                }]
            except Exception:
                session["confirmed"] = False
                session["state"] = "AWAITING_CONFIRMATION"
                return [{
                    "type": "say",
                    "text": "I could not save the visit. Please check the secure database settings."
                    if language == "en"
                    else "??????? ???????? ???? ?? ???? ????? ??????? ?????? ???????",
                }]

        if answer in ("no", "no i don't", "????", "??? ??"):
            session["state"] = "LISTENING"
            session["confirmed"] = False
            return [{
                "type": "say",
                "text": "Okay. Please tell me what needs to be corrected."
                if language == "en"
                else "??? ??? ????? ????? ?? ???? ??????? ???",
            }]

        return [{
            "type": "say",
            "text": "Please answer yes to confirm or no to make corrections."
            if language == "en"
            else "?????? ?? ??? ??? ?? ????? ?? ??? ???? ?????",
        }]

    if session.get("state") == "CONFIRMED":
        return [{
            "type": "say",
            "text": "This visit is already saved. Start a new visit for another record."
            if language == "en"
            else "?? ??????? ???? ?? ???????? ??? ?? ??????? ?? ??? ?? ????? ???? ?????",
        }]

    extractor = llm_fn or extract_visit
    result = extractor(
        text,
        state=session.get("state"),
        form=session.get("form", {}),
    )

    if not isinstance(result, dict):
        result = {"form": session.get("form", {})}

    session["form"] = result.get("form", session.get("form", {}))

    detector = danger_fn or check_danger
    flags = detector(session["form"], text, None)
    session["danger_flags"] = flags

    referral = None
    if "emergency" in flags:
        referral = get_referral_phrase(language, "emergency")
    elif "urgent" in flags:
        referral = get_referral_phrase(language, "urgent")

    missing = [
        field for field in REQUIRED_FIELDS
        if not session["form"].get(field)
    ]

    if missing:
        session["state"] = "LISTENING"
        messages = []

        if referral:
            messages.append({"type": "say", "text": referral})

        field = missing[0]
        messages.append({
            "type": "say",
            "text": QUESTIONS[field][language],
        })
        return messages

    session["state"] = "AWAITING_CONFIRMATION"

    summary = "\n".join(
        f"{field.replace('_', ' ')}: {value or 'Not provided'}"
        for field, value in session["form"].items()
    )

    messages = []
    if referral:
        messages.append({"type": "say", "text": referral})

    messages.append({
        "type": "say",
        "text": (
            "Please review these details:\n" + summary
            + "\nDo you confirm? Please say yes or no."
            if language == "en"
            else "????? ??????? ??????:\n" + summary
            + "\n???? ?? ???? ?????? ???? ???? ????? ??? ?? ???? ?????"
        ),
    })

    return messages

