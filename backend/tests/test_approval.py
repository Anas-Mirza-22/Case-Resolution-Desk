"""Approval/unknown-value tests: no guessing, request != approval, secret hold."""
from datetime import date, datetime

from backend.constants import (
    CAPSTONE_DEADLINE,
    EXTENSION_DEADLINE,
    PKT,
    Eligibility,
    ExtensionState,
    SubmissionHold,
    SubmissionState,
)
from backend.rules import RuleInputs, evaluate


def _inputs(**overrides):
    base = dict(
        assessed_on=date(2026, 10, 7),
        attendance_pct=None,
        live_sessions=None,
        capstone_score=None,
        submission_state=SubmissionState.UNKNOWN,
        extension_state=ExtensionState.UNKNOWN,
        extension_requested_at=None,
        medical_note="none",
        makeup_state="none",
        missed_session_date=None,
    )
    base.update(overrides)
    return RuleInputs(**base)


def test_unknown_values_are_pending_not_zero():
    result = evaluate(_inputs())
    assert result.eligibility == Eligibility.PENDING
    assert "attendance percentage" in result.missing_facts
    assert "live-session count" in result.missing_facts


def test_extension_request_is_not_approval():
    """A timely request keeps the standard due date until the mentor approves."""
    result = evaluate(
        _inputs(
            attendance_pct=80.0,
            live_sessions=3,
            capstone_score=70.0,
            submission_state=SubmissionState.SAFE,
            extension_state=ExtensionState.REQUESTED_PENDING,
            extension_requested_at=datetime(2026, 10, 7, 11, 0, tzinfo=PKT),
        )
    )
    assert result.extension.due_date == CAPSTONE_DEADLINE
    assert result.extension.timely is True
    assert result.status.value == "Waiting for Mentor"


def test_extension_request_with_naive_timestamp_is_indeterminate():
    """A naive timestamp must not be assumed timely; the standard due date stays."""
    result = evaluate(
        _inputs(
            attendance_pct=80.0,
            live_sessions=3,
            capstone_score=70.0,
            submission_state=SubmissionState.SAFE,
            extension_state=ExtensionState.REQUESTED_PENDING,
            extension_requested_at=datetime(2026, 10, 7, 11, 0),  # naive
        )
    )
    assert result.extension.timely is None
    assert result.extension.due_date == CAPSTONE_DEADLINE
    assert "timestamp is missing or timezone-naive" in result.extension.detail


def test_approved_extension_ends_monday():
    result = evaluate(
        _inputs(
            attendance_pct=80.0,
            live_sessions=3,
            capstone_score=70.0,
            submission_state=SubmissionState.SAFE,
            extension_state=ExtensionState.APPROVED,
        )
    )
    assert result.extension.due_date == EXTENSION_DEADLINE
    assert result.extension.due_date.weekday() == 0  # Monday


def test_secret_hold_blocks_pass():
    result = evaluate(
        _inputs(
            attendance_pct=82.0,
            live_sessions=3,
            capstone_score=78.0,
            submission_state=SubmissionState.SECRET_FOUND,
        )
    )
    assert result.submission_hold == SubmissionHold.SECRET_FOUND
    assert result.eligibility == Eligibility.INELIGIBLE