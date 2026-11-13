from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import NexusAPIError
from app.core.security import VerifiedSupabaseClaims, verify_supabase_jwt
from app.models.foundation import (
    Organisation,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.services.audit import record_audit_event

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUserContext:
    user: User
    claims: VerifiedSupabaseClaims


@dataclass(frozen=True)
class TenantAccessContext:
    user: User
    claims: VerifiedSupabaseClaims
    organisation: Organisation
    roles: frozenset[str]
    permissions: frozenset[str]

    def has_permission(self, permission_code: str) -> bool:
        return permission_code in self.permissions or "tenant.admin" in self.permissions


def get_authenticated_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedUserContext:
    """
    Validates the Bearer JWT issued by Supabase Auth and resolves/provisions
    the authenticated User record.
    """
    if credentials is None or not credentials.credentials:
        raise NexusAPIError(
            status_code=401,
            code="authentication_required",
            message="Missing Bearer authentication token.",
        )

    claims = verify_supabase_jwt(credentials.credentials)

    user = db.scalars(
        select(User).where(User.supabase_sub == claims.sub)
    ).first()
    if user is None:
        user = db.scalars(select(User).where(User.email == claims.email)).first()

    if user is None:
        user = User(
            supabase_sub=claims.sub,
            email=claims.email,
            full_name=claims.full_name,
            is_active=True,
            mfa_verified=claims.is_mfa_verified,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if user.mfa_verified != claims.is_mfa_verified:
            user.mfa_verified = claims.is_mfa_verified
            db.commit()
            db.refresh(user)

    if not user.is_active:
        raise NexusAPIError(
            status_code=403,
            code="account_suspended",
            message="User account is suspended.",
        )

    return AuthenticatedUserContext(user=user, claims=claims)


def resolve_user_organisation_access(
    db: Session,
    *,
    user: User,
    claims: VerifiedSupabaseClaims,
    target_organisation_id: str,
    action_description: str = "tenant.access",
) -> TenantAccessContext:
    """
    Authoritative server-side tenant membership and permission resolver.
    NEVER trusts a client-supplied organisation_id unless the authenticated user
    holds an active UserRole membership in that organisation in the database.
    Logs cross-tenant denial attempts to the target organisation's audit log if it exists.
    """
    org = db.scalars(
        select(Organisation).where(Organisation.id == target_organisation_id)
    ).first()

    active_memberships = list(
        db.scalars(
            select(UserRole).where(
                UserRole.organisation_id == target_organisation_id,
                UserRole.user_id == user.id,
                UserRole.status == "active",
            )
        ).all()
    )

    if org is None or org.status != "active" or not active_memberships:
        if org is not None:
            record_audit_event(
                db,
                organisation_id=org.id,
                actor_user_id=user.id,
                action=action_description,
                resource_type="organisation",
                resource_id=target_organisation_id,
                result="denied",
                metadata={"reason": "cross_tenant_or_unauthorised_membership"},
            )
            db.commit()

        raise NexusAPIError(
            status_code=403,
            code="tenant_access_denied",
            message="Access to the requested organisation is denied.",
        )

    role_ids = [m.role_id for m in active_memberships]
    roles = list(db.scalars(select(Role).where(Role.id.in_(role_ids))).all())
    role_codes = frozenset(r.code for r in roles)

    perm_rows = list(
        db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id.in_(role_ids))
        ).all()
    )
    permissions = frozenset(perm_rows)

    settings = get_settings()
    if (
        settings.require_admin_mfa
        and "tenant.admin" in permissions
        and not claims.is_mfa_verified
    ):
        record_audit_event(
            db,
            organisation_id=org.id,
            actor_user_id=user.id,
            action=action_description,
            resource_type="organisation",
            resource_id=org.id,
            result="denied",
            metadata={"reason": "admin_mfa_required"},
        )
        db.commit()
        raise NexusAPIError(
            status_code=403,
            code="mfa_required",
            message="Multi-factor authentication (aal2) is required for administrator actions.",
        )

    return TenantAccessContext(
        user=user,
        claims=claims,
        organisation=org,
        roles=role_codes,
        permissions=permissions,
    )


def get_active_tenant_context(
    request: Request,
    x_organisation_id: Optional[str] = Header(default=None, alias="X-Organisation-ID"),
    auth: AuthenticatedUserContext = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> TenantAccessContext:
    """
    Resolves the active organisation context from path parameter `org_id` or `X-Organisation-ID` header,
    or falls back to the user's sole active organisation membership.
    Always validates membership server-side against the database.
    """
    path_org_id = request.path_params.get("org_id")
    if path_org_id and x_organisation_id and path_org_id != x_organisation_id:
        raise NexusAPIError(
            status_code=403,
            code="conflicting_tenant_context",
            message="Path organisation ID conflicts with X-Organisation-ID header.",
        )

    target_org_id = path_org_id or x_organisation_id
    if not target_org_id:
        first_membership = db.scalars(
            select(UserRole).where(
                UserRole.user_id == auth.user.id,
                UserRole.status == "active",
            )
        ).first()
        if first_membership is None:
            raise NexusAPIError(
                status_code=403,
                code="no_active_organisation",
                message="User has no active organisation membership.",
            )
        target_org_id = first_membership.organisation_id

    return resolve_user_organisation_access(
        db,
        user=auth.user,
        claims=auth.claims,
        target_organisation_id=target_org_id,
        action_description=f"{request.method} {request.url.path}",
    )


def require_permission(
    permission_code: str,
) -> Callable[[TenantAccessContext, Session], TenantAccessContext]:
    """Dependency factory enforcing a specific granular RBAC permission within the verified tenant."""

    def _dependency(
        ctx: TenantAccessContext = Depends(get_active_tenant_context),
        db: Session = Depends(get_db),
    ) -> TenantAccessContext:
        if not ctx.has_permission(permission_code):
            record_audit_event(
                db,
                organisation_id=ctx.organisation.id,
                actor_user_id=ctx.user.id,
                action=f"permission.check.{permission_code}",
                resource_type="permission",
                resource_id=permission_code,
                result="denied",
                metadata={"required_permission": permission_code},
            )
            db.commit()
            raise NexusAPIError(
                status_code=403,
                code="insufficient_permissions",
                message=f"Missing required permission: {permission_code}",
            )
        return ctx

    return _dependency
