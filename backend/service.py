"""Orchestration: validate -> retrieve -> evaluate -> explain -> persist."""
from __future__ import annotations

import logging

from . import constants as C
from .config import Settings
from .db import Database
from .llm import explain, redact_secrets
from .models import (
    CaseCreateRequest,
    CaseOutcome,
    CaseResponse,
    Citation,
    ExtensionOutcome,
    RequirementResult,
)
from .retrieval import PolicyIndex, mandatory_sources, refers_to_old_policy
from .rules import RuleInputs, evaluate

logger = logging.getLogger(__name__)


class CaseService:
    def __init__(self, settings: Settings, db: Database, index: PolicyIndex) -> None:
        self.settings = settings
        self.db = db
        self.index = index

    def create_case(self, req: CaseCreateRequest) -> CaseResponse:
        inputs = RuleInputs(
            assessed_on=req.assessed_on,
            attendance_pct=req.attendance_pct,
            live_sessions=req.live_sessions,
            capstone_score=req.capstone_score,
            submission_state=req.submission_state,
            extension_state=req.extension_state,
            extension_requested_at=req.extension_requested_at,
            medical_note=req.medical_note,
            makeup_state=req.makeup_state,
            missed_session_date=req.missed_session_date,
        )
        result = evaluate(inputs)

        # --- Retrieval: version-aware, mandatory sources included. ---
        query = req.question
        notes = redact_secrets(req.learner_notes)
        include_old = refers_to_old_policy(query, notes)
        relevant = self.index.relevant(
            query=query,
            assessed_on=req.assessed_on,
            include_superseded=include_old,
            top_k=6,
        )
        mandatory = set(mandatory_sources(query, notes))
        selected = [c for c in relevant if c.doc_id in mandatory or not mandatory] or relevant
        # Always include at least one current source per mandatory doc if available.
        for doc_id in mandatory:
            if not any(c.doc_id == doc_id for c in selected):
                for c in self.index.chunks:
                    if (
                        c.doc_id == doc_id
                        and not c.superseded
                        and c.effective_date <= req.assessed_on
                    ):
                        selected.append(c)
                        break

        excerpts = [
            {
                "doc_id": c.doc_id,
                "version": c.version,
                "section": c.section,
                "text": c.text,
            }
            for c in selected
        ]

        outcome = CaseOutcome(
            eligibility=result.eligibility,
            submission_hold=result.submission_hold,
            requirement_results=[
                RequirementResult(name=r.name, met=r.met, detail=r.detail)
                for r in result.requirements
            ],
            extension=ExtensionOutcome(
                state=result.extension.state,
                timely=result.extension.timely,
                due_date=result.extension.due_date,
                detail=result.extension.detail,
            ),
            due_date=result.extension.due_date,
        )

        # --- LLM explanation (never changes the outcome). ---
        llm = explain(
            settings=self.settings,
            code_outcome={
                "eligibility": outcome.eligibility.value,
                "submission_hold": outcome.submission_hold.value,
                "requirements": [r.model_dump() for r in outcome.requirement_results],
                "extension": outcome.extension.model_dump(mode="json"),
                "status": result.status.value,
                "next_action": result.next_action,
            },
            excerpts=excerpts,
            question=req.question,
            notes=notes,
        )

        citations = [
            Citation(
                doc_id=c["doc_id"],
                version=c["version"],
                section=c["section"],
                superseded=True,
            )
            if "SUPERSEDED"
            in next(
                (
                    x.status
                    for x in self.index.chunks
                    if x.doc_id == c["doc_id"] and x.version == c["version"]
                ),
                "",
            ).upper()
            else Citation(
                doc_id=c["doc_id"],
                version=c["version"],
                section=c["section"],
            )
            for c in excerpts
        ]
        # De-duplicate citations by (doc_id, version).
        seen: set[tuple[str, str]] = set()
        deduped: list[Citation] = []
        for cit in citations:
            key = (cit.doc_id, cit.version)
            if key not in seen:
                seen.add(key)
                deduped.append(cit)

        case_note = _build_case_note(req, result, deduped)

        case_id = self.db.insert_case(
            assessed_on=req.assessed_on.isoformat(),
            learner_name=req.learner_name,
            question=req.question,
            inputs=req.model_dump(mode="json"),
            outcome=outcome.model_dump(mode="json"),
            eligibility=outcome.eligibility.value,
            status=result.status.value,
            next_action=result.next_action,
            other_actions=result.other_actions,
            missing_facts=result.missing_facts,
            answer=llm.answer,
            citations=[c.model_dump() for c in deduped],
            case_note=case_note,
            llm_error=llm.error,
        )

        return CaseResponse(
            id=case_id,
            inputs=req,
            outcome=outcome,
            status=result.status,
            next_action=result.next_action,
            other_actions=result.other_actions,
            missing_facts=result.missing_facts,
            answer=llm.answer,
            citations=deduped,
            case_note=case_note,
            llm_error=llm.error,
            created_at=__import__("datetime").datetime.utcnow(),
        )

    def list_cases(self):
        return self.db.list_cases()

    def get_case(self, case_id: int):
        return self.db.get_case(case_id)

    def delete_case(self, case_id: int) -> bool:
        return self.db.delete_case(case_id)


def _build_case_note(req: CaseCreateRequest, result, citations: list[Citation]) -> str:
    facts = [
        f"Learner: {req.learner_name}",
        f"Assessed on: {req.assessed_on.isoformat()}",
        f"Attendance: {req.attendance_pct if req.attendance_pct is not None else 'unknown'}",
        f"Live sessions: {req.live_sessions if req.live_sessions is not None else 'unknown'}",
        f"Capstone score: {req.capstone_score if req.capstone_score is not None else 'unknown'}",
        f"Submission: {req.submission_state.value}",
        f"Extension: {req.extension_state.value}",
        f"Medical note: {req.medical_note.value}",
        f"Makeup: {req.makeup_state.value}",
    ]
    sources = ", ".join(f"{c.doc_id} {c.version}" for c in citations) or "none"
    unresolved = ", ".join(result.missing_facts) or "none"
    return (
        "CASE NOTE\n"
        + "\n".join(f"- {f}" for f in facts)
        + f"\n- Sources used: {sources}"
        + f"\n- Outcome: {result.eligibility.value} | submission hold: {result.submission_hold.value}"
        + f"\n- Unresolved: {unresolved}"
        + f"\n- Next action: {result.next_action}"
    )