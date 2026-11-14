"""Meeting Intelligence router: grounded summaries, minutes, decisions, actions, Q&A."""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantAccessContext, require_permission
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.foundation import utcnow
from app.models.intelligence import (
    ActionItem,
    AiAnswer,
    AiJobLog,
    AiQuestion,
    Decision,
    EvidenceLink,
    MeetingSummary,
)
from app.models.meetings_media import Meeting
from app.services.audit import record_audit_event
from app.services.intelligence_rag import (
    answer_question_from_evidence,
    detect_prompt_injection,
    extract_decisions_and_actions,
    generate_summary_from_evidence,
    permission_filtered_retrieval,
)
from app.workers.context import enqueue_tenant_job

router = APIRouter(tags=["meeting-intelligence"])


class GenerateSummaryBody(BaseModel):
    transcript_id: str = Field(min_length=1, max_length=36)


class ReviewSummaryBody(BaseModel):
    approved: bool = Field(...)
    review_note: Optional[str] = Field(default=None, max_length=500)


class AskQuestionBody(BaseModel):
    question_text: str = Field(min_length=3, max_length=2000)
    meeting_id: Optional[str] = Field(default=None, max_length=36)


@router.post("/meetings/{meeting_id}/summaries", status_code=status.HTTP_202_ACCEPTED)
def generate_meeting_summary(
    meeting_id: str,
    payload: GenerateSummaryBody,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Generates a grounded summary/minutes/decisions/actions set:
    retrieval is permission-filtered BEFORE generation; every claim links to
    supporting transcript segment IDs + timestamps; output requires human review.
    """
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        meeting = db.scalars(
            select(Meeting).where(Meeting.id == meeting_id)
        ).first()
        if meeting is None:
            raise NexusAPIError(
                status_code=404,
                code="meeting_not_found",
                message="Meeting not found in the active organisation.",
            )

        bg_job = enqueue_tenant_job(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            job_type="intelligence.generate_summary",
            source_entity_type="meeting",
            source_entity_id=meeting.id,
            idempotency_key=f"summary:{meeting.id}:{payload.transcript_id}",
        )
        return {
            "job_id": bg_job.id,
            "meeting_id": meeting.id,
            "transcript_id": payload.transcript_id,
            "status": bg_job.status,
        }


@router.post("/meetings/{meeting_id}/summaries/{job_id}/execute")
def execute_summary_generation(
    meeting_id: str,
    job_id: str,
    payload: GenerateSummaryBody,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    from app.workers.context import execute_job_in_tenant_context

    def _handler(session: Session, bg_job) -> MeetingSummary:
        meeting = session.scalars(
            select(Meeting).where(Meeting.id == bg_job.source_entity_id)
        ).first()
        if meeting is None:
            raise RuntimeError("Meeting not found in tenant context.")

        retrieval = permission_filtered_retrieval(
            session,
            organisation_id=ctx.organisation.id,
            transcript_ids=[payload.transcript_id],
        )
        injection_hits: list[str] = []
        for seg in retrieval.segments:
            injection_hits.extend(detect_prompt_injection(seg.text))

        summary_text = generate_summary_from_evidence(
            retrieval, meeting_title=meeting.title
        )

        existing = session.scalars(
            select(MeetingSummary).where(
                MeetingSummary.background_job_id == bg_job.id
            )
        ).first()
        if existing is not None:
            return existing

        summary = MeetingSummary(
            organisation_id=ctx.organisation.id,
            meeting_id=meeting.id,
            transcript_id=payload.transcript_id,
            background_job_id=bg_job.id,
            kind="summary",
            content_text=summary_text,
            is_ai_interpretation=True,
            review_status="pending_review",
        )
        session.add(summary)
        session.flush()

        for seg in retrieval.segments[:10]:
            session.add(
                EvidenceLink(
                    organisation_id=ctx.organisation.id,
                    summary_id=summary.id,
                    transcript_id=seg.transcript_id,
                    segment_id=seg.segment_id,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    evidence_kind="quote",
                )
            )

        decisions, actions = extract_decisions_and_actions(retrieval)
        for decision_text, seg in decisions[:10]:
            decision = Decision(
                organisation_id=ctx.organisation.id,
                meeting_id=meeting.id,
                summary_id=summary.id,
                decision_text=decision_text,
                is_ai_interpretation=True,
            )
            session.add(decision)
            session.flush()
            session.add(
                EvidenceLink(
                    organisation_id=ctx.organisation.id,
                    decision_id=decision.id,
                    transcript_id=seg.transcript_id,
                    segment_id=seg.segment_id,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    evidence_kind="quote",
                )
            )
        for action_text, owner_hint, due_hint, seg in actions[:10]:
            action = ActionItem(
                organisation_id=ctx.organisation.id,
                meeting_id=meeting.id,
                summary_id=summary.id,
                action_text=action_text,
                owner_hint=owner_hint,
                due_hint=due_hint,
                is_ai_interpretation=True,
            )
            session.add(action)
            session.flush()
            session.add(
                EvidenceLink(
                    organisation_id=ctx.organisation.id,
                    action_item_id=action.id,
                    transcript_id=seg.transcript_id,
                    segment_id=seg.segment_id,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    evidence_kind="quote",
                )
            )

        session.add(
            AiJobLog(
                organisation_id=ctx.organisation.id,
                background_job_id=bg_job.id,
                job_kind="summary",
                llm_model_id="stub-llm",
                prompt_template_version="summary-v1",
                retrieved_segment_count=retrieval.retrieved_segment_count,
                permission_filter_applied=True,
                injection_attempts_detected=len(injection_hits),
            )
        )

        record_audit_event(
            session,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="intelligence.summary.generate",
            resource_type="meeting_summary",
            resource_id=summary.id,
            result="succeeded",
            metadata={
                "meeting_id": meeting.id,
                "retrieved_segment_count": retrieval.retrieved_segment_count,
                "permission_filter_applied": True,
                "injection_attempts_detected": len(injection_hits),
                "requires_human_review": True,
            },
        )
        return summary

    summary = execute_job_in_tenant_context(
        db,
        job_id=job_id,
        expected_organisation_id=ctx.organisation.id,
        handler=_handler,
    )

    decisions = list(
        db.scalars(
            select(Decision).where(Decision.summary_id == summary.id)
        ).all()
    )
    actions = list(
        db.scalars(
            select(ActionItem).where(ActionItem.summary_id == summary.id)
        ).all()
    )

    return {
        "summary_id": summary.id,
        "meeting_id": summary.meeting_id,
        "content_text": summary.content_text,
        "is_ai_interpretation": summary.is_ai_interpretation,
        "review_status": summary.review_status,
        "decision_count": len(decisions),
        "action_item_count": len(actions),
    }


class SummaryDetail:
    """Deprecated placeholder retained for API shape documentation."""


@router.get("/meetings/{meeting_id}/summaries/{summary_id}")
def get_summary_detail(
    meeting_id: str,
    summary_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        summary = db.scalars(
            select(MeetingSummary).where(
                MeetingSummary.id == summary_id,
                MeetingSummary.meeting_id == meeting_id,
            )
        ).first()
        if summary is None:
            raise NexusAPIError(
                status_code=404,
                code="summary_not_found",
                message="Meeting summary not found in the active organisation.",
            )

        decisions = list(
            db.scalars(
                select(Decision).where(Decision.summary_id == summary.id)
            ).all()
        )
        actions = list(
            db.scalars(
                select(ActionItem).where(ActionItem.summary_id == summary.id)
            ).all()
        )
        evidence = list(
            db.scalars(
                select(EvidenceLink).where(EvidenceLink.summary_id == summary.id)
            ).all()
        )

        return {
            "summary_id": summary.id,
            "meeting_id": summary.meeting_id,
            "transcript_id": summary.transcript_id,
            "kind": summary.kind,
            "content_text": summary.content_text,
            "is_ai_interpretation": summary.is_ai_interpretation,
            "review_status": summary.review_status,
            "reviewed_by_user_id": summary.reviewed_by_user_id,
            "reviewed_at": summary.reviewed_at.isoformat() if summary.reviewed_at else None,
            "decisions": [
                {
                    "id": d.id,
                    "decision_text": d.decision_text,
                    "is_ai_interpretation": d.is_ai_interpretation,
                }
                for d in decisions
            ],
            "action_items": [
                {
                    "id": a.id,
                    "action_text": a.action_text,
                    "owner_hint": a.owner_hint,
                    "due_hint": a.due_hint,
                    "is_ai_interpretation": a.is_ai_interpretation,
                }
                for a in actions
            ],
            "evidence_links": [
                {
                    "id": e.id,
                    "transcript_id": e.transcript_id,
                    "segment_id": e.segment_id,
                    "start_ms": e.start_ms,
                    "end_ms": e.end_ms,
                    "evidence_kind": e.evidence_kind,
                }
                for e in evidence
            ],
        }


@router.post("/summaries/{summary_id}/review")
def review_summary(
    summary_id: str,
    payload: ReviewSummaryBody,
    ctx: TenantAccessContext = Depends(require_permission("transcript.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Human review gate: minutes/summaries stay 'pending_review' and must not be
    distributed until explicitly approved by an authorised human reviewer.
    """
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        summary = db.scalars(
            select(MeetingSummary).where(MeetingSummary.id == summary_id)
        ).first()
        if summary is None:
            raise NexusAPIError(
                status_code=404,
                code="summary_not_found",
                message="Meeting summary not found in the active organisation.",
            )

        summary.review_status = "approved" if payload.approved else "changes_requested"
        summary.reviewed_by_user_id = ctx.user.id
        summary.reviewed_at = utcnow()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="intelligence.summary.review",
            resource_type="meeting_summary",
            resource_id=summary.id,
            result="succeeded",
            metadata={
                "review_status": summary.review_status,
                "review_note": payload.review_note,
            },
        )
        db.commit()
        db.refresh(summary)

        return {
            "summary_id": summary.id,
            "review_status": summary.review_status,
            "reviewed_by_user_id": summary.reviewed_by_user_id,
            "reviewed_at": summary.reviewed_at.isoformat(),
        }


@router.post("/assistant/questions", status_code=status.HTTP_200_OK)
def ask_assistant_question(
    payload: AskQuestionBody,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Evidence-grounded Q&A over authorised records:
    permission-filtered retrieval first; abstains when no evidence supports an answer;
    never invents decisions, owners, or deadlines.
    """
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        if payload.meeting_id:
            meeting = db.scalars(
                select(Meeting).where(Meeting.id == payload.meeting_id)
            ).first()
            if meeting is None:
                raise NexusAPIError(
                    status_code=404,
                    code="meeting_not_found",
                    message="Meeting not found in the active organisation.",
                )

        question = AiQuestion(
            organisation_id=ctx.organisation.id,
            meeting_id=payload.meeting_id,
            asked_by_user_id=ctx.user.id,
            question_text=payload.question_text,
        )
        db.add(question)
        db.flush()

        retrieval = permission_filtered_retrieval(
            db,
            organisation_id=ctx.organisation.id,
            transcript_ids=None,
            query_text=payload.question_text,
        )
        answer_text, abstained, supporting = answer_question_from_evidence(
            retrieval, question=payload.question_text
        )

        answer = AiAnswer(
            organisation_id=ctx.organisation.id,
            question_id=question.id,
            answer_text=answer_text,
            abstained=abstained,
            is_ai_interpretation=True,
        )
        db.add(answer)
        db.flush()

        for seg in supporting[:5]:
            db.add(
                EvidenceLink(
                    organisation_id=ctx.organisation.id,
                    answer_id=answer.id,
                    transcript_id=seg.transcript_id,
                    segment_id=seg.segment_id,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    evidence_kind="quote",
                )
            )

        db.add(
            AiJobLog(
                organisation_id=ctx.organisation.id,
                background_job_id="assistant-inline",
                job_kind="assistant_qa",
                llm_model_id="stub-llm",
                prompt_template_version="qa-v1",
                retrieved_segment_count=retrieval.retrieved_segment_count,
                permission_filter_applied=True,
                injection_attempts_detected=sum(
                    len(detect_prompt_injection(seg.text)) for seg in retrieval.segments
                ),
            )
        )

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="intelligence.assistant.question",
            resource_type="ai_answer",
            resource_id=answer.id,
            result="succeeded",
            metadata={
                "abstained": abstained,
                "supporting_segment_count": len(supporting),
                "permission_filter_applied": True,
            },
        )
        db.commit()
        db.refresh(answer)
        db.refresh(question)

        return {
            "question_id": question.id,
            "answer_id": answer.id,
            "answer_text": answer.answer_text,
            "abstained": abstained,
            "is_ai_interpretation": True,
            "supporting_segment_count": len(supporting),
        }
