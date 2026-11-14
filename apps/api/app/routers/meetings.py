import base64
from datetime import datetime, timedelta
import hashlib
import math
from typing import Optional

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantAccessContext, require_permission
from app.core.config import get_settings
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.foundation import Department, Workspace, utcnow
from app.models.meetings_media import (
    MediaAsset,
    MediaChunk,
    MediaDerivative,
    MediaProcessingJob,
    MediaUploadSession,
    Meeting,
    MeetingParticipant,
)
from app.models.transcription import Transcript
from app.services.audit import record_audit_event
from app.services.storage_media import (
    get_private_storage,
    validate_media_magic_bytes,
    validate_media_mime_type,
)
from app.workers.context import enqueue_tenant_job
from app.workers.media_worker import run_media_validation_and_normalisation_worker

router = APIRouter(prefix="/meetings", tags=["meetings"])

ALLOWED_VISIBILITIES: frozenset[str] = frozenset(
    {"workspace", "private", "department", "organisation"}
)
MAX_ACTIVE_UPLOADS_PER_TENANT = 10


class ParticipantInput(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    display_name: str = Field(min_length=1, max_length=255)
    role: str = Field(default="attendee", max_length=32)


class CreateMeetingRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    department_id: Optional[str] = Field(default=None, max_length=36)
    title: str = Field(min_length=2, max_length=255)
    agenda: Optional[str] = Field(default=None, max_length=5000)
    scheduled_start_at: Optional[datetime] = None
    scheduled_end_at: Optional[datetime] = None
    visibility: str = Field(default="workspace")
    attendees: list[ParticipantInput] = Field(default_factory=list)


class RecordingNoticeConfirmRequest(BaseModel):
    notice_version: str = Field(default="2026-11-v1", min_length=2, max_length=32)
    host_confirmed: bool = Field(...)


class InitiateUploadSessionRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=3, max_length=100)
    declared_size_bytes: int = Field(gt=0)
    expected_sha256: str = Field(min_length=64, max_length=64)
    chunk_size_bytes: Optional[int] = Field(default=None, gt=0)


class UploadChunkRequest(BaseModel):
    data_base64: str = Field(min_length=1)
    sha256_checksum: str = Field(min_length=64, max_length=64)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_meeting(
    payload: CreateMeetingRequest,
    ctx: TenantAccessContext = Depends(require_permission("meeting.record")),
    db: Session = Depends(get_db),
) -> dict:
    if payload.visibility not in ALLOWED_VISIBILITIES:
        raise NexusAPIError(
            status_code=400,
            code="invalid_visibility",
            message=f"Visibility must be one of {sorted(ALLOWED_VISIBILITIES)}.",
        )

    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        workspace = db.scalars(
            select(Workspace).where(Workspace.id == payload.workspace_id)
        ).first()
        if workspace is None:
            raise NexusAPIError(
                status_code=404,
                code="workspace_not_found",
                message="Workspace not found in the active organisation.",
            )

        if payload.department_id:
            dept = db.scalars(
                select(Department).where(Department.id == payload.department_id)
            ).first()
            if dept is None:
                raise NexusAPIError(
                    status_code=404,
                    code="department_not_found",
                    message="Department not found in the active organisation.",
                )

        meeting = Meeting(
            organisation_id=ctx.organisation.id,
            workspace_id=workspace.id,
            department_id=payload.department_id,
            host_user_id=ctx.user.id,
            title=payload.title.strip(),
            agenda=payload.agenda,
            scheduled_start_at=payload.scheduled_start_at,
            scheduled_end_at=payload.scheduled_end_at,
            visibility=payload.visibility,
            recording_state="idle",
        )
        db.add(meeting)
        db.flush()

        for attendee in payload.attendees:
            db.add(
                MeetingParticipant(
                    organisation_id=ctx.organisation.id,
                    meeting_id=meeting.id,
                    email=attendee.email.strip().lower(),
                    display_name=attendee.display_name.strip(),
                    role=attendee.role,
                    consent_status="notified",
                )
            )
        db.flush()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="meeting.create",
            resource_type="meeting",
            resource_id=meeting.id,
            result="succeeded",
            metadata={
                "workspace_id": meeting.workspace_id,
                "visibility": meeting.visibility,
                "attendee_count": len(payload.attendees),
            },
        )
        db.commit()
        db.refresh(meeting)

        return {
            "id": meeting.id,
            "organisation_id": meeting.organisation_id,
            "workspace_id": meeting.workspace_id,
            "department_id": meeting.department_id,
            "host_user_id": meeting.host_user_id,
            "title": meeting.title,
            "agenda": meeting.agenda,
            "visibility": meeting.visibility,
            "recording_state": meeting.recording_state,
            "notice_confirmed": meeting.notice_confirmed_at is not None,
        }


@router.get("")
def list_meetings(
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        meetings = list(
            db.scalars(
                select(Meeting).order_by(Meeting.created_at.desc())
            ).all()
        )
        return {
            "items": [
                {
                    "id": m.id,
                    "organisation_id": m.organisation_id,
                    "workspace_id": m.workspace_id,
                    "title": m.title,
                    "visibility": m.visibility,
                    "recording_state": m.recording_state,
                    "notice_confirmed": m.notice_confirmed_at is not None,
                }
                for m in meetings
            ]
        }


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
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
        participants = list(
            db.scalars(
                select(MeetingParticipant).where(
                    MeetingParticipant.meeting_id == meeting.id
                )
            ).all()
        )
        return {
            "id": meeting.id,
            "organisation_id": meeting.organisation_id,
            "workspace_id": meeting.workspace_id,
            "department_id": meeting.department_id,
            "host_user_id": meeting.host_user_id,
            "title": meeting.title,
            "agenda": meeting.agenda,
            "visibility": meeting.visibility,
            "recording_state": meeting.recording_state,
            "notice_version": meeting.notice_version,
            "notice_confirmed": meeting.notice_confirmed_at is not None,
            "attendees": [
                {
                    "id": p.id,
                    "email": p.email,
                    "display_name": p.display_name,
                    "role": p.role,
                    "consent_status": p.consent_status,
                }
                for p in participants
            ],
        }


@router.post("/{meeting_id}/recording-notice-confirm")
def confirm_recording_notice(
    meeting_id: str,
    payload: RecordingNoticeConfirmRequest,
    ctx: TenantAccessContext = Depends(require_permission("meeting.record")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Records the host's confirmation of the pre-recording notice and consent reminder.
    Must be completed before starting recording capture or initiating media uploads.
    Note: Recording notice confirmation is NEVER treated as voice-cloning consent.
    """
    if not payload.host_confirmed:
        raise NexusAPIError(
            status_code=400,
            code="recording_notice_not_confirmed",
            message="Host must explicitly confirm the recording notice before capture.",
        )

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

        now = utcnow()
        meeting.notice_version = payload.notice_version.strip()
        meeting.notice_confirmed_at = now
        meeting.notice_confirmed_by_user_id = ctx.user.id
        if meeting.recording_state == "idle":
            meeting.recording_state = "notice_confirmed"

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="meeting.recording_notice.confirm",
            resource_type="meeting",
            resource_id=meeting.id,
            result="succeeded",
            metadata={
                "notice_version": meeting.notice_version,
                "voice_cloning_consent_granted": False,
            },
        )
        db.commit()
        db.refresh(meeting)

        return {
            "meeting_id": meeting.id,
            "recording_state": meeting.recording_state,
            "notice_version": meeting.notice_version,
            "notice_confirmed_at": meeting.notice_confirmed_at.isoformat(),
            "notice_confirmed_by_user_id": meeting.notice_confirmed_by_user_id,
        }


@router.post("/{meeting_id}/uploads", status_code=status.HTTP_201_CREATED)
def initiate_upload_session(
    meeting_id: str,
    payload: InitiateUploadSessionRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ctx: TenantAccessContext = Depends(require_permission("meeting.record")),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    normalized_mime = validate_media_mime_type(payload.mime_type)

    if payload.declared_size_bytes > settings.upload_max_file_size_bytes:
        raise NexusAPIError(
            status_code=413,
            code="upload_file_too_large",
            message=(
                f"Declared size {payload.declared_size_bytes} exceeds plan limit "
                f"({settings.upload_max_file_size_bytes} bytes)."
            ),
        )

    chunk_size = payload.chunk_size_bytes or settings.upload_chunk_size_bytes
    total_chunks = max(1, math.ceil(payload.declared_size_bytes / chunk_size))
    idem_key = (
        idempotency_key.strip()
        if idempotency_key and idempotency_key.strip()
        else f"{meeting_id}:{payload.expected_sha256}"
    )

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

        if meeting.notice_confirmed_at is None:
            record_audit_event(
                db,
                organisation_id=ctx.organisation.id,
                actor_user_id=ctx.user.id,
                action="media.upload.initiate",
                resource_type="meeting",
                resource_id=meeting.id,
                result="denied",
                metadata={"reason": "recording_notice_unconfirmed"},
            )
            db.commit()
            raise NexusAPIError(
                status_code=403,
                code="recording_notice_required",
                message="Recording notice and consent reminder must be confirmed before uploading media.",
            )

        existing_session = db.scalars(
            select(MediaUploadSession).where(
                MediaUploadSession.organisation_id == ctx.organisation.id,
                MediaUploadSession.idempotency_key == idem_key,
            )
        ).first()
        if existing_session is not None:
            received = list(
                db.scalars(
                    select(MediaChunk.chunk_index)
                    .where(MediaChunk.upload_session_id == existing_session.id)
                    .order_by(MediaChunk.chunk_index.asc())
                ).all()
            )
            return {
                "upload_session_id": existing_session.id,
                "meeting_id": existing_session.meeting_id,
                "status": existing_session.status,
                "chunk_size_bytes": existing_session.chunk_size_bytes,
                "total_chunks": existing_session.total_chunks,
                "received_chunks": received,
                "expires_at": existing_session.expires_at.isoformat(),
            }

        active_count = (
            db.scalar(
                select(func.count(MediaUploadSession.id)).where(
                    MediaUploadSession.organisation_id == ctx.organisation.id,
                    MediaUploadSession.status.in_(("initiated", "uploading")),
                )
            )
            or 0
        )
        if active_count >= MAX_ACTIVE_UPLOADS_PER_TENANT:
            raise NexusAPIError(
                status_code=429,
                code="tenant_upload_quota_exceeded",
                message="Maximum concurrent active upload sessions reached for this organisation.",
            )

        session_rec = MediaUploadSession(
            organisation_id=ctx.organisation.id,
            meeting_id=meeting.id,
            initiated_by_user_id=ctx.user.id,
            file_name=payload.file_name.strip(),
            mime_type=normalized_mime,
            declared_size_bytes=payload.declared_size_bytes,
            chunk_size_bytes=chunk_size,
            total_chunks=total_chunks,
            expected_sha256=payload.expected_sha256.lower(),
            idempotency_key=idem_key,
            status="initiated",
            expires_at=utcnow() + timedelta(hours=4),
        )
        db.add(session_rec)
        meeting.recording_state = "uploading"
        db.flush()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="media.upload.initiate",
            resource_type="media_upload_session",
            resource_id=session_rec.id,
            result="succeeded",
            metadata={
                "meeting_id": meeting.id,
                "mime_type": normalized_mime,
                "declared_size_bytes": payload.declared_size_bytes,
                "total_chunks": total_chunks,
            },
        )
        db.commit()
        db.refresh(session_rec)

        return {
            "upload_session_id": session_rec.id,
            "meeting_id": session_rec.meeting_id,
            "status": session_rec.status,
            "chunk_size_bytes": session_rec.chunk_size_bytes,
            "total_chunks": session_rec.total_chunks,
            "received_chunks": [],
            "expires_at": session_rec.expires_at.isoformat(),
        }


@router.put("/{meeting_id}/uploads/{session_id}/chunks/{chunk_index}")
def upload_media_chunk(
    meeting_id: str,
    session_id: str,
    chunk_index: int,
    payload: UploadChunkRequest,
    ctx: TenantAccessContext = Depends(require_permission("meeting.record")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Uploads an individual chunk with SHA-256 verification and chunk-0 magic-byte validation.
    Duplicate uploads of the same chunk_index with the same SHA-256 are idempotent.
    """
    try:
        chunk_bytes = base64.b64decode(payload.data_base64, validate=True)
    except Exception as exc:
        raise NexusAPIError(
            status_code=400,
            code="invalid_chunk_encoding",
            message="Chunk payload must be valid base64.",
        ) from exc

    computed_sha256 = hashlib.sha256(chunk_bytes).hexdigest()
    if computed_sha256 != payload.sha256_checksum.lower():
        raise NexusAPIError(
            status_code=400,
            code="chunk_checksum_mismatch",
            message="Chunk SHA-256 checksum does not match uploaded bytes.",
        )

    storage = get_private_storage()

    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        upload_session = db.scalars(
            select(MediaUploadSession).where(
                MediaUploadSession.id == session_id,
                MediaUploadSession.meeting_id == meeting_id,
            )
        ).first()
        if upload_session is None:
            raise NexusAPIError(
                status_code=404,
                code="upload_session_not_found",
                message="Upload session not found in the active organisation.",
            )

        if chunk_index < 0 or chunk_index >= upload_session.total_chunks:
            raise NexusAPIError(
                status_code=400,
                code="invalid_chunk_index",
                message=f"chunk_index must be between 0 and {upload_session.total_chunks - 1}.",
            )

        if chunk_index == 0:
            validate_media_magic_bytes(upload_session.mime_type, chunk_bytes[:32])

        existing_chunk = db.scalars(
            select(MediaChunk).where(
                MediaChunk.upload_session_id == upload_session.id,
                MediaChunk.chunk_index == chunk_index,
            )
        ).first()
        if existing_chunk is not None:
            if existing_chunk.sha256_checksum == computed_sha256:
                return {
                    "upload_session_id": upload_session.id,
                    "chunk_index": chunk_index,
                    "sha256_checksum": computed_sha256,
                    "size_bytes": existing_chunk.size_bytes,
                    "idempotent_replay": True,
                }
            raise NexusAPIError(
                status_code=409,
                code="conflicting_chunk_overwrite",
                message="Chunk index already exists with a different checksum.",
            )

        chunk_key = (
            f"tenants/{ctx.organisation.id}/meetings/{meeting_id}"
            f"/uploads/{upload_session.id}/chunk_{chunk_index:05d}"
        )
        storage.put_bytes(
            organisation_id=ctx.organisation.id,
            object_key=chunk_key,
            data=chunk_bytes,
        )

        chunk_rec = MediaChunk(
            organisation_id=ctx.organisation.id,
            upload_session_id=upload_session.id,
            chunk_index=chunk_index,
            size_bytes=len(chunk_bytes),
            sha256_checksum=computed_sha256,
            object_key=chunk_key,
        )
        db.add(chunk_rec)
        upload_session.status = "uploading"
        db.commit()

        return {
            "upload_session_id": upload_session.id,
            "chunk_index": chunk_index,
            "sha256_checksum": computed_sha256,
            "size_bytes": len(chunk_bytes),
            "idempotent_replay": False,
        }


@router.get("/{meeting_id}/uploads/{session_id}")
def get_upload_session_status(
    meeting_id: str,
    session_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.record")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Returns upload session state and received chunk indices so interrupted uploads
    can resume deterministically from the first missing chunk.
    """
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        upload_session = db.scalars(
            select(MediaUploadSession).where(
                MediaUploadSession.id == session_id,
                MediaUploadSession.meeting_id == meeting_id,
            )
        ).first()
        if upload_session is None:
            raise NexusAPIError(
                status_code=404,
                code="upload_session_not_found",
                message="Upload session not found in the active organisation.",
            )

        chunks = list(
            db.scalars(
                select(MediaChunk)
                .where(MediaChunk.upload_session_id == upload_session.id)
                .order_by(MediaChunk.chunk_index.asc())
            ).all()
        )
        received_indices = [c.chunk_index for c in chunks]
        missing_indices = [
            i
            for i in range(upload_session.total_chunks)
            if i not in set(received_indices)
        ]

        return {
            "upload_session_id": upload_session.id,
            "meeting_id": upload_session.meeting_id,
            "status": upload_session.status,
            "total_chunks": upload_session.total_chunks,
            "received_chunks": received_indices,
            "missing_chunks": missing_indices,
            "bytes_received": sum(c.size_bytes for c in chunks),
            "declared_size_bytes": upload_session.declared_size_bytes,
        }


@router.post(
    "/{meeting_id}/uploads/{session_id}/complete",
    status_code=status.HTTP_202_ACCEPTED,
)
def finalise_upload_session(
    meeting_id: str,
    session_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.record")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Finalises a chunked upload session idempotently:
    1. Verifies all chunks 0..total_chunks-1 have arrived.
    2. Reassembles the original media and validates total size & full-file SHA-256 checksum.
    3. Stores the immutable original in `media_assets` (separate from derivatives).
    4. Queues and runs the asynchronous `media.validate_and_normalise` worker job.
    """
    storage = get_private_storage()

    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        upload_session = db.scalars(
            select(MediaUploadSession).where(
                MediaUploadSession.id == session_id,
                MediaUploadSession.meeting_id == meeting_id,
            )
        ).first()
        if upload_session is None:
            raise NexusAPIError(
                status_code=404,
                code="upload_session_not_found",
                message="Upload session not found in the active organisation.",
            )

        existing_asset = db.scalars(
            select(MediaAsset).where(
                MediaAsset.upload_session_id == upload_session.id
            )
        ).first()
        if existing_asset is not None:
            proc_job = db.scalars(
                select(MediaProcessingJob).where(
                    MediaProcessingJob.media_asset_id == existing_asset.id
                )
            ).first()
            return {
                "upload_session_id": upload_session.id,
                "media_asset_id": existing_asset.id,
                "job_id": proc_job.background_job_id if proc_job else None,
                "status": existing_asset.status,
                "idempotent_replay": True,
            }

        chunks = list(
            db.scalars(
                select(MediaChunk)
                .where(MediaChunk.upload_session_id == upload_session.id)
                .order_by(MediaChunk.chunk_index.asc())
            ).all()
        )
        if len(chunks) != upload_session.total_chunks:
            raise NexusAPIError(
                status_code=400,
                code="incomplete_upload_chunks",
                message=(
                    f"Expected {upload_session.total_chunks} chunks, "
                    f"but only {len(chunks)} have been uploaded."
                ),
            )

        assembled = b"".join(
            storage.get_bytes(
                organisation_id=ctx.organisation.id, object_key=c.object_key
            )
            for c in chunks
        )
        if len(assembled) != upload_session.declared_size_bytes:
            raise NexusAPIError(
                status_code=400,
                code="assembled_size_mismatch",
                message="Assembled media byte length does not match declared_size_bytes.",
            )

        full_sha256 = hashlib.sha256(assembled).hexdigest()
        if full_sha256 != upload_session.expected_sha256:
            raise NexusAPIError(
                status_code=400,
                code="final_checksum_mismatch",
                message="Assembled file SHA-256 does not match expected_sha256.",
            )

        validate_media_magic_bytes(upload_session.mime_type, assembled[:32])

        original_key = (
            f"tenants/{ctx.organisation.id}/meetings/{meeting_id}"
            f"/original/{upload_session.id}/{upload_session.file_name}"
        )
        storage.put_bytes(
            organisation_id=ctx.organisation.id,
            object_key=original_key,
            data=assembled,
        )

        retention_until = utcnow() + timedelta(days=ctx.organisation.retention_days)
        asset = MediaAsset(
            organisation_id=ctx.organisation.id,
            meeting_id=meeting_id,
            upload_session_id=upload_session.id,
            uploaded_by_user_id=ctx.user.id,
            object_key=original_key,
            file_name=upload_session.file_name,
            mime_type=upload_session.mime_type,
            size_bytes=len(assembled),
            sha256_checksum=full_sha256,
            retention_until=retention_until,
            status="uploaded",
        )
        db.add(asset)
        upload_session.status = "completed"

        meeting = db.scalars(
            select(Meeting).where(Meeting.id == meeting_id)
        ).first()
        if meeting is not None:
            meeting.recording_state = "processing"
        db.flush()

        bg_job = enqueue_tenant_job(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            job_type="media.validate_and_normalise",
            source_entity_type="media_asset",
            source_entity_id=asset.id,
            idempotency_key=f"media-norm:{asset.id}",
        )

        proc_job = MediaProcessingJob(
            organisation_id=ctx.organisation.id,
            media_asset_id=asset.id,
            background_job_id=bg_job.id,
            stage="validate_and_normalise",
            status="queued",
        )
        db.add(proc_job)

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="media.upload.complete",
            resource_type="media_asset",
            resource_id=asset.id,
            result="succeeded",
            metadata={
                "meeting_id": meeting_id,
                "size_bytes": asset.size_bytes,
                "sha256_checksum": asset.sha256_checksum,
                "job_id": bg_job.id,
            },
        )
        db.commit()

    # Execute validation and derivative generation in isolated worker tenant context
    run_media_validation_and_normalisation_worker(
        db,
        background_job_id=bg_job.id,
        organisation_id=ctx.organisation.id,
        actor_user_id=ctx.user.id,
        storage=storage,
    )
    db.refresh(asset)

    return {
        "upload_session_id": upload_session.id,
        "media_asset_id": asset.id,
        "job_id": bg_job.id,
        "status": asset.status,
        "idempotent_replay": False,
    }


@router.get("/{meeting_id}/media")
def list_meeting_media(
    meeting_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
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

        assets = list(
            db.scalars(
                select(MediaAsset).where(MediaAsset.meeting_id == meeting_id)
            ).all()
        )
        derivatives = list(
            db.scalars(
                select(MediaDerivative).where(
                    MediaDerivative.meeting_id == meeting_id
                )
            ).all()
        )
        deriv_by_asset: dict[str, list[dict]] = {}
        for d in derivatives:
            deriv_by_asset.setdefault(d.media_asset_id, []).append(
                {
                    "id": d.id,
                    "kind": d.kind,
                    "mime_type": d.mime_type,
                    "size_bytes": d.size_bytes,
                    "sha256_checksum": d.sha256_checksum,
                    "processing_version": d.processing_version,
                }
            )

        return {
            "meeting_id": meeting_id,
            "items": [
                {
                    "id": a.id,
                    "meeting_id": a.meeting_id,
                    "file_name": a.file_name,
                    "mime_type": a.mime_type,
                    "size_bytes": a.size_bytes,
                    "sha256_checksum": a.sha256_checksum,
                    "codec": a.codec,
                    "duration_ms": a.duration_ms,
                    "sample_rate_hz": a.sample_rate_hz,
                    "channels": a.channels,
                    "status": a.status,
                    "retention_until": a.retention_until.isoformat(),
                    "derivatives": deriv_by_asset.get(a.id, []),
                }
                for a in assets
            ],
        }


@router.get("/{meeting_id}/transcripts")
def list_meeting_transcripts(
    meeting_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Lists transcripts for a meeting in the active organisation (newest first)
    so clients can discover existing transcripts without knowing a transcript ID.
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

        transcripts = list(
            db.scalars(
                select(Transcript)
                .where(Transcript.meeting_id == meeting_id)
                .order_by(Transcript.created_at.desc(), Transcript.id.asc())
            ).all()
        )

        return {
            "meeting_id": meeting_id,
            "items": [
                {
                    "id": t.id,
                    "meeting_id": t.meeting_id,
                    "media_asset_id": t.media_asset_id,
                    "status": t.status,
                    "language_code": t.language_code,
                    "detected_language": t.detected_language,
                    "asr_model_id": t.asr_model_id,
                    "current_revision_number": t.current_revision_number,
                    "created_at": t.created_at.isoformat(),
                    "updated_at": t.updated_at.isoformat(),
                }
                for t in transcripts
            ],
        }
