from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.foundation import Permission, Role, RolePermission

CANONICAL_PERMISSIONS: dict[str, str] = {
    "meeting.view": "View authorised meeting records and metadata",
    "meeting.record": "Create meetings and capture or upload recordings",
    "transcript.edit": "Edit transcript segments and speaker labels",
    "transcript.export": "Export transcripts and meeting documents as DOCX/PDF",
    "document.share": "Share meeting documents and records within policy",
    "voice.clone.create": "Enrol a consent-verified personal voice profile (Phase 6 gated)",
    "voice.clone.use": "Request synthesis with an authorised voice profile (Phase 6 gated)",
    "voice.clone.revoke": "Revoke a personal voice profile or permission grant",
    "retention.manage": "Manage retention policies, legal holds, and deletion workflows",
    "audit.view": "View tamper-evident organisation audit and compliance logs",
    "tenant.admin": "Manage organisation settings, workspaces, invitations, and roles",
}

DEFAULT_ROLE_BUNDLES: dict[str, tuple[str, list[str]]] = {
    "organisation_admin": (
        "Organisation Administrator",
        [
            "meeting.view",
            "meeting.record",
            "transcript.edit",
            "transcript.export",
            "document.share",
            "voice.clone.revoke",
            "retention.manage",
            "audit.view",
            "tenant.admin",
        ],
    ),
    "meeting_admin": (
        "Meeting Administrator",
        [
            "meeting.view",
            "meeting.record",
            "transcript.edit",
            "transcript.export",
            "document.share",
        ],
    ),
    "department_manager": (
        "Department Manager",
        [
            "meeting.view",
            "meeting.record",
            "transcript.export",
            "document.share",
        ],
    ),
    "meeting_host": (
        "Meeting Host",
        [
            "meeting.view",
            "meeting.record",
            "transcript.edit",
            "transcript.export",
            "document.share",
        ],
    ),
    "participant": (
        "Participant",
        ["meeting.view"],
    ),
    "transcription_editor": (
        "Transcription Editor",
        ["meeting.view", "transcript.edit", "transcript.export"],
    ),
    "records_manager": (
        "Records Manager",
        ["meeting.view", "retention.manage", "audit.view"],
    ),
    "voice_profile_owner": (
        "Voice Profile Owner",
        ["meeting.view", "voice.clone.revoke"],
    ),
    "auditor": (
        "Auditor",
        ["audit.view"],
    ),
}


def ensure_canonical_permissions(db: Session) -> dict[str, Permission]:
    """Ensures all canonical permission records exist in the database."""
    existing = {
        p.code: p for p in db.scalars(select(Permission)).all()
    }
    for code, description in CANONICAL_PERMISSIONS.items():
        if code not in existing:
            perm = Permission(code=code, description=description)
            db.add(perm)
            db.flush()
            existing[code] = perm
    return existing


def bootstrap_organisation_roles(
    db: Session, organisation_id: str
) -> dict[str, Role]:
    """Creates the standard NEXUS RBAC roles and permission bindings for a new organisation."""
    perms = ensure_canonical_permissions(db)
    existing_roles = {
        r.code: r
        for r in db.scalars(
            select(Role).where(Role.organisation_id == organisation_id)
        ).all()
    }

    for role_code, (role_name, perm_codes) in DEFAULT_ROLE_BUNDLES.items():
        if role_code in existing_roles:
            continue
        role = Role(
            organisation_id=organisation_id,
            code=role_code,
            name=role_name,
            is_system=True,
        )
        db.add(role)
        db.flush()
        for p_code in perm_codes:
            db.add(
                RolePermission(
                    role_id=role.id,
                    permission_id=perms[p_code].id,
                )
            )
        db.flush()
        existing_roles[role_code] = role

    return existing_roles
