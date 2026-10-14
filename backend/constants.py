"""Single source of truth for thresholds, enums, statuses, and paths."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

# --- Timezone: PKT is UTC+5 with no DST (fixed offset). ---
PKT = timezone(timedelta(hours=5))

# --- Default assessment date per task (2026-10-07). ---
DEFAULT_ASSESSED_ON: date = date(2026, 10, 7)

# --- Certificate thresholds (KB-01, KB-02). ---
MIN_ATTENDANCE_PCT: float = 80.0
MIN_LIVE_SESSIONS: int = 3
MIN_CAPSTONE_SCORE: float = 70.0

# --- Capstone deadline (KB-02 v3). ---
CAPSTONE_DEADLINE: datetime = datetime(2026, 10, 9, 17, 0, tzinfo=PKT)
# Approved one-business-day extension ends Mon 12 Oct 2026 17:00 PKT.
EXTENSION_DEADLINE: datetime = datetime(2026, 10, 12, 17, 0, tzinfo=PKT)

# --- Numeric input bounds (reject impossible numbers). ---
ATTENDANCE_MIN: float = 0.0
ATTENDANCE_MAX: float = 100.0
CAPSTONE_MIN: float = 0.0
CAPSTONE_MAX: float = 100.0

# --- Paths. ---
BASE_DIR: Path = Path(__file__).resolve().parent
DEFAULT_POLICIES_DIR: Path = BASE_DIR / "policies"
DEFAULT_DB_PATH: Path = BASE_DIR / "data" / "cases.db"

# --- Policy source IDs (metadata keys are parsed from file headers). ---
KB_ATTENDANCE = "KB-01"
KB_CAPSTONE = "KB-02"
KB_SUBMISSION = "KB-03"
KB_WORKFLOW = "KB-04"
KB_OLD_CAPSTONE = "KB-05"


class Eligibility(str, Enum):
    ELIGIBLE = "eligible"          # all requirements met AND submission safe
    INELIGIBLE = "ineligible"      # at least one confirmed unmet requirement
    PENDING = "pending"            # unknowns or awaiting decisions


class SubmissionHold(str, Enum):
    NONE = "none"
    SECRET_FOUND = "secret_found"
    MISSING_README = "missing_readme"
    INACCESSIBLE_LINK = "inaccessible_link"
    UNOPENABLE_PACKAGE = "unopenable_package"
    NOT_SUBMITTED = "not_submitted"
    UNKNOWN = "unknown"


class SubmissionState(str, Enum):
    UNKNOWN = "unknown"
    NOT_SUBMITTED = "not_submitted"
    SAFE = "safe"
    SECRET_FOUND = "secret_found"
    MISSING_README = "missing_readme"
    INACCESSIBLE_LINK = "inaccessible_link"
    UNOPENABLE_PACKAGE = "unopenable_package"


class ExtensionState(str, Enum):
    NOT_REQUESTED = "not_requested"
    REQUESTED_PENDING = "requested_pending"
    APPROVED = "approved"
    DENIED = "denied"
    UNKNOWN = "unknown"


class MedicalNoteState(str, Enum):
    NONE = "none"
    OFFERED_UNVERIFIED = "offered_unverified"
    VERIFIED = "verified"


class MakeupState(str, Enum):
    NONE = "none"
    REQUESTED_PENDING = "requested_pending"
    APPROVED = "approved"
    COMPLETED = "completed"


class CaseStatus(str, Enum):
    OPEN = "Open"
    WAITING_FOR_LEARNER = "Waiting for Learner"
    WAITING_FOR_MENTOR = "Waiting for Mentor"
    READY_FOR_REVIEW = "Ready for Review"
    CLOSED = "Closed"


# --- Secret-like redaction pattern (Groq keys and generic key shapes). ---
# Kept intentionally narrow so we do not over-redact normal prose.
SECRET_PATTERN = (
    r"(gsk_[A-Za-z0-9]{10,}"          # Groq keys
    r"|sk-[A-Za-z0-9]{16,}"            # generic sk- keys
    r"|AIza[0-9A-Za-z_\-]{20,})"       # Google-style keys
)