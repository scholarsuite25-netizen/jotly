from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantAccessContext, require_permission
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.foundation import BackgroundJob, utcnow
from app.services.audit import record_audit_event

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job_status(
    job_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Retrieves a background job's status strictly within the caller's verified tenant context.
    Prevents cross-tenant job ID guessing (IDOR).
    """
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        job = db.scalars(
            select(BackgroundJob).where(BackgroundJob.id == job_id)
        ).first()
        if job is None:
            raise NexusAPIError(
                status_code=404,
                code="job_not_found",
                message="Background job not found in the active organisation.",
            )
        return {
            "id": job.id,
            "organisation_id": job.organisation_id,
            "job_type": job.job_type,
            "source_entity_type": job.source_entity_type,
            "source_entity_id": job.source_entity_id,
            "status": job.status,
            "progress": job.progress,
            "retry_count": job.retry_count,
            "max_retries": job.max_retries,
            "worker_version": job.worker_version,
            "error_code": job.error_code,
            "error_message": job.error_message,
        }


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.record")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        job = db.scalars(
            select(BackgroundJob).where(BackgroundJob.id == job_id)
        ).first()
        if job is None:
            raise NexusAPIError(
                status_code=404,
                code="job_not_found",
                message="Background job not found in the active organisation.",
            )
        if job.status in ("succeeded", "failed", "cancelled"):
            raise NexusAPIError(
                status_code=409,
                code="job_not_cancellable",
                message=f"Job in status '{job.status}' cannot be cancelled.",
            )
        job.status = "cancelled"
        job.completed_at = utcnow()
        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="job.cancel",
            resource_type="background_job",
            resource_id=job.id,
            result="succeeded",
        )
        db.commit()
        db.refresh(job)
        return {"id": job.id, "status": job.status}
