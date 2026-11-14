from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantScopedMixin
from app.models.foundation import new_uuid, utcnow


class SpeechProject(Base, TenantScopedMixin):
    __tablename__ = "speech_projects"
    __table_args__ = (
        Index(
            "ix_speech_projects_org_idem",
            "organisation_id",
            "idempotency_key",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_document_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_document_version_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    voice_id: Mapped[str] = mapped_column(String(64), nullable=False)
    speed_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    output_format: Mapped[str] = mapped_column(String(16), nullable=False, default="wav")
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued"
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    tts_model_id: Mapped[str] = mapped_column(String(120), nullable=False, default="stub-kokoro")
    tts_model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0.0")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class SpeechChunk(Base, TenantScopedMixin):
    __tablename__ = "speech_chunks"
    __table_args__ = (
        Index(
            "ix_speech_chunks_org_project_idx",
            "organisation_id",
            "speech_project_id",
            "chunk_index",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    speech_project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("speech_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    pronunciation_overrides_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}"
    )
    object_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AudioAsset(Base, TenantScopedMixin):
    __tablename__ = "audio_assets"
    __table_args__ = (
        Index("ix_audio_assets_org_project", "organisation_id", "speech_project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    speech_project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("speech_projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    output_format: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    loudness_normalised: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    synthetic_disclosure: Mapped[str] = mapped_column(
        String(255), nullable=False, default="AI-generated speech"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AudioChapter(Base, TenantScopedMixin):
    __tablename__ = "audio_chapters"
    __table_args__ = (
        Index(
            "ix_audio_chapters_org_asset",
            "organisation_id",
            "audio_asset_id",
            "chapter_index",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    audio_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("audio_assets.id", ondelete="CASCADE"), nullable=False
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)


class PronunciationEntry(Base, TenantScopedMixin):
    __tablename__ = "pronunciation_entries"
    __table_args__ = (
        Index(
            "ix_pronunciation_entries_org_word",
            "organisation_id",
            "word",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    word: Mapped[str] = mapped_column(String(120), nullable=False)
    phonetic_hint: Mapped[str] = mapped_column(String(255), nullable=False)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
