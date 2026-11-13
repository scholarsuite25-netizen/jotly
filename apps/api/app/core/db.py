from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generator, Optional

from sqlalchemy import ForeignKey, String, create_engine, event, text
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
    with_loader_criteria,
)

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Canonical SQLAlchemy declarative base."""


class TenantScopedMixin:
    """Mixin for entities owned by a specific organisation_id, used by ORM RLS loader criteria."""

    organisation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organisations.id", ondelete="RESTRICT"),
        nullable=False,
    )


_current_org_id_ctx: ContextVar[Optional[str]] = ContextVar(
    "current_organisation_id", default=None
)
_current_user_id_ctx: ContextVar[Optional[str]] = ContextVar(
    "current_user_id", default=None
)
_rls_enforced_ctx: ContextVar[bool] = ContextVar("rls_enforced", default=False)


def get_current_organisation_id() -> Optional[str]:
    return _current_org_id_ctx.get()


def get_current_user_id() -> Optional[str]:
    return _current_user_id_ctx.get()


def is_rls_enforced() -> bool:
    return _rls_enforced_ctx.get()


@contextmanager
def tenant_db_context(
    db: Session,
    organisation_id: str,
    user_id: Optional[str] = None,
) -> Generator[Session, None, None]:
    """
    Establishes server-verified tenant context on the database session.
    1. On PostgreSQL, executes SET LOCAL app.current_organisation_id and app.current_user_id
       so PostgreSQL Row-Level Security (RLS) policies enforce isolation at the engine level.
    2. Sets contextvars and SQLAlchemy loader criteria so every ORM SELECT/UPDATE/DELETE
       is automatically constrained to the verified organisation_id across all dialects.
    """
    if not organisation_id or not organisation_id.strip():
        raise ValueError("Verified organisation_id is required to enter tenant DB context.")

    token_org = _current_org_id_ctx.set(organisation_id)
    token_user = _current_user_id_ctx.set(user_id)
    token_rls = _rls_enforced_ctx.set(True)

    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT set_config('app.current_organisation_id', :org_id, true)"),
            {"org_id": organisation_id},
        )
        db.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": user_id or ""},
        )

    try:
        yield db
    finally:
        if bind is not None and bind.dialect.name == "postgresql":
            db.execute(
                text("SELECT set_config('app.current_organisation_id', '', true)")
            )
            db.execute(text("SELECT set_config('app.current_user_id', '', true)"))
        _rls_enforced_ctx.reset(token_rls)
        _current_user_id_ctx.reset(token_user)
        _current_org_id_ctx.reset(token_org)


@event.listens_for(Session, "do_orm_execute")
def _enforce_orm_tenant_isolation(execute_state) -> None:
    """
    Defense-in-depth ORM-layer RLS enforcement:
    When tenant_db_context is active, automatically injects
    `organisation_id == current_organisation_id` on every SELECT against TenantScopedMixin models.
    """
    if (
        execute_state.is_select
        and not execute_state.is_column_load
        and not execute_state.is_relationship_load
        and _rls_enforced_ctx.get()
    ):
        active_org_id = _current_org_id_ctx.get()
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                TenantScopedMixin,
                lambda cls: cls.organisation_id == active_org_id,
                include_aliases=True,
            )
        )


@event.listens_for(Session, "before_flush")
def _enforce_write_tenant_isolation(session: Session, flush_context, instances) -> None:
    """
    Prevents inserting or mutating a TenantScopedMixin record belonging to a different tenant
    while inside an active tenant_db_context.
    """
    if not _rls_enforced_ctx.get():
        return
    active_org_id = _current_org_id_ctx.get()
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, TenantScopedMixin):
            obj_org = getattr(obj, "organisation_id", None)
            if obj_org != active_org_id:
                raise PermissionError(
                    f"RLS write violation: object organisation_id '{obj_org}' "
                    f"does not match active tenant context '{active_org_id}'."
                )


settings = get_settings()
connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(
    settings.database_url,
    echo=settings.db_echo,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
