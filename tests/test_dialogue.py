from backend.dialogue import create_session


def test_session_starts_in_listening_state():
    session = create_session(language="en")
    assert session["state"] == "LISTENING"


def test_session_uses_selected_language():
    session = create_session(language="hi")
    assert session["language"] == "hi"


def test_session_fields_start_empty():
    session = create_session(language="en")
    assert isinstance(session["form"], dict)
    assert len(session["form"]) == 7
    assert all(value == "" for value in session["form"].values())



def test_extract_visit_date_without_gemini():
    from backend.llm import extract_visit

    result = extract_visit("The visit date is 21 November 2026.")
    assert result["form"]["visit_date"] == "2026-11-21"
