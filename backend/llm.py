
"""LLM response validation for Gnani Voice Field Register.

This module validates structured extraction results.
It does not connect to or invent any external AI endpoint.
"""

from dataclasses import dataclass, field
from datetime import date
import json
from typing import Any


ALLOWED_INTENTS = {
    "provide_info",
    "correction",
    "confirm_yes",
    "confirm_no",
    "other",
}

ALLOWED_VISIT_TYPES = {
    "antenatal",
    "postnatal",
    "newborn",
    "immunisation",
    "other",
}

ALLOWED_FORM_FIELDS = {
    "beneficiary_id",
    "visit_type",
    "weight_kg",
    "vaccinations_due",
    "next_visit_date",
    "temperature_c",
    "bp_systolic",
    "bp_diastolic",
}


@dataclass
class LLMResult:
    """Validated result returned by the extraction layer."""

    intent: str = "other"
    patch: dict[str, Any] = field(default_factory=dict)
    danger_candidates: list[str] = field(default_factory=list)


class LLMValidationError(ValueError):
    """Raised when an AI response is invalid or unsafe to use."""


def _parse_response(raw: Any) -> dict:
    """Convert a JSON string or dictionary into a dictionary."""

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMValidationError("AI returned invalid JSON.") from exc

    if not isinstance(raw, dict):
        raise LLMValidationError("AI response must be a JSON object.")

    return raw


def _validate_patch(patch: Any) -> dict[str, Any]:
    """Validate extracted form fields without inventing missing values."""

    if not isinstance(patch, dict):
        raise LLMValidationError("Patch must be a JSON object.")

    unknown_fields = set(patch) - ALLOWED_FORM_FIELDS
    if unknown_fields:
        raise LLMValidationError(
            f"Unknown form fields: {', '.join(sorted(unknown_fields))}"
        )

    cleaned = {}

    for key, value in patch.items():

        if key == "beneficiary_id":
            if value is not None and not isinstance(value, str):
                raise LLMValidationError("beneficiary_id must be text or null.")

        elif key == "visit_type":
            if value is not None and value not in ALLOWED_VISIT_TYPES:
                raise LLMValidationError("Invalid visit_type.")

        elif key in {"weight_kg", "temperature_c"}:
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise LLMValidationError(f"{key} must be a number or null.")

        elif key in {"bp_systolic", "bp_diastolic"}:
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise LLMValidationError(f"{key} must be an integer or null.")

        elif key == "vaccinations_due":
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise LLMValidationError(
                    "vaccinations_due must be a list of text values."
                )

        elif key == "next_visit_date":
            if value is not None:
                if not isinstance(value, str):
                    raise LLMValidationError(
                        "next_visit_date must be text or null."
                    )
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise LLMValidationError(
                        "next_visit_date must use YYYY-MM-DD format."
                    ) from exc

        cleaned[key] = value

    return cleaned


def validate_llm_result(raw: Any) -> LLMResult:
    """Validate an untrusted LLM response against the shared contract."""

    data = _parse_response(raw)

    intent = data.get("intent", "other")
    if intent not in ALLOWED_INTENTS:
        raise LLMValidationError("Unknown intent.")

    patch = _validate_patch(data.get("patch", {}))

    danger_candidates = data.get("danger_candidates", [])
    if not isinstance(danger_candidates, list) or not all(
        isinstance(item, str) for item in danger_candidates
    ):
        raise LLMValidationError("danger_candidates must be a list of strings.")

    return LLMResult(
        intent=intent,
        patch=patch,
        danger_candidates=danger_candidates,
    )
