from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantScopedMixin
from app.models.foundation import new_uuid, utcnow


class MeetingSummary(Base, TenantScopedMixin):
    """AI-generated summary — always distinct from source transcript (human-reviewed flag)."""

    __tablename__ = "meeting_summaries"
    __table_args__ = (
        Index("ix_meeting_summaries_org_meeting", "organisation_id", "meeting_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="RESTRICT"), nullable=False
    )
    transcript_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transcripts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    background_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("background_jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="summary")
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    llm_model_id: Mapped[str] = mapped_column(String(120), nullable=False, default="stub-llm")
    llm_model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0.0")
    prompt_template_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="summary-v1"
    )
    is_ai_interpretation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending_review"
    )
    reviewed_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Decision(Base, TenantScopedMixin):
    __tablename__ = "decisions"
    __table_args__ = (
        Index("ix_decisions_org_meeting", "organisation_id", "meeting_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="RESTRICT"), nullable=False
    )
    summary_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("meeting_summaries.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_ai_interpretation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ActionItem(Base, TenantScopedMixin):
    __tablename__ = "action_items"
    __table_args__ = (
        Index("ix_action_items_org_meeting", "organisation_id", "meeting_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="RESTRICT"), nullable=False
    )
    summary_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("meeting_summaries.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_text: Mapped[str] = mapped_column(Text, nullable=False)
    owner_hint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    due_hint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_ai_interpretation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AiQuestion(Base, TenantScopedMixin):
    __tablename__ = "ai_questions"
    __table_args__ = (
        Index("ix_ai_questions_org_meeting", "organisation_id", "meeting_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    meeting_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("meetings.id", ondelete="RESTRICT"),
        nullable=True,
    )
    asked_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AiAnswer(Base, TenantScopedMixin):
    __tablename__ = "ai_answers"
    __table_args__ = (
        Index("ix_ai_answers_org_question", "organisation_id", "question_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_questions.id", ondelete="CASCADE"), nullable=False
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_ai_interpretation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    llm_model_id: Mapped[str] = mapped_column(String(120), nullable=False, default="stub-llm")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class EvidenceLink(Base, TenantScopedMixin):
    """Every material claim/answer must link to supporting transcript segment IDs + timestamps."""

    __tablename__ = "evidence_links"
    __table_args__ = (
        Index("ix_evidence_links_org_summary", "organisation_id", "summary_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    summary_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("meeting_summaries.id", ondelete="CASCADE"),
        nullable=True,
    )
    answer_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("ai_answers.id", ondelete="CASCADE"), nullable=True
    )
    decision_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("decisions.id", ondelete="CASCADE"), nullable=True
    )
    action_item_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("action_items.id", ondelete="CASCADE"), nullable=True
    )
    transcript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcripts.id", ondelete="RESTRICT"), nullable=False
    )
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcript_segments.id", ondelete="RESTRICT"), nullable=False
    )
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="quote"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AiJobLog(Base, TenantScopedMixin):
    __tablename__ = "ai_job_logs"
    __table_args__ = (
        Index("ix_ai_job_logs_org_job", "organisation_id", "background_job_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    background_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("background_jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_segment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    permission_filter_applied: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    injection_attempts_detected: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
