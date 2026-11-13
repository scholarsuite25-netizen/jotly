from typing import Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import tenant_db_context
from app.core.errors import NexusAPIError
from app.models.foundation import BackgroundJob, utcnow
from app.services.audit import record_audit_event

T = TypeVar("T")


def enqueue_tenant_job(
    db: Session,
    *,
    organisation_id: str,
    actor_user_id: str,
    job_type: str,
    source_entity_type: str,
    source_entity_id: str,
    idempotency_key: str,
) -> BackgroundJob:
    """
    Creates or returns an idempotent BackgroundJob strictly bound to the verified organisation_id.
    """
    with tenant_db_context(db, organisation_id=organisation_id, user_id=actor_user_id):
        existing = db.scalars(
            select(BackgroundJob).where(
                BackgroundJob.organisation_id == organisation_id,
                BackgroundJob.idempotency_key == idempotency_key,
            )
        ).first()
        if existing is not None:
            return existing

        job = BackgroundJob(
            organisation_id=organisation_id,
            job_type=job_type,
            source_entity_type=source_entity_type,
            source_entity_id=source_entity_id,
            status="queued",
            progress=0,
            idempotency_key=idempotency_key,
        )
        db.add(job)
        db.flush()

        record_audit_event(
            db,
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
            action="job.enqueue",
            resource_type="background_job",
            resource_id=job.id,
            result="succeeded",
            metadata={"job_type": job_type, "idempotency_key": idempotency_key},
        )
        db.commit()
        db.refresh(job)
        return job


def execute_job_in_tenant_context(
    db: Session,
    *,
    job_id: str,
    expected_organisation_id: str,
    handler: Callable[[Session, BackgroundJob], T],
) -> T:
    """
    Executes a background job strictly inside the explicit tenant context of `expected_organisation_id`.
    If the job does not exist in that tenant (e.g., cross-tenant queue mismatch), execution is blocked.
    """
    with tenant_db_context(db, organisation_id=expected_organisation_id):
        job = db.scalars(
            select(BackgroundJob).where(BackgroundJob.id == job_id)
        ).first()
        if job is None or job.organisation_id != expected_organisation_id:
            raise NexusAPIError(
                status_code=403,
                code="worker_tenant_isolation_violation",
                message="Background worker rejected job outside its declared tenant context.",
            )

        job.status = "running"
        job.started_at = utcnow()
        db.commit()

        try:
            result = handler(db, job)
            job.status = "succeeded"
            job.progress = 100
            job.completed_at = utcnow()
            db.commit()
            return result
        except Exception as exc:
            job.retry_count += 1
            job.status = "failed"
            job.error_code = "worker_execution_failed"
            job.error_message = "Job processing failed safely."
            db.commit()
            raise exc
