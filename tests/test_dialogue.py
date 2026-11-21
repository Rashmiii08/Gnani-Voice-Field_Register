
import unittest

from backend.dialogue import Session, handle_turn


def fake_llm(text, state, form, today):
    if "correct" in text.lower():
        return {
            "intent": "correction",
            "patch": {"weight_kg": 56},
            "danger_candidates": []
        }

    return {
        "intent": "provide_info",
        "patch": {
            "beneficiary_id": "BEN001",
            "visit_type": "antenatal",
            "weight_kg": 55,
            "next_visit_date": "2026-11-28"
        },
        "danger_candidates": []
    }


def safe_danger_check(form, transcript, candidates):
    return False


def danger_detected(form, transcript, candidates):
    return True


class TestDialogue(unittest.TestCase):

    def test_information_creates_confirmation(self):
        session = Session(session_id="TEST001", language="en")

        replies = handle_turn(
            session, "Start visit", fake_llm, safe_danger_check
        )

        self.assertEqual(session.state, "CONFIRMING")
        self.assertTrue(any(reply.kind == "readback" for reply in replies))

    def test_correction_updates_weight(self):
        session = Session(
            session_id="TEST002",
            language="en",
            state="CONFIRMING"
        )
        session.form.weight_kg = 55

        replies = handle_turn(
            session, "correct the weight", fake_llm, safe_danger_check
        )

        self.assertEqual(session.form.weight_kg, 56)
        self.assertEqual(session.state, "CONFIRMING")

    def test_yes_confirms_and_saves_record(self):
        session = Session(
            session_id="TEST003",
            language="en",
            state="CONFIRMING"
        )

        saved_records = []

        def fake_save(transcript, form):
            saved_records.append({
                "transcript": transcript,
                "form": form
            })
            return 101

        replies = handle_turn(
            session,
            "yes",
            fake_llm,
            safe_danger_check,
            save_fn=fake_save
        )

        self.assertEqual(session.state, "SAVED")
        self.assertEqual(session.record_id, 101)
        self.assertEqual(len(saved_records), 1)
        self.assertIn("yes", saved_records[0]["transcript"].lower())
        self.assertIsNone(saved_records[0]["form"]["beneficiary_id"])

    def test_yes_without_save_function_does_not_mark_saved(self):
        session = Session(
            session_id="TEST005",
            language="en",
            state="CONFIRMING"
        )

        replies = handle_turn(
            session, "yes", fake_llm, safe_danger_check
        )

        self.assertEqual(session.state, "CONFIRMING")
        self.assertIsNone(session.record_id)

    def test_danger_flag_blocks_normal_flow(self):
        session = Session(session_id="TEST004", language="en")

        replies = handle_turn(
            session, "Test danger", fake_llm, danger_detected
        )

        self.assertTrue(session.danger_flag)
        self.assertTrue(any(reply.kind == "referral" for reply in replies))


if __name__ == "__main__":
    unittest.main()
