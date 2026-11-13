from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantScopedMixin
from app.models.foundation import new_uuid, utcnow


class Transcript(Base, TenantScopedMixin):
    __tablename__ = "transcripts"
    __table_args__ = (
        Index("ix_transcripts_org_meeting", "organisation_id", "meeting_id"),
        Index("ix_transcripts_org_media", "organisation_id", "media_asset_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="RESTRICT"), nullable=False
    )
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False
    )
    background_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("background_jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    language_code: Mapped[str] = mapped_column(
        String(16), nullable=False, default="en"
    )
    detected_language: Mapped[str] = mapped_column(
        String(16), nullable=False, default="en"
    )
    language_confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.95
    )
    asr_model_id: Mapped[str] = mapped_column(
        String(120), nullable=False, default="faster-whisper-large-v3"
    )
    asr_model_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="1.0.3"
    )
    diarisation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    diarisation_model_id: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="completed"
    )
    current_revision_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class TranscriptSpeaker(Base, TenantScopedMixin):
    """
    Represents a speaker track in a transcript.
    `is_model_suggestion` defaults to True for diarisation output, and `identity_verified`
    is ALWAYS False so speaker diarisation is never misrepresented as biometric identity verification.
    """

    __tablename__ = "transcript_speakers"
    __table_args__ = (
        Index(
            "ix_transcript_speakers_org_tx_key",
            "organisation_id",
            "transcript_id",
            "speaker_key",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    transcript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False
    )
    speaker_key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_model_suggestion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    identity_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class SpeakerLabel(Base, TenantScopedMixin):
    """Audit/history record of speaker label assignments or human relabelling."""

    __tablename__ = "speaker_labels"
    __table_args__ = (
        Index("ix_speaker_labels_org_tx", "organisation_id", "transcript_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    transcript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False
    )
    speaker_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transcript_speakers.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_display_name: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    new_display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    changed_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="model_suggestion"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class TranscriptSegment(Base, TenantScopedMixin):
    """
    Individual timestamped transcript segment.
    Preserves `original_asr_text` immutably while storing human edits in `current_text`.
    """

    __tablename__ = "transcript_segments"
    __table_args__ = (
        Index(
            "ix_transcript_segments_org_tx_seq",
            "organisation_id",
            "transcript_id",
            "sequence_number",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    transcript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    original_asr_text: Mapped[str] = mapped_column(Text, nullable=False)
    current_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.9)
    speaker_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("transcript_speakers.id", ondelete="SET NULL"),
        nullable=True,
    )
    speaker_is_model_suggestion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class TranscriptRevision(Base, TenantScopedMixin):
    """Immutable revision log preserving original ASR output and every human edit/undo."""

    __tablename__ = "transcript_revisions"
    __table_args__ = (
        Index(
            "ix_transcript_revisions_org_tx_rev",
            "organisation_id",
            "transcript_id",
            "revision_number",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    transcript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False
    )
    segment_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("transcript_segments.id", ondelete="SET NULL"),
        nullable=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    previous_speaker_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )
    new_speaker_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    editor_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class TranscriptExport(Base, TenantScopedMixin):
    __tablename__ = "transcript_exports"
    __table_args__ = (
        Index("ix_transcript_exports_org_tx", "organisation_id", "transcript_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    transcript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcripts.id", ondelete="RESTRICT"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
