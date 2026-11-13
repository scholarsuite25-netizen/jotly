from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantAccessContext, require_permission
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.meetings_media import MediaAsset
from app.models.transcription import (
    Transcript,
    TranscriptSegment,
    TranscriptSpeaker,
)
from app.workers.context import enqueue_tenant_job
from app.workers.transcription_worker import run_transcription_worker

router = APIRouter(prefix="/media", tags=["transcription"])


class TranscriptionRequest(BaseModel):
    language_code: str = Field(default="en", min_length=2, max_length=16)
    enable_diarisation: bool = Field(default=False)


@router.post("/{asset_id}/transcriptions", status_code=status.HTTP_202_ACCEPTED)
def queue_transcription(
    asset_id: str,
    payload: TranscriptionRequest,
    ctx: TenantAccessContext = Depends(require_permission("meeting.record")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Queues an idempotent ASR transcription job for a validated media asset.
    Diarisation output is always stored and served as model suggestions only.
    """
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        asset = db.scalars(
            select(MediaAsset).where(MediaAsset.id == asset_id)
        ).first()
        if asset is None:
            raise NexusAPIError(
                status_code=404,
                code="media_asset_not_found",
                message="Media asset not found in the active organisation.",
            )
        if asset.status != "validated":
            raise NexusAPIError(
                status_code=409,
                code="media_not_ready_for_transcription",
                message=f"Media asset status '{asset.status}' must be 'validated' before transcription.",
            )

        bg_job = enqueue_tenant_job(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            job_type="transcription.run",
            source_entity_type="media_asset",
            source_entity_id=asset.id,
            idempotency_key=f"transcription:{asset.id}",
        )
        return {
            "job_id": bg_job.id,
            "media_asset_id": asset.id,
            "language_code": payload.language_code,
            "enable_diarisation": payload.enable_diarisation,
            "status": bg_job.status,
        }


@router.post("/{asset_id}/transcriptions/{job_id}/execute", status_code=status.HTTP_200_OK)
def execute_transcription_job(
    asset_id: str,
    job_id: str,
    payload: TranscriptionRequest,
    ctx: TenantAccessContext = Depends(require_permission("meeting.record")),
    db: Session = Depends(get_db),
) -> dict:
    transcript = run_transcription_worker(
        db,
        background_job_id=job_id,
        organisation_id=ctx.organisation.id,
        actor_user_id=ctx.user.id,
        language_code=payload.language_code,
        enable_diarisation=payload.enable_diarisation,
    )
    return {
        "transcript_id": transcript.id,
        "media_asset_id": transcript.media_asset_id,
        "detected_language": transcript.detected_language,
        "language_confidence": transcript.language_confidence,
        "asr_model_id": transcript.asr_model_id,
        "diarisation_enabled": transcript.diarisation_enabled,
        "status": transcript.status,
    }
