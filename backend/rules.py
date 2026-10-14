"""Pure business rules. No I/O, no clock calls, no LLM, no DB.

All functions take explicit inputs and return structured results so the
behaviour is deterministic and unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from . import constants as C
from .constants import (
    CaseStatus,
    Eligibility,
    ExtensionState,
    MakeupState,
    MedicalNoteState,
    SubmissionHold,
    SubmissionState,
)


@dataclass(frozen=True)
class RuleInputs:
    assessed_on: date
    attendance_pct: float | None
    live_sessions: int | None
    capstone_score: float | None
    submission_state: SubmissionState
    extension_state: ExtensionState
    extension_requested_at: datetime | None
    medical_note: MedicalNoteState
    makeup_state: MakeupState
    missed_session_date: date | None


@dataclass(frozen=True)
class RequirementCheck:
    name: str
    met: bool | None
    detail: str


@dataclass(frozen=True)
class ExtensionCheck:
    state: str
    timely: bool | None
    due_date: datetime
    detail: str


@dataclass(frozen=True)
class RuleResult:
    eligibility: Eligibility
    submission_hold: SubmissionHold
    requirements: list[RequirementCheck]
    extension: ExtensionCheck
    status: CaseStatus
    next_action: str
    other_actions: list[str]
    missing_facts: list[str]


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------

def check_attendance(attendance_pct: float | None) -> RequirementCheck:
    """KB-01: attendance >= 80, no rounding up."""
    if attendance_pct is None:
        return RequirementCheck(
            "attendance", None, "Attendance percentage is unknown."
        )
    met = attendance_pct >= C.MIN_ATTENDANCE_PCT
    detail = (
        f"Recorded attendance {attendance_pct:g}% "
        f"{'meets' if met else 'is below'} the 80% threshold."
    )
    return RequirementCheck("attendance", met, detail)


def check_live_sessions(live_sessions: int | None) -> RequirementCheck:
    """KB-01: at least 3 completed live sessions."""
    if live_sessions is None:
        return RequirementCheck(
            "live_sessions", None, "Live-session count is unknown."
        )
    met = live_sessions >= C.MIN_LIVE_SESSIONS
    detail = (
        f"{live_sessions} completed live session(s) "
        f"{'meet' if met else 'are below'} the minimum of 3."
    )
    return RequirementCheck("live_sessions", met, detail)


def check_capstone(capstone_score: float | None) -> RequirementCheck:
    """KB-02 v3: capstone score >= 70."""
    if capstone_score is None:
        return RequirementCheck(
            "capstone", None, "Capstone score is unknown; certification remains pending."
        )
    met = capstone_score >= C.MIN_CAPSTONE_SCORE
    detail = (
        f"Capstone score {capstone_score:g} "
        f"{'meets' if met else 'is below'} the current pass threshold of 70/100 (KB-02 v3)."
    )
    return RequirementCheck("capstone", met, detail)


def check_submission(state: SubmissionState) -> tuple[SubmissionHold, RequirementCheck]:
    """KB-03: safe submission required; secrets put the package on hold."""
    if state == SubmissionState.SAFE:
        return SubmissionHold.NONE, RequirementCheck(
            "submission", True, "Submission is valid and safe to review."
        )
    if state == SubmissionState.SECRET_FOUND:
        return SubmissionHold.SECRET_FOUND, RequirementCheck(
            "submission",
            False,
            "A secret appears in the submission package; a pass decision cannot be issued.",
        )
    if state == SubmissionState.MISSING_README:
        return SubmissionHold.MISSING_README, RequirementCheck(
            "submission", False, "README with local setup steps is missing (KB-03)."
        )
    if state == SubmissionState.INACCESSIBLE_LINK:
        return SubmissionHold.INACCESSIBLE_LINK, RequirementCheck(
            "submission", False, "Repository link cannot be accessed (KB-03)."
        )
    if state == SubmissionState.UNOPENABLE_PACKAGE:
        return SubmissionHold.UNOPENABLE_PACKAGE, RequirementCheck(
            "submission", False, "The submitted package cannot be opened (KB-03)."
        )
    if state == SubmissionState.NOT_SUBMITTED:
        return SubmissionHold.NOT_SUBMITTED, RequirementCheck(
            "submission", None, "No submission has been provided yet."
        )
    return SubmissionHold.UNKNOWN, RequirementCheck(
        "submission", None, "Submission safety/validity is unknown."
    )


def check_extension(
    extension_state: ExtensionState,
    extension_requested_at: datetime | None,
) -> ExtensionCheck:
    """KB-02 v3: one-business-day extension requires timely request AND mentor approval.

    The request timestamp must be timezone-aware. A naive timestamp is treated
    the same as a missing one: timeliness cannot be confirmed, so the standard
    due date remains in force. Aware timestamps in any timezone are compared
    in PKT against the published deadline.
    """
    standard = C.CAPSTONE_DEADLINE
    approved = C.EXTENSION_DEADLINE

    if extension_state == ExtensionState.APPROVED:
        return ExtensionCheck(
            state=ExtensionState.APPROVED.value,
            timely=True,
            due_date=approved,
            detail=(
                "Extension approved by mentor; individual due date is now "
                "Monday, 12 Oct 2026 17:00 PKT."
            ),
        )
    if extension_state == ExtensionState.DENIED:
        return ExtensionCheck(
            state=ExtensionState.DENIED.value,
            timely=None,
            due_date=standard,
            detail="Extension was denied; standard due date remains Fri 9 Oct 2026 17:00 PKT.",
        )
    if extension_state == ExtensionState.REQUESTED_PENDING:
        timely: bool | None = None
        if (
            extension_requested_at is not None
            and extension_requested_at.tzinfo is not None
        ):
            # Normalize to PKT so any aware timestamp compares correctly.
            requested_pkt = extension_requested_at.astimezone(C.PKT)
            timely = requested_pkt < C.CAPSTONE_DEADLINE

        if timely is False:
            detail = (
                "Request was made at or after the published deadline; no automatic "
                "extension applies (KB-02 v3). Refer for human review without promising acceptance."
            )
        elif timely is True:
            detail = (
                "Extension was requested before the deadline but mentor approval is pending; "
                "standard due date Fri 9 Oct 2026 17:00 PKT remains in force."
            )
        else:
            detail = (
                "Extension request timestamp is missing or timezone-naive, so timeliness "
                "cannot be confirmed; standard due date remains in force until approval is recorded."
            )
        return ExtensionCheck(
            state=ExtensionState.REQUESTED_PENDING.value,
            timely=timely,
            due_date=standard,
            detail=detail,
        )
    if extension_state == ExtensionState.NOT_REQUESTED:
        return ExtensionCheck(
            state=ExtensionState.NOT_REQUESTED.value,
            timely=None,
            due_date=standard,
            detail="No extension requested; standard due date Fri 9 Oct 2026 17:00 PKT applies.",
        )
    return ExtensionCheck(
        state=ExtensionState.UNKNOWN.value,
        timely=None,
        due_date=standard,
        detail="Extension status is unknown; standard due date remains in force.",
    )


# --------------------------------------------------------------------------
# Aggregate evaluation
# --------------------------------------------------------------------------

def evaluate(inputs: RuleInputs) -> RuleResult:
    """Compute the full deterministic outcome, status, and next actions."""
    attendance = check_attendance(inputs.attendance_pct)
    sessions = check_live_sessions(inputs.live_sessions)
    capstone = check_capstone(inputs.capstone_score)
    hold, submission = check_submission(inputs.submission_state)
    extension = check_extension(inputs.extension_state, inputs.extension_requested_at)

    requirements = [attendance, sessions, capstone, submission]

    # --- Missing facts (unknowns only; never convert to 0). ---
    missing: list[str] = []
    if inputs.attendance_pct is None:
        missing.append("attendance percentage")
    if inputs.live_sessions is None:
        missing.append("live-session count")
    if inputs.capstone_score is None:
        missing.append("capstone score")
    if inputs.submission_state == SubmissionState.UNKNOWN:
        missing.append("submission safety/validity")
    if inputs.extension_state == ExtensionState.UNKNOWN:
        missing.append("extension status")
    if (
        inputs.extension_state == ExtensionState.REQUESTED_PENDING
        and inputs.extension_requested_at is None
    ):
        missing.append("extension request timestamp")

    # --- Eligibility precedence. ---
    if hold == SubmissionHold.SECRET_FOUND:
        eligibility = Eligibility.INELIGIBLE
    elif any(r.met is False for r in (attendance, sessions, capstone)):
        eligibility = Eligibility.INELIGIBLE
    elif hold not in (SubmissionHold.NONE,) and hold != SubmissionHold.SECRET_FOUND:
        # missing_readme / inaccessible_link / unopenable_package => pending
        eligibility = Eligibility.PENDING
    elif attendance.met and sessions.met and capstone.met and hold == SubmissionHold.NONE:
        eligibility = Eligibility.ELIGIBLE
    else:
        eligibility = Eligibility.PENDING

    # --- Status priority. ---
    mentor_blocker = (
        inputs.makeup_state in (MakeupState.REQUESTED_PENDING, MakeupState.APPROVED)
        and inputs.makeup_state != MakeupState.COMPLETED
    ) or (inputs.extension_state == ExtensionState.REQUESTED_PENDING)

    learner_blocker = bool(missing) or hold in (
        SubmissionHold.MISSING_README,
        SubmissionHold.INACCESSIBLE_LINK,
        SubmissionHold.UNOPENABLE_PACKAGE,
        SubmissionHold.SECRET_FOUND,
        SubmissionHold.NOT_SUBMITTED,
    ) or inputs.medical_note in (MedicalNoteState.OFFERED_UNVERIFIED,)

    if mentor_blocker:
        status = CaseStatus.WAITING_FOR_MENTOR
    elif learner_blocker:
        status = CaseStatus.WAITING_FOR_LEARNER
    elif eligibility == Eligibility.ELIGIBLE:
        status = CaseStatus.READY_FOR_REVIEW
    else:
        status = CaseStatus.OPEN

    # --- Next actions (primary + others, all blockers listed). ---
    primary, others = _next_actions(
        inputs, eligibility, hold, mentor_blocker, learner_blocker, missing, extension
    )

    return RuleResult(
        eligibility=eligibility,
        submission_hold=hold,
        requirements=requirements,
        extension=extension,
        status=status,
        next_action=primary,
        other_actions=others,
        missing_facts=missing,
    )


def _next_actions(
    inputs: RuleInputs,
    eligibility: Eligibility,
    hold: SubmissionHold,
    mentor_blocker: bool,
    learner_blocker: bool,
    missing: list[str],
    extension: ExtensionCheck,
) -> tuple[str, list[str]]:
    """Return the single primary next action plus a list of other actions."""
    others: list[str] = []
    primary = ""

    if hold == SubmissionHold.SECRET_FOUND:
        primary = (
            "Ask the learner to revoke/rotate the exposed key, remove it from the "
            "package (including repo history), and provide a clean replacement."
        )
    elif hold == SubmissionHold.MISSING_README:
        primary = "Ask the learner to provide a README with local setup steps."
    elif hold == SubmissionHold.INACCESSIBLE_LINK:
        primary = "Ask the learner for repository access or a ZIP."
    elif hold == SubmissionHold.UNOPENABLE_PACKAGE:
        primary = "Ask the learner for a corrected, openable package."
    elif hold == SubmissionHold.NOT_SUBMITTED:
        primary = "Ask the learner to submit the capstone package (ZIP or repo link + README)."
    elif mentor_blocker:
        if inputs.extension_state == ExtensionState.REQUESTED_PENDING:
            primary = (
                "Route the timely extension request to the mentor for a recorded decision; "
                "the standard due date remains in force until approval."
            )
        else:
            primary = "Route the makeup request to the mentor for a recorded decision."
    elif learner_blocker:
        if inputs.medical_note == MedicalNoteState.OFFERED_UNVERIFIED:
            primary = (
                "Ask the learner for a verifiable medical note and the missed-session date so "
                "the coordinator can verify evidence before correcting the attendance record."
            )
        elif inputs.attendance_pct is None or inputs.live_sessions is None:
            primary = "Ask the learner for the missing attendance record and live-session count."
        elif inputs.capstone_score is None:
            primary = "Ask the learner for the capstone score once it is available."
        else:
            primary = "Request the missing information listed in the case note."
    else:
        primary = (
            "Forward the case to a human reviewer; the assistant cannot issue a certificate."
        )

    # Other actions (all visible blockers).
    if mentor_blocker and not primary.startswith("Route the timely"):
        others.append("Route the makeup request to the mentor for a recorded decision.")
    if (
        inputs.medical_note == MedicalNoteState.OFFERED_UNVERIFIED
        and not primary.startswith("Ask the learner for a verifiable medical")
    ):
        others.append(
            "Verify the medical note; do not change the attendance record until verified."
        )
    if inputs.missed_session_date is None and inputs.makeup_state != MakeupState.NONE:
        others.append(
            "Request the missed-session date to confirm the 7-calendar-day makeup window."
        )
    if missing and not primary.startswith("Ask the learner for the missing"):
        others.append("Collect missing facts: " + ", ".join(missing) + ".")
    if (
        extension.state == ExtensionState.REQUESTED_PENDING.value
        and extension.timely is None
    ):
        others.append("Request the extension request timestamp (PKT) to confirm timeliness.")
    if hold != SubmissionHold.NONE and not primary.startswith("Ask the learner to"):
        others.append("Resolve submission hold: " + hold.value.replace("_", " ") + ".")

    return primary, others