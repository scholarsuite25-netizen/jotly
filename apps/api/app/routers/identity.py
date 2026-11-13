from typing import Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUserContext,
    get_authenticated_user,
    resolve_user_organisation_access,
)
from app.core.db import get_db
from app.models.foundation import Organisation, Role, UserRole

router = APIRouter(tags=["identity"])


@router.get("/me")
def get_current_identity(
    x_organisation_id: Optional[str] = Header(default=None, alias="X-Organisation-ID"),
    auth: AuthenticatedUserContext = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Returns the authenticated Supabase Auth user identity, all verified organisation
    memberships, and — if an active organisation is selected or available — the
    resolved roles and granular permissions for that organisation.
    """
    memberships = list(
        db.scalars(
            select(UserRole).where(
                UserRole.user_id == auth.user.id,
                UserRole.status == "active",
            )
        ).all()
    )

    org_ids = list({m.organisation_id for m in memberships})
    orgs = (
        {
            o.id: o
            for o in db.scalars(
                select(Organisation).where(Organisation.id.in_(org_ids))
            ).all()
        }
        if org_ids
        else {}
    )
    role_ids = list({m.role_id for m in memberships})
    roles_by_id = (
        {
            r.id: r
            for r in db.scalars(select(Role).where(Role.id.in_(role_ids))).all()
        }
        if role_ids
        else {}
    )

    organisations_summary: dict[str, dict] = {}
    for m in memberships:
        org = orgs.get(m.organisation_id)
        role = roles_by_id.get(m.role_id)
        if not org or not role:
            continue
        entry = organisations_summary.setdefault(
            org.id,
            {
                "id": org.id,
                "slug": org.slug,
                "name": org.name,
                "roles": [],
            },
        )
        if role.code not in entry["roles"]:
            entry["roles"].append(role.code)

    active_org_payload = None
    target_org_id = x_organisation_id or (org_ids[0] if len(org_ids) == 1 else None)
    if target_org_id:
        tenant_ctx = resolve_user_organisation_access(
            db,
            user=auth.user,
            claims=auth.claims,
            target_organisation_id=target_org_id,
            action_description="GET /api/v1/me",
        )
        active_org_payload = {
            "id": tenant_ctx.organisation.id,
            "slug": tenant_ctx.organisation.slug,
            "name": tenant_ctx.organisation.name,
            "roles": sorted(tenant_ctx.roles),
            "permissions": sorted(tenant_ctx.permissions),
        }

    return {
        "user": {
            "id": auth.user.id,
            "supabase_sub": auth.user.supabase_sub,
            "email": auth.user.email,
            "full_name": auth.user.full_name,
            "mfa_verified": auth.user.mfa_verified,
        },
        "organisations": list(organisations_summary.values()),
        "active_organisation": active_org_payload,
    }
