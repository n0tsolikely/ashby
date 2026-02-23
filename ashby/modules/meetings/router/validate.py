from __future__ import annotations

from typing import List

from ashby.modules.meetings.mode_registry import validate_mode
from ashby.modules.meetings.retention_registry import validate_retention
from ashby.modules.meetings.template_registry import validate_template
from ashby.modules.meetings.schemas.plan import UIState, ValidationIssue, ValidationResult


def validate_ui(ui: UIState) -> ValidationResult:
    issues: List[ValidationIssue] = []

    if ui.mode is not None:
        mv = validate_mode(ui.mode)
        if not mv.ok:
            issues.append(ValidationIssue(code="invalid_mode", message=mv.message or "Invalid mode.", field="mode"))

    if ui.template is not None:
        if ui.mode is None:
            issues.append(
                ValidationIssue(
                    code="template_requires_mode",
                    message="Template validation requires a mode to be selected.",
                    field="template",
                )
            )
        else:
            tv = validate_template(ui.mode, ui.template)
            if not tv.ok:
                issues.append(
                    ValidationIssue(code="invalid_template", message=tv.message or "Invalid template.", field="template")
                )

    if ui.retention is not None:
        rv = validate_retention(ui.retention)
        if not rv.ok:
            issues.append(
                ValidationIssue(
                    code="invalid_retention",
                    message=rv.message or "Invalid retention.",
                    field="retention",
                )
            )

    if ui.speakers is not None:
        s = ui.speakers
        if isinstance(s, int):
            if s <= 0:
                issues.append(
                    ValidationIssue(
                        code="invalid_speakers",
                        message="Speakers must be a positive integer.",
                        field="speakers",
                    )
                )
        elif isinstance(s, str):
            if s.strip().lower() != "auto":
                issues.append(
                    ValidationIssue(
                        code="invalid_speakers",
                        message="Speakers must be a positive int or 'auto'.",
                        field="speakers",
                    )
                )
        else:
            issues.append(
                ValidationIssue(
                    code="invalid_speakers",
                    message="Speakers must be a positive int or 'auto'.",
                    field="speakers",
                )
            )

    if ui.transcript_version_id is not None:
        tv = ui.transcript_version_id
        if not isinstance(tv, str) or not tv.strip():
            issues.append(
                ValidationIssue(
                    code="invalid_transcript_version_id",
                    message="transcript_version_id must be a non-empty string when provided.",
                    field="transcript_version_id",
                )
            )

    return ValidationResult(ok=(len(issues) == 0), issues=issues)
