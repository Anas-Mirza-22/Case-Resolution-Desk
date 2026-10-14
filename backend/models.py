"""Pydantic v2 request/response models and validation."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class CaseCreateRequest(BaseModel):
    """Request body for POST /api/cases."""

    model_config = ConfigDict(extra="forbid")

    learner_name: str = Field(..., min_length=1, max_length=120)
    question: str = Field(..., min_length=1, max_length=2000)
    assessed_on: date = Field(default=C.DEFAULT_ASSESSED_ON)

    # Numeric facts (None == unknown; never coerced to 0).
    attendance_pct: float | None = Field(default=None)
    live_sessions: int | None = Field(default=None)
    capstone_score: float | None = Field(default=None)

    submission_state: SubmissionState = SubmissionState.UNKNOWN
    extension_state: ExtensionState = ExtensionState.UNKNOWN
    extension_requested_at: datetime | None = None

    medical_note: MedicalNoteState = MedicalNoteState.NONE
    makeup_state: MakeupState = MakeupState.NONE
    missed_session_date: date | None = None

    learner_notes: str = Field(default="", max_length=4000)

    @field_validator("learner_name", "question")
    @classmethod
    def _strip_required(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("attendance_pct")
    @classmethod
    def _attendance_range(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if not (C.ATTENDANCE_MIN <= v <= C.ATTENDANCE_MAX):
            raise ValueError(
                f"attendance_pct must be between {C.ATTENDANCE_MIN:g} and {C.ATTENDANCE_MAX:g}"
            )
        return v

    @field_validator("capstone_score")
    @classmethod
    def _score_range(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if not (C.CAPSTONE_MIN <= v <= C.CAPSTONE_MAX):
            raise ValueError(
                f"capstone_score must be between {C.CAPSTONE_MIN:g} and {C.CAPSTONE_MAX:g}"
            )
        return v

    @field_validator("live_sessions")
    @classmethod
    def _sessions_non_negative(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v < 0:
            raise ValueError("live_sessions must be >= 0")
        return v

    @field_validator("extension_requested_at")
    @classmethod
    def _tz_aware(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        if v.tzinfo is None:
            raise ValueError("extension_requested_at must include a timezone offset")
        return v


class Citation(BaseModel):
    doc_id: str
    version: str
    section: str = ""
    superseded: bool = False


class RequirementResult(BaseModel):
    name: str
    met: bool | None  # None == unknown / not yet determinable
    detail: str


class ExtensionOutcome(BaseModel):
    state: str
    timely: bool | None
    due_date: datetime
    detail: str


class CaseOutcome(BaseModel):
    eligibility: Eligibility
    submission_hold: SubmissionHold
    requirement_results: list[RequirementResult]
    extension: ExtensionOutcome
    due_date: datetime


class CaseResponse(BaseModel):
    id: int
    inputs: CaseCreateRequest
    outcome: CaseOutcome
    status: CaseStatus
    next_action: str
    other_actions: list[str]
    missing_facts: list[str]
    answer: str | None
    citations: list[Citation]
    case_note: str
    llm_error: str | None
    created_at: datetime


class CaseListItem(BaseModel):
    id: int
    learner_name: str
    eligibility: Eligibility
    status: CaseStatus
    created_at: datetime


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
    llm_configured: bool
    policies_loaded: int
    detail: dict[str, Any] = Field(default_factory=dict)