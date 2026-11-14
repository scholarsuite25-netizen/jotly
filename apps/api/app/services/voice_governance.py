"""Voice Governance service: consent validation, synthesis authorization, revocation blocking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NexusAPIError
from app.models.foundation import utcnow
from app.models.voice_governance import (
    VoiceAuditEvent,
    VoiceConsent,
    VoicePermission,
    VoiceProfile,
)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite stores naive datetimes; compare with timezone-aware values safely."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def record_voice_audit(
    db: Session,
    *,
    organisation_id: str,
    voice_profile_id: Optional[str],
    voice_job_id: Optional[str],
    actor_user_id: Optional[str],
    action: str,
    result: str,
    reason: Optional[str] = None,
    permitted_ip_metadata: Optional[str] = None,
) -> VoiceAuditEvent:
    entry = VoiceAuditEvent(
        organisation_id=organisation_id,
        voice_profile_id=voice_profile_id,
        voice_job_id=voice_job_id,
        actor_user_id=actor_user_id,
        action=action,
        result=result,
        reason=reason,
        permitted_ip_metadata=permitted_ip_metadata,
    )
    db.add(entry)
    db.flush()
    return entry


def validate_consent_for_profile(
    db: Session,
    *,
    organisation_id: str,
    voice_profile: VoiceProfile,
    now: Optional[datetime] = None,
) -> VoiceConsent:
    """
    Authoritative consent validation:
    1. Consent record must exist, be signed, and verification must have passed.
    2. Consent must not be revoked or expired.
    3. Profile must not be revoked or deleted.
    4. Profile must stay private (public_gallery=False).
    """
    current = now or utcnow()

    if voice_profile.organisation_id != organisation_id:
        raise NexusAPIError(
            status_code=403,
            code="voice_tenant_mismatch",
            message="Voice profile does not belong to the active organisation.",
        )
    if voice_profile.revoked_at is not None or voice_profile.deleted_at is not None:
        raise NexusAPIError(
            status_code=403,
            code="voice_profile_unavailable",
            message="Voice profile is revoked or deleted and cannot be used.",
        )
    if voice_profile.public_gallery:
        raise NexusAPIError(
            status_code=403,
            code="voice_public_gallery_forbidden",
            message="Public voice galleries are prohibited.",
        )
    if (
        voice_profile.expires_at is not None
        and _aware(voice_profile.expires_at) < current
    ):
        raise NexusAPIError(
            status_code=403,
            code="voice_profile_expired",
            message="Voice profile has expired.",
        )

    consent = db.scalars(
        select(VoiceConsent).where(
            VoiceConsent.id == voice_profile.consent_record_id
        )
    ).first()
    if consent is None:
        raise NexusAPIError(
            status_code=403,
            code="voice_consent_missing",
            message="Voice profile has no valid consent record.",
        )
    if not consent.verification_passed:
        raise NexusAPIError(
            status_code=403,
            code="voice_consent_verification_failed",
            message="Voice-owner identity/authority verification has not passed.",
        )
    if consent.revocation_at is not None:
        raise NexusAPIError(
            status_code=403,
            code="voice_consent_revoked",
            message="Voice-owner consent has been revoked.",
        )
    if consent.expires_at is not None and _aware(consent.expires_at) < current:
        raise NexusAPIError(
            status_code=403,
            code="voice_consent_expired",
            message="Voice-owner consent has expired.",
        )
    return consent


def authorize_voice_synthesis(
    db: Session,
    *,
    organisation_id: str,
    voice_profile: VoiceProfile,
    requester_user_id: str,
    allowed_use: str,
    now: Optional[datetime] = None,
) -> VoicePermission:
    """
    Server-side permission checks required before EVERY synthesis job:
    owner or explicit, non-revoked, non-expired VoicePermission grant is required.
    Immediate revocation blocks synthesis because grants are checked live.
    """
    current = now or utcnow()
    validate_consent_for_profile(
        db, organisation_id=organisation_id, voice_profile=voice_profile, now=current
    )

    if voice_profile.owner_user_id == requester_user_id:
        grant = VoicePermission(
            organisation_id=organisation_id,
            voice_profile_id=voice_profile.id,
            grantee_user_id=requester_user_id,
            allowed_use=allowed_use,
            granted_by_user_id=requester_user_id,
            expires_at=None,
            revoked_at=None,
        )
        db.add(grant)
        db.flush()
        return grant

    permission = db.scalars(
        select(VoicePermission).where(
            VoicePermission.organisation_id == organisation_id,
            VoicePermission.voice_profile_id == voice_profile.id,
            VoicePermission.grantee_user_id == requester_user_id,
            VoicePermission.revoked_at.is_(None),
        )
    ).first()

    if permission is None:
        record_voice_audit(
            db,
            organisation_id=organisation_id,
            voice_profile_id=voice_profile.id,
            voice_job_id=None,
            actor_user_id=requester_user_id,
            action="voice.synthesis.authorise",
            result="denied",
            reason="no_permission_grant",
        )
        raise NexusAPIError(
            status_code=403,
            code="voice_permission_required",
            message="No active permission grant from the voice profile owner.",
        )
    if permission.expires_at is not None and _aware(permission.expires_at) < current:
        record_voice_audit(
            db,
            organisation_id=organisation_id,
            voice_profile_id=voice_profile.id,
            voice_job_id=None,
            actor_user_id=requester_user_id,
            action="voice.synthesis.authorise",
            result="denied",
            reason="permission_grant_expired",
        )
        raise NexusAPIError(
            status_code=403,
            code="voice_permission_expired",
            message="Permission grant from the voice profile owner has expired.",
        )
    if permission.allowed_use not in (allowed_use, "*"):
        record_voice_audit(
            db,
            organisation_id=organisation_id,
            voice_profile_id=voice_profile.id,
            voice_job_id=None,
            actor_user_id=requester_user_id,
            action="voice.synthesis.authorise",
            result="denied",
            reason="out_of_scope_use",
        )
        raise NexusAPIError(
            status_code=403,
            code="voice_use_out_of_scope",
            message=f"Permission grant does not cover requested use '{allowed_use}'.",
        )
    return permission
