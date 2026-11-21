from backend.danger import check_danger


def test_empty_visit_has_no_danger_flags():
    result = check_danger(form={}, transcript_text="")
    assert result == []


def test_severe_pain_is_flagged():
    result = check_danger(
        form={},
        transcript_text="The person has severe pain"
    )
    assert "urgent" in result


def test_emergency_keyword_is_flagged():
    result = check_danger(
        form={},
        transcript_text="This is a medical emergency"
    )
    assert "emergency" in result


def test_normal_visit_does_not_crash():
    result = check_danger(
        form={"main_concern": "routine checkup"},
        transcript_text="I need a routine checkup"
    )
    assert result == []
