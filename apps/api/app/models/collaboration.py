from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantScopedMixin
from app.models.foundation import new_uuid, utcnow


class MeetingComment(Base, TenantScopedMixin):
    __tablename__ = "meeting_comments"
    __table_args__ = (
        Index("ix_meeting_comments_org_meeting", "organisation_id", "meeting_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ShareGrant(Base, TenantScopedMixin):
    """Time-limited, revocable share grant for records inside/outside the org."""

    __tablename__ = "share_grants"
    __table_args__ = (
        Index("ix_share_grants_org_resource", "organisation_id", "resource_type", "resource_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    grantee_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    grantee_organisation_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("organisations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    permission: Mapped[str] = mapped_column(String(32), nullable=False, default="view")
    granted_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Notification(Base, TenantScopedMixin):
    """Privacy-safe notification: no meeting content in preview payload."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_org_user", "organisation_id", "recipient_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    recipient_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_text: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ApprovalWorkflow(Base, TenantScopedMixin):
    """Review/approval state machine for records (summary minutes, exports, etc.)."""

    __tablename__ = "approval_workflows"
    __table_args__ = (
        Index("ix_approval_workflows_org_resource", "organisation_id", "resource_type", "resource_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    decided_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    decision_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ActionAssignment(Base, TenantScopedMixin):
    """Assignment of an AI-extracted action item to an accountable user."""

    __tablename__ = "action_assignments"
    __table_args__ = (
        Index("ix_action_assignments_org_action", "organisation_id", "action_item_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    action_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("action_items.id", ondelete="CASCADE"), nullable=False
    )
    assigned_to_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class IntegrationEvent(Base, TenantScopedMixin):
    __tablename__ = "integration_events"
    __table_args__ = (
        Index("ix_integration_events_org_provider", "organisation_id", "provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
