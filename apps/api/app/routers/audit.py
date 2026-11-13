import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantAccessContext, require_permission
from app.core.db import get_db, tenant_db_context
from app.models.foundation import AuditLog
from app.services.audit import verify_organisation_audit_chain

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("")
def list_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    ctx: TenantAccessContext = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Returns permitted audit events strictly isolated to the current organisation.
    Requires `audit.view` or `tenant.admin` permission.
    """
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        logs = list(
            db.scalars(
                select(AuditLog)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(limit)
            ).all()
        )
        return {
            "organisation_id": ctx.organisation.id,
            "items": [
                {
                    "id": log.id,
                    "organisation_id": log.organisation_id,
                    "actor_user_id": log.actor_user_id,
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "result": log.result,
                    "correlation_id": log.correlation_id,
                    "metadata": json.loads(log.metadata_json or "{}"),
                    "previous_hash": log.previous_hash,
                    "entry_hash": log.entry_hash,
                    "created_at": log.created_at.isoformat(),
                }
                for log in logs
            ],
        }


@router.get("/verify")
def verify_audit_chain_endpoint(
    ctx: TenantAccessContext = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
) -> dict:
    """Verifies the cryptographic SHA-256 hash chain for the current organisation's audit log."""
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        is_valid, count, broken_id = verify_organisation_audit_chain(
            db, ctx.organisation.id
        )
        return {
            "organisation_id": ctx.organisation.id,
            "chain_valid": is_valid,
            "entries_verified": count,
            "broken_entry_id": broken_id,
        }
