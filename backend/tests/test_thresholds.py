"""Threshold tests: 79.9 vs 80 attendance, 69 vs 70 score, sessions 2 vs 3."""
from datetime import date

from backend.constants import Eligibility, SubmissionState
from backend.rules import RuleInputs, evaluate


def _inputs(**overrides):
    base = dict(
        assessed_on=date(2026, 10, 7),
        attendance_pct=80.0,
        live_sessions=3,
        capstone_score=70.0,
        submission_state=SubmissionState.SAFE,
        extension_state="not_requested",
        extension_requested_at=None,
        medical_note="none",
        makeup_state="none",
        missed_session_date=None,
    )
    base.update(overrides)
    return RuleInputs(**base)


def test_attendance_no_rounding():
    assert evaluate(_inputs(attendance_pct=79.9)).eligibility == Eligibility.INELIGIBLE
    assert evaluate(_inputs(attendance_pct=80.0)).eligibility == Eligibility.ELIGIBLE


def test_capstone_threshold():
    assert evaluate(_inputs(capstone_score=69.0)).eligibility == Eligibility.INELIGIBLE
    assert evaluate(_inputs(capstone_score=70.0)).eligibility == Eligibility.ELIGIBLE


def test_live_sessions_threshold():
    assert evaluate(_inputs(live_sessions=2)).eligibility == Eligibility.INELIGIBLE
    assert evaluate(_inputs(live_sessions=3)).eligibility == Eligibility.ELIGIBLE