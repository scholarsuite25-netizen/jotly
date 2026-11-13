import hashlib
import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.correlation import get_correlation_id
from app.models.foundation import AuditLog, utcnow

GENESIS_HASH = "0" * 64

FORBIDDEN_SENSITIVE_AUDIT_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "transcript",
        "transcript_text",
        "raw_audio",
        "voice_sample",
        "audio_bytes",
    }
)


def sanitize_audit_metadata(metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    """
    Recursively strips/redacts sensitive keys (tokens, secrets, raw transcript/voice samples)
    so audit logs never leak confidential user content or credentials.
    """
    if not metadata:
        return {}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = str(key).lower()
        if any(forbidden in lowered for forbidden in FORBIDDEN_SENSITIVE_AUDIT_KEYS):
            clean[key] = "[REDACTED]"
        elif isinstance(value, dict):
            clean[key] = sanitize_audit_metadata(value)
        else:
            clean[key] = value
    return clean


def compute_audit_entry_hash(
    *,
    organisation_id: str,
    actor_user_id: Optional[str],
    action: str,
    resource_type: str,
    resource_id: str,
    result: str,
    correlation_id: str,
    metadata_json: str,
    previous_hash: str,
    created_at_iso: str,
) -> str:
    payload = "|".join(
        [
            organisation_id,
            actor_user_id or "anonymous",
            action,
            resource_type,
            resource_id,
            result,
            correlation_id,
            metadata_json,
            previous_hash,
            created_at_iso,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_audit_event(
    db: Session,
    *,
    organisation_id: str,
    actor_user_id: Optional[str],
    action: str,
    resource_type: str,
    resource_id: str,
    result: str,
    metadata: Optional[dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
) -> AuditLog:
    """
    Records a tamper-evident, cryptographically hash-chained audit event scoped to organisation_id.
    """
    cid = correlation_id or get_correlation_id()
    sanitized = sanitize_audit_metadata(metadata)
    metadata_json = json.dumps(sanitized, sort_keys=True, separators=(",", ":"))

    last_entry = db.scalars(
        select(AuditLog)
        .where(AuditLog.organisation_id == organisation_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    ).first()

    previous_hash = last_entry.entry_hash if last_entry else GENESIS_HASH
    now = utcnow()
    created_iso = now.isoformat()

    entry_hash = compute_audit_entry_hash(
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        correlation_id=cid,
        metadata_json=metadata_json,
        previous_hash=previous_hash,
        created_at_iso=created_iso,
    )

    entry = AuditLog(
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        correlation_id=cid,
        metadata_json=metadata_json,
        previous_hash=previous_hash,
        entry_hash=entry_hash,
        created_at=now,
    )
    db.add(entry)
    db.flush()
    return entry


def verify_organisation_audit_chain(
    db: Session, organisation_id: str
) -> tuple[bool, int, Optional[str]]:
    """
    Verifies the integrity of the per-organisation SHA-256 audit log chain.
    Returns (is_valid, total_checked, broken_entry_id).
    """
    entries = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.organisation_id == organisation_id)
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        ).all()
    )

    expected_prev = GENESIS_HASH
    for entry in entries:
        if entry.previous_hash != expected_prev:
            return False, len(entries), entry.id

        created_dt = entry.created_at
        if created_dt.tzinfo is None:
            from datetime import timezone

            created_dt = created_dt.replace(tzinfo=timezone.utc)

        recomputed = compute_audit_entry_hash(
            organisation_id=entry.organisation_id,
            actor_user_id=entry.actor_user_id,
            action=entry.action,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            result=entry.result,
            correlation_id=entry.correlation_id,
            metadata_json=entry.metadata_json,
            previous_hash=entry.previous_hash,
            created_at_iso=created_dt.isoformat(),
        )
        if recomputed != entry.entry_hash:
            return False, len(entries), entry.id
        expected_prev = entry.entry_hash

    return True, len(entries), None
