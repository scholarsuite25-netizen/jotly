from datetime import timedelta
import hashlib
import re
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUserContext,
    TenantAccessContext,
    get_authenticated_user,
    get_active_tenant_context,
    require_permission,
)
from app.auth.permissions import DEFAULT_ROLE_BUNDLES, bootstrap_organisation_roles
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.foundation import (
    Invitation,
    Organisation,
    UserRole,
    Workspace,
    utcnow,
)
from app.services.audit import record_audit_event
from app.services.email import EmailMessage, MultiProviderEmailService

router = APIRouter(prefix="/organisations", tags=["organisations"])


class CreateOrganisationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=120)
    retention_days: int = Field(default=365, ge=30, le=3650)


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)


class CreateInvitationRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    role_code: str = Field(default="participant", max_length=80)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or f"org-{uuid.uuid4().hex[:8]}"


@router.post("", status_code=status.HTTP_201_CREATED)
def create_organisation(
    payload: CreateOrganisationRequest,
    auth: AuthenticatedUserContext = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Creates a new tenant organisation, seeds canonical NEXUS roles & permissions,
    assigns the creator as `organisation_admin`, creates a Default Workspace,
    and writes the genesis tamper-evident audit event.
    """
    slug = _slugify(payload.slug or payload.name)
    existing = db.scalars(
        select(Organisation).where(Organisation.slug == slug)
    ).first()
    if existing is not None:
        raise NexusAPIError(
            status_code=409,
            code="organisation_slug_exists",
            message=f"Organisation slug '{slug}' is already in use.",
        )

    org = Organisation(
        name=payload.name.strip(),
        slug=slug,
        status="active",
        retention_days=payload.retention_days,
    )
    db.add(org)
    db.flush()

    roles = bootstrap_organisation_roles(db, org.id)
    admin_role = roles["organisation_admin"]

    membership = UserRole(
        organisation_id=org.id,
        user_id=auth.user.id,
        role_id=admin_role.id,
        status="active",
    )
    db.add(membership)

    default_workspace = Workspace(
        organisation_id=org.id,
        name="General Workspace",
        description="Default workspace for organisation meetings and documents.",
    )
    db.add(default_workspace)
    db.flush()

    record_audit_event(
        db,
        organisation_id=org.id,
        actor_user_id=auth.user.id,
        action="organisation.create",
        resource_type="organisation",
        resource_id=org.id,
        result="succeeded",
        metadata={"slug": org.slug, "retention_days": org.retention_days},
    )
    db.commit()
    db.refresh(org)

    return {
        "id": org.id,
        "slug": org.slug,
        "name": org.name,
        "status": org.status,
        "retention_days": org.retention_days,
        "default_workspace_id": default_workspace.id,
    }


@router.get("/{org_id}")
def get_organisation(
    org_id: str,
    ctx: TenantAccessContext = Depends(get_active_tenant_context),
) -> dict:
    return {
        "id": ctx.organisation.id,
        "slug": ctx.organisation.slug,
        "name": ctx.organisation.name,
        "status": ctx.organisation.status,
        "retention_days": ctx.organisation.retention_days,
        "roles": sorted(ctx.roles),
        "permissions": sorted(ctx.permissions),
    }


@router.post("/{org_id}/workspaces", status_code=status.HTTP_201_CREATED)
def create_workspace(
    org_id: str,
    payload: CreateWorkspaceRequest,
    ctx: TenantAccessContext = Depends(require_permission("tenant.admin")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        workspace = Workspace(
            organisation_id=ctx.organisation.id,
            name=payload.name.strip(),
            description=payload.description,
        )
        db.add(workspace)
        db.flush()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="workspace.create",
            resource_type="workspace",
            resource_id=workspace.id,
            result="succeeded",
            metadata={"name": workspace.name},
        )
        db.commit()
        db.refresh(workspace)

        return {
            "id": workspace.id,
            "organisation_id": workspace.organisation_id,
            "name": workspace.name,
            "description": workspace.description,
        }


@router.get("/{org_id}/workspaces")
def list_workspaces(
    org_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        workspaces = list(
            db.scalars(
                select(Workspace).order_by(Workspace.created_at.asc())
            ).all()
        )
        return {
            "items": [
                {
                    "id": w.id,
                    "organisation_id": w.organisation_id,
                    "name": w.name,
                    "description": w.description,
                }
                for w in workspaces
            ]
        }


@router.get("/{org_id}/workspaces/{workspace_id}")
def get_workspace_by_id(
    org_id: str,
    workspace_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Fetches a specific workspace by ID inside the active tenant RLS context.
    Even if a user in Tenant A guesses a valid workspace_id belonging to Tenant B,
    the RLS context + ORM tenant filter ensures it returns 404 Not Found.
    """
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        workspace = db.scalars(
            select(Workspace).where(Workspace.id == workspace_id)
        ).first()
        if workspace is None:
            raise NexusAPIError(
                status_code=404,
                code="workspace_not_found",
                message="Workspace not found in the active organisation.",
            )
        return {
            "id": workspace.id,
            "organisation_id": workspace.organisation_id,
            "name": workspace.name,
            "description": workspace.description,
        }


@router.post("/{org_id}/invitations", status_code=status.HTTP_201_CREATED)
def create_invitation(
    org_id: str,
    payload: CreateInvitationRequest,
    ctx: TenantAccessContext = Depends(require_permission("tenant.admin")),
    db: Session = Depends(get_db),
) -> dict:
    if payload.role_code not in DEFAULT_ROLE_BUNDLES:
        raise NexusAPIError(
            status_code=400,
            code="invalid_role_code",
            message=f"Unknown role_code '{payload.role_code}'.",
        )

    raw_token = uuid.uuid4().hex
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    email_service = MultiProviderEmailService()

    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        delivery = email_service.send(
            EmailMessage(
                to_email=payload.email.strip().lower(),
                subject=f"Invitation to join {ctx.organisation.name} on NEXUS Meeting Intelligence",
                text_body=(
                    f"You have been invited to join '{ctx.organisation.name}' "
                    f"with role '{payload.role_code}'."
                ),
                category="organisation_invitation",
                organisation_id=ctx.organisation.id,
            )
        )

        invitation = Invitation(
            organisation_id=ctx.organisation.id,
            email=payload.email.strip().lower(),
            role_code=payload.role_code,
            invited_by_user_id=ctx.user.id,
            token_hash=token_hash,
            status="pending",
            email_provider=delivery.provider,
            expires_at=utcnow() + timedelta(days=7),
        )
        db.add(invitation)
        db.flush()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="organisation.invitation.create",
            resource_type="invitation",
            resource_id=invitation.id,
            result="succeeded",
            metadata={
                "invited_email": invitation.email,
                "role_code": invitation.role_code,
                "email_provider": delivery.provider,
            },
        )
        db.commit()
        db.refresh(invitation)

        return {
            "id": invitation.id,
            "organisation_id": invitation.organisation_id,
            "email": invitation.email,
            "role_code": invitation.role_code,
            "status": invitation.status,
            "email_provider": invitation.email_provider,
            "expires_at": invitation.expires_at.isoformat(),
        }
