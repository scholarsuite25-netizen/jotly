from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantScopedMixin
from app.models.foundation import new_uuid, utcnow


class VoiceConsent(Base, TenantScopedMixin):
    __tablename__ = "voice_consents"
    __table_args__ = (
        Index("ix_voice_consents_org_owner", "organisation_id", "owner_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    consent_text_version: Mapped[str] = mapped_column(String(32), nullable=False)
    permitted_uses: Mapped[str] = mapped_column(
        Text, nullable=False, default="internal_synthesis"
    )
    jurisdiction: Mapped[str] = mapped_column(String(64), nullable=False, default="NG")
    verification_method: Mapped[str] = mapped_column(
        String(64), nullable=False, default="challenge_live_sample"
    )
    verification_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    verification_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocation_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class VoiceProfile(Base, TenantScopedMixin):
    """Private-by-default consent-gated voice profile (Phase 6 governance)."""

    __tablename__ = "voice_profiles"
    __table_args__ = (
        Index("ix_voice_profiles_org_owner", "organisation_id", "owner_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    consent_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("voice_consents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    model_id: Mapped[str] = mapped_column(String(120), nullable=False, default="stub-openvoice-v2")
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0.0")
    public_gallery: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class VoiceSample(Base, TenantScopedMixin):
    __tablename__ = "voice_samples"
    __table_args__ = (
        Index("ix_voice_samples_org_profile", "organisation_id", "voice_profile_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    voice_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("voice_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="challenge_live_sample"
    )
    consent_scope: Mapped[str] = mapped_column(
        String(64), nullable=False, default="internal_synthesis"
    )
    retention_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class VoicePermission(Base, TenantScopedMixin):
    """Owner-controlled, expiring permission grant for a voice profile."""

    __tablename__ = "voice_permissions"
    __table_args__ = (
        Index(
            "ix_voice_permissions_org_profile_grantee",
            "organisation_id",
            "voice_profile_id",
            "grantee_user_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    voice_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("voice_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    grantee_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    allowed_use: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class VoiceJob(Base, TenantScopedMixin):
    __tablename__ = "voice_jobs"
    __table_args__ = (
        Index("ix_voice_jobs_org_profile", "organisation_id", "voice_profile_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    voice_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("voice_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    background_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("background_jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requester_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_object_key: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    disclosure_flag: Mapped[str] = mapped_column(
        String(255), nullable=False, default="AI-generated voice clone"
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class VoiceAuditEvent(Base, TenantScopedMixin):
    __tablename__ = "voice_audit_events"
    __table_args__ = (
        Index("ix_voice_audit_org_profile", "organisation_id", "voice_profile_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    voice_profile_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("voice_profiles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    voice_job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    actor_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    permitted_ip_metadata: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
