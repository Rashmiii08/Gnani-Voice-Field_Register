import json
import argparse
from pathlib import Path


def normalize(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    if isinstance(value, list):
        return [normalize(item) for item in value]

    if isinstance(value, str):
        return " ".join(value.lower().strip().split())

    return value


def score_clip(expected, actual):
    total = len(expected)

    if total == 0:
        return 100.0, []

    correct = 0
    errors = []

    for field, expected_value in expected.items():
        actual_value = actual.get(field)

        if normalize(actual_value) == normalize(expected_value):
            correct += 1
        else:
            errors.append({
                "field": field,
                "expected": expected_value,
                "actual": actual_value
            })

    return round((correct / total) * 100, 2), errors


def main():
    parser = argparse.ArgumentParser(
        description="Score synthetic Gnani voice field-register test cases."
    )

    parser.add_argument(
        "--expected",
        default="assets/expected_cases.json"
    )

    parser.add_argument(
        "--actual",
        required=True,
        help="Path to JSON file containing actual extracted results."
    )

    args = parser.parse_args()

    expected_path = Path(args.expected)
    actual_path = Path(args.actual)

    if not expected_path.exists() or not actual_path.exists():
        raise SystemExit("Error: Input JSON file not found.")

    expected_data = json.loads(
        expected_path.read_text(encoding="utf-8-sig")
    )

    actual_data = json.loads(
        actual_path.read_text(encoding="utf-8-sig")
    )

    actual_by_id = {
        case["id"]: case
        for case in actual_data
        if isinstance(case, dict) and "id" in case
    }

    total_score = 0
    count = len(expected_data)

    for expected_case in expected_data:
        case_id = expected_case["id"]
        actual_case = actual_by_id.get(case_id)

        if actual_case is None:
            print(f"\nCase: {case_id}")
            print("Score: 0% (Missing actual result)")
            continue

        score, errors = score_clip(
            expected_case["expected"],
            actual_case.get("actual", {})
        )

        total_score += score

        print(f"\nCase: {case_id}")
        print(f"Score: {score}%")

        for error in errors:
            print(
                f"  Mismatch - {error['field']}: "
                f"expected={error['expected']}, "
                f"actual={error['actual']}"
            )

    if count:
        print("\n------------------------------")
        print(f"Overall score: {round(total_score / count, 2)}%")
        print("------------------------------")
    else:
        print("No expected test cases found.")


if __name__ == "__main__":
    main()