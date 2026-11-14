"""Voice Clone Vault router: consent enrolment, profiles, permissions, synthesis, revocation.

CRITICAL SAFEGUARDS (per prompts/phases/06_PHASE_VOICE_GOVERNANCE.md):
- Every synthesis request re-validates consent + permission server-side.
- Immediate revocation blocks subsequent synthesis.
- No anonymous/bulk cloning, no public gallery.
- Feature remains behind VOICE_CLONING_ENABLED=False until all Phase 6 gates pass.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    TenantAccessContext,
    get_active_tenant_context,
    require_permission,
)
from app.core.config import get_settings
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.foundation import utcnow
from app.models.voice_governance import (
    VoiceAuditEvent,
    VoiceConsent,
    VoiceJob,
    VoicePermission,
    VoiceProfile,
    VoiceSample,
)
from app.services.audit import record_audit_event
from app.services.storage_media import (
    create_signed_playback_url,
    get_private_storage,
    verify_signed_playback_signature,
)
from app.services.voice_governance import (
    _aware,
    authorize_voice_synthesis,
    record_voice_audit,
)
from app.workers.context import enqueue_tenant_job

router = APIRouter(prefix="/voice", tags=["voice-governance"])
FORBIDDEN_VOICE_USES: frozenset[str] = frozenset(
    {
        "authentication",
        "financial_authorisation",
        "emergency_instructions",
        "identity_verification",
    }
)


class ConsentBody(BaseModel):
    consent_text_version: str = Field(min_length=2, max_length=32)
    permitted_uses: str = Field(default="internal_synthesis", max_length=255)
    jurisdiction: str = Field(default="NG", max_length=64)
    verification_method: str = Field(
        default="challenge_live_sample", max_length=64
    )
    verification_reference: str = Field(min_length=4, max_length=128)
    verification_passed: bool = Field(...)
    expires_in_days: Optional[int] = Field(default=365, ge=1, le=3650)


class CreateProfileBody(BaseModel):
    consent_id: str = Field(min_length=1, max_length=36)
    display_name: str = Field(min_length=1, max_length=120)
    sample_content_base64: str = Field(min_length=1, max_length=5000000)
    retention_days: int = Field(default=90, ge=1, le=3650)


class PermissionBody(BaseModel):
    grantee_user_id: str = Field(min_length=1, max_length=36)
    allowed_use: str = Field(default="internal_synthesis", max_length=64)
    expires_in_days: Optional[int] = Field(default=30, ge=1, le=3650)


class SynthesisBody(BaseModel):
    text_content: str = Field(min_length=1, max_length=50000)


def _assert_voice_cloning_gate() -> None:
    """The global feature flag must remain disabled until all Phase 6 gates pass."""
    settings = get_settings()
    if settings.voice_cloning_enabled:
        raise NexusAPIError(
            status_code=503,
            code="voice_cloning_publicly_disabled",
            message=(
                "Public voice cloning is disabled until legal, security, licensing, "
                "abuse-prevention, quality and operational gates are signed off."
            ),
        )


@router.post("/consents", status_code=status.HTTP_201_CREATED)
def record_consent(
    payload: ConsentBody,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    _assert_voice_cloning_gate()
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        consent = VoiceConsent(
            organisation_id=ctx.organisation.id,
            owner_user_id=ctx.user.id,
            consent_text_version=payload.consent_text_version.strip(),
            permitted_uses=payload.permitted_uses.strip(),
            jurisdiction=payload.jurisdiction.strip(),
            verification_method=payload.verification_method.strip(),
            verification_reference=payload.verification_reference.strip(),
            verification_passed=payload.verification_passed,
            expires_at=(
                utcnow() + timedelta(days=payload.expires_in_days)
                if payload.expires_in_days
                else None
            ),
        )
        db.add(consent)
        db.flush()

        record_voice_audit(
            db,
            organisation_id=ctx.organisation.id,
            voice_profile_id=None,
            voice_job_id=None,
            actor_user_id=ctx.user.id,
            action="voice.consent.record",
            result="succeeded" if payload.verification_passed else "verification_pending",
            reason=None if payload.verification_passed else "verification_not_passed",
        )
        db.commit()
        db.refresh(consent)

        return {
            "consent_id": consent.id,
            "owner_user_id": consent.owner_user_id,
            "consent_text_version": consent.consent_text_version,
            "verification_passed": consent.verification_passed,
            "expires_at": consent.expires_at.isoformat() if consent.expires_at else None,
            "revocation_at": None,
        }


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
def create_voice_profile(
    payload: CreateProfileBody,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Enrols a private-by-default voice profile ONLY with a valid, verified, unrevoked
    consent record belonging to the requester (no anonymous or bulk cloning).
    """
    _assert_voice_cloning_gate()
    storage = get_private_storage()
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        consent = db.scalars(
            select(VoiceConsent).where(
                VoiceConsent.id == payload.consent_id,
                VoiceConsent.organisation_id == ctx.organisation.id,
                VoiceConsent.owner_user_id == ctx.user.id,
            )
        ).first()
        if consent is None:
            raise NexusAPIError(
                status_code=404,
                code="consent_not_found",
                message="Valid consent record not found for the voice profile owner.",
            )
        if not consent.verification_passed:
            raise NexusAPIError(
                status_code=403,
                code="consent_verification_failed",
                message="Identity/authority verification must pass before profile enrolment.",
            )
        if consent.revocation_at is not None:
            raise NexusAPIError(
                status_code=403,
                code="consent_revoked",
                message="Consent has been revoked; enrolment denied.",
            )
        if consent.expires_at is not None and _aware(consent.expires_at) < utcnow():
            raise NexusAPIError(
                status_code=403,
                code="consent_expired",
                message="Consent has expired; enrolment denied.",
            )

        profile = VoiceProfile(
            organisation_id=ctx.organisation.id,
            owner_user_id=ctx.user.id,
            consent_record_id=consent.id,
            display_name=payload.display_name.strip(),
            status="active",
            public_gallery=False,
        )
        db.add(profile)
        db.flush()

        import base64

        try:
            sample_bytes = base64.b64decode(payload.sample_content_base64, validate=True)
        except Exception as exc:
            raise NexusAPIError(
                status_code=400,
                code="invalid_sample_encoding",
                message="Voice sample payload must be valid base64.",
            ) from exc
        if not sample_bytes:
            raise NexusAPIError(
                status_code=400,
                code="voice_sample_empty",
                message="Voice sample must not be empty.",
            )

        sha256_checksum = hashlib.sha256(sample_bytes).hexdigest()
        sample_key = (
            f"tenants/{ctx.organisation.id}/voice/{profile.id}"
            f"/samples/challenge-live-{profile.id[:8]}.wav"
        )
        storage.put_bytes(
            organisation_id=ctx.organisation.id,
            object_key=sample_key,
            data=sample_bytes,
        )
        sample = VoiceSample(
            organisation_id=ctx.organisation.id,
            voice_profile_id=profile.id,
            object_key=sample_key,
            duration_ms=max(1, len(sample_bytes) // 32),
            sha256_checksum=sha256_checksum,
            source_type="challenge_live_sample",
            consent_scope=consent.permitted_uses,
            retention_until=utcnow() + timedelta(days=payload.retention_days),
        )
        db.add(sample)

        record_voice_audit(
            db,
            organisation_id=ctx.organisation.id,
            voice_profile_id=profile.id,
            voice_job_id=None,
            actor_user_id=ctx.user.id,
            action="voice.profile.enrol",
            result="succeeded",
            reason=None,
        )
        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="voice.profile.enrol",
            resource_type="voice_profile",
            resource_id=profile.id,
            result="succeeded",
            metadata={
                "private_by_default": True,
                "consent_id": consent.id,
            },
        )
        db.commit()
        db.refresh(profile)

        return {
            "voice_profile_id": profile.id,
            "owner_user_id": profile.owner_user_id,
            "display_name": profile.display_name,
            "status": profile.status,
            "public_gallery": profile.public_gallery,
            "consent_id": consent.id,
            "model_id": profile.model_id,
            "sample_id": sample.id,
        }


@router.post("/profiles/{profile_id}/permissions", status_code=status.HTTP_201_CREATED)
def grant_voice_permission(
    profile_id: str,
    payload: PermissionBody,
    ctx: TenantAccessContext = Depends(get_active_tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    """Only the voice-profile owner can grant, scope, and expire synthesis permissions."""
    _assert_voice_cloning_gate()
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        profile = db.scalars(
            select(VoiceProfile).where(
                VoiceProfile.id == profile_id,
                VoiceProfile.organisation_id == ctx.organisation.id,
            )
        ).first()
        if profile is None:
            raise NexusAPIError(
                status_code=404,
                code="voice_profile_not_found",
                message="Voice profile not found in the active organisation.",
            )
        if profile.owner_user_id != ctx.user.id:
            record_voice_audit(
                db,
                organisation_id=ctx.organisation.id,
                voice_profile_id=profile.id,
                voice_job_id=None,
                actor_user_id=ctx.user.id,
                action="voice.permission.grant",
                result="denied",
                reason="not_profile_owner",
            )
            raise NexusAPIError(
                status_code=403,
                code="voice_profile_owner_required",
                message="Only the voice profile owner can grant permissions.",
            )
        if profile.revoked_at is not None or profile.deleted_at is not None:
            raise NexusAPIError(
                status_code=403,
                code="voice_profile_unavailable",
                message="Revoked or deleted profiles cannot be shared.",
            )

        existing = db.scalars(
            select(VoicePermission).where(
                VoicePermission.organisation_id == ctx.organisation.id,
                VoicePermission.voice_profile_id == profile.id,
                VoicePermission.grantee_user_id == payload.grantee_user_id,
                VoicePermission.revoked_at.is_(None),
            )
        ).first()
        if existing is not None:
            existing.allowed_use = payload.allowed_use.strip()
            existing.expires_at = (
                utcnow() + timedelta(days=payload.expires_in_days)
                if payload.expires_in_days
                else None
            )
            db.commit()
            db.refresh(existing)
            permission = existing
            created = False
        else:
            permission = VoicePermission(
                organisation_id=ctx.organisation.id,
                voice_profile_id=profile.id,
                grantee_user_id=payload.grantee_user_id,
                allowed_use=payload.allowed_use.strip(),
                granted_by_user_id=ctx.user.id,
                expires_at=(
                    utcnow() + timedelta(days=payload.expires_in_days)
                    if payload.expires_in_days
                    else None
                ),
            )
            db.add(permission)
            db.flush()
            created = True

        record_voice_audit(
            db,
            organisation_id=ctx.organisation.id,
            voice_profile_id=profile.id,
            voice_job_id=None,
            actor_user_id=ctx.user.id,
            action="voice.permission.grant",
            result="succeeded",
            reason=f"grantee={payload.grantee_user_id}",
        )
        db.commit()
        db.refresh(permission)

        return {
            "permission_id": permission.id,
            "voice_profile_id": profile.id,
            "grantee_user_id": permission.grantee_user_id,
            "allowed_use": permission.allowed_use,
            "expires_at": permission.expires_at.isoformat() if permission.expires_at else None,
            "revoked_at": None,
            "updated_existing": not created,
        }


@router.post("/profiles/{profile_id}/permissions/{permission_id}/revoke")
def revoke_voice_permission(
    profile_id: str,
    permission_id: str,
    ctx: TenantAccessContext = Depends(get_active_tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    _assert_voice_cloning_gate()
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        profile = db.scalars(
            select(VoiceProfile).where(
                VoiceProfile.id == profile_id,
                VoiceProfile.organisation_id == ctx.organisation.id,
            )
        ).first()
        if profile is None:
            raise NexusAPIError(
                status_code=404,
                code="voice_profile_not_found",
                message="Voice profile not found in the active organisation.",
            )
        if profile.owner_user_id != ctx.user.id:
            raise NexusAPIError(
                status_code=403,
                code="voice_profile_owner_required",
                message="Only the voice profile owner can revoke permissions.",
            )
        permission = db.scalars(
            select(VoicePermission).where(
                VoicePermission.id == permission_id,
                VoicePermission.voice_profile_id == profile.id,
            )
        ).first()
        if permission is None:
            raise NexusAPIError(
                status_code=404,
                code="voice_permission_not_found",
                message="Voice permission grant not found.",
            )
        if permission.revoked_at is None:
            permission.revoked_at = utcnow()
            record_voice_audit(
                db,
                organisation_id=ctx.organisation.id,
                voice_profile_id=profile.id,
                voice_job_id=None,
                actor_user_id=ctx.user.id,
                action="voice.permission.revoke",
                result="succeeded",
                reason=f"grantee={permission.grantee_user_id}",
            )
            db.commit()
            db.refresh(permission)
        return {
            "permission_id": permission.id,
            "revoked_at": permission.revoked_at.isoformat(),
        }


@router.post("/profiles/{profile_id}/revoke")
def revoke_voice_profile(
    profile_id: str,
    ctx: TenantAccessContext = Depends(get_active_tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    """Owner revocation immediately blocks profile use and all active grants."""
    _assert_voice_cloning_gate()
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        profile = db.scalars(
            select(VoiceProfile).where(
                VoiceProfile.id == profile_id,
                VoiceProfile.organisation_id == ctx.organisation.id,
            )
        ).first()
        if profile is None:
            raise NexusAPIError(
                status_code=404,
                code="voice_profile_not_found",
                message="Voice profile not found in the active organisation.",
            )
        if profile.owner_user_id != ctx.user.id:
            raise NexusAPIError(
                status_code=403,
                code="voice_profile_owner_required",
                message="Only the voice profile owner can revoke the profile.",
            )
        if profile.revoked_at is None:
            profile.revoked_at = utcnow()
            profile.status = "revoked"
            db.flush()

            record_voice_audit(
                db,
                organisation_id=ctx.organisation.id,
                voice_profile_id=profile.id,
                voice_job_id=None,
                actor_user_id=ctx.user.id,
                action="voice.profile.revoke",
                result="succeeded",
                reason="owner_revocation",
            )
            record_audit_event(
                db,
                organisation_id=ctx.organisation.id,
                actor_user_id=ctx.user.id,
                action="voice.profile.revoke",
                resource_type="voice_profile",
                resource_id=profile.id,
                result="succeeded",
                metadata={"immediate_block": True},
            )
            db.commit()
            db.refresh(profile)
        return {
            "voice_profile_id": profile.id,
            "status": profile.status,
            "revoked_at": profile.revoked_at.isoformat(),
        }


@router.post("/profiles/{profile_id}/synthesis", status_code=status.HTTP_202_ACCEPTED)
def request_voice_synthesis(
    profile_id: str,
    payload: SynthesisBody,
    ctx: TenantAccessContext = Depends(get_active_tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    """
    Requests clone synthesis: consent + permission are re-validated server-side on
    EVERY request; revocation/expiry blocks immediately. Prohibited uses are rejected.
    """
    _assert_voice_cloning_gate()
    text_sha256 = hashlib.sha256(payload.text_content.encode("utf-8")).hexdigest()

    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        profile = db.scalars(
            select(VoiceProfile).where(
                VoiceProfile.id == profile_id,
                VoiceProfile.organisation_id == ctx.organisation.id,
            )
        ).first()
        if profile is None:
            record_voice_audit(
                db,
                organisation_id=ctx.organisation.id,
                voice_profile_id=None,
                voice_job_id=None,
                actor_user_id=ctx.user.id,
                action="voice.synthesis.authorise",
                result="denied",
                reason="profile_not_found_or_cross_tenant",
            )
            db.commit()
            raise NexusAPIError(
                status_code=404,
                code="voice_profile_not_found",
                message="Voice profile not found in the active organisation.",
            )

        try:
            permission = authorize_voice_synthesis(
                db,
                organisation_id=ctx.organisation.id,
                voice_profile=profile,
                requester_user_id=ctx.user.id,
                allowed_use="internal_synthesis",
            )
        except NexusAPIError:
            db.commit()
            raise

        bg_job = enqueue_tenant_job(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            job_type="voice.synthesize",
            source_entity_type="voice_profile",
            source_entity_id=profile.id,
            idempotency_key=f"voice-synth:{profile.id}:{text_sha256}",
        )
        voice_job = VoiceJob(
            organisation_id=ctx.organisation.id,
            voice_profile_id=profile.id,
            background_job_id=bg_job.id,
            requester_user_id=ctx.user.id,
            text_sha256=text_sha256,
            status="queued",
            disclosure_flag="AI-generated voice clone",
        )
        db.add(voice_job)
        db.flush()

        record_voice_audit(
            db,
            organisation_id=ctx.organisation.id,
            voice_profile_id=profile.id,
            voice_job_id=voice_job.id,
            actor_user_id=ctx.user.id,
            action="voice.synthesis.authorise",
            result="succeeded",
            reason=f"permission={permission.id}",
        )
        db.commit()
        db.refresh(voice_job)

        return {
            "voice_job_id": voice_job.id,
            "job_id": bg_job.id,
            "voice_profile_id": profile.id,
            "text_sha256": text_sha256,
            "status": voice_job.status,
            "disclosure_flag": voice_job.disclosure_flag,
        }


@router.get("/jobs/{voice_job_id}/result")
def get_voice_job_result(
    voice_job_id: str,
    ctx: TenantAccessContext = Depends(get_active_tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    storage = get_private_storage()
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        voice_job = db.scalars(
            select(VoiceJob).where(
                VoiceJob.id == voice_job_id,
                VoiceJob.organisation_id == ctx.organisation.id,
            )
        ).first()
        if voice_job is None:
            raise NexusAPIError(
                status_code=404,
                code="voice_job_not_found",
                message="Voice job not found in the active organisation.",
            )

        if voice_job.status != "completed":
            return {
                "voice_job_id": voice_job.id,
                "status": voice_job.status,
                "output_object_key": None,
            }

        signed = create_signed_playback_url(
            organisation_id=ctx.organisation.id, asset_id=voice_job.id
        )
        signed["url"] = signed["url"].replace("/media/", "/voice/")

        record_voice_audit(
            db,
            organisation_id=ctx.organisation.id,
            voice_profile_id=voice_job.voice_profile_id,
            voice_job_id=voice_job.id,
            actor_user_id=ctx.user.id,
            action="voice.output.access",
            result="succeeded",
        )
        db.commit()
        return {
            "voice_job_id": voice_job.id,
            "status": voice_job.status,
            "output_object_key": voice_job.output_object_key,
            "disclosure_flag": voice_job.disclosure_flag,
            "playback_url": signed["url"],
            "expires_at": signed["expires_at"],
        }


@router.get("/outputs/{voice_job_id}/stream")
def stream_voice_output(
    voice_job_id: str,
    org_id: str,
    expires: int,
    signature: str,
    db: Session = Depends(get_db),
) -> dict:
    verify_signed_playback_signature(
        organisation_id=org_id,
        asset_id=voice_job_id,
        expires=expires,
        signature=signature,
    )
    storage = get_private_storage()
    with tenant_db_context(db, organisation_id=org_id):
        voice_job = db.scalars(
            select(VoiceJob).where(
                VoiceJob.id == voice_job_id,
                VoiceJob.organisation_id == org_id,
            )
        ).first()
        if voice_job is None or not voice_job.output_object_key:
            raise NexusAPIError(
                status_code=404,
                code="voice_output_not_found",
                message="Voice output not found.",
            )
        raw_bytes = storage.get_bytes(
            organisation_id=org_id, object_key=voice_job.output_object_key
        )
        from fastapi import Response

        return Response(
            content=raw_bytes,
            media_type="audio/wav",
            headers={
                "Cache-Control": "private, no-store",
                "X-Synthetic-Audio-Disclosure": voice_job.disclosure_flag,
            },
        )


@router.get("/profiles/{profile_id}/audit")
def get_voice_audit_trail(
    profile_id: str,
    ctx: TenantAccessContext = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        profile = db.scalars(
            select(VoiceProfile).where(
                VoiceProfile.id == profile_id,
                VoiceProfile.organisation_id == ctx.organisation.id,
            )
        ).first()
        if profile is None:
            raise NexusAPIError(
                status_code=404,
                code="voice_profile_not_found",
                message="Voice profile not found in the active organisation.",
            )
        events = list(
            db.scalars(
                select(VoiceAuditEvent)
                .where(VoiceAuditEvent.voice_profile_id == profile.id)
                .order_by(VoiceAuditEvent.created_at.desc())
                .limit(200)
            ).all()
        )
        return {
            "voice_profile_id": profile.id,
            "items": [
                {
                    "id": e.id,
                    "action": e.action,
                    "result": e.result,
                    "reason": e.reason,
                    "actor_user_id": e.actor_user_id,
                    "voice_job_id": e.voice_job_id,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ],
        }
