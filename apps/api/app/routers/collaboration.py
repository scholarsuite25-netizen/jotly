"""Collaboration router: comments, share grants, notifications, approvals, assignments."""

from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantAccessContext, get_active_tenant_context, require_permission
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.foundation import utcnow
from app.models.collaboration import (
    ActionAssignment,
    ApprovalWorkflow,
    IntegrationEvent,
    MeetingComment,
    Notification,
    ShareGrant,
)
from app.models.intelligence import ActionItem, MeetingSummary
from app.models.meetings_media import Meeting
from app.services.audit import record_audit_event

router = APIRouter(tags=["collaboration"])

ALLOWED_PERMISSIONS: frozenset[str] = frozenset({"view", "comment", "edit"})


def create_notification(
    db: Session,
    *,
    organisation_id: str,
    recipient_user_id: str,
    notification_type: str,
    resource_type: str,
    resource_id: str,
    preview_text: str = "",
) -> Notification:
    """Privacy-safe notification: never embeds meeting content in the preview payload."""
    notification = Notification(
        organisation_id=organisation_id,
        recipient_user_id=recipient_user_id,
        notification_type=notification_type,
        resource_type=resource_type,
        resource_id=resource_id,
        preview_text=preview_text[:255],
    )
    db.add(notification)
    db.flush()
    return notification


class CommentBody(BaseModel):
    comment_text: str = Field(min_length=1, max_length=5000)


@router.post("/meetings/{meeting_id}/comments", status_code=status.HTTP_201_CREATED)
def add_meeting_comment(
    meeting_id: str,
    payload: CommentBody,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        meeting = db.scalars(
            select(Meeting).where(Meeting.id == meeting_id)
        ).first()
        if meeting is None:
            raise NexusAPIError(
                status_code=404,
                code="meeting_not_found",
                message="Meeting not found in the active organisation.",
            )
        comment = MeetingComment(
            organisation_id=ctx.organisation.id,
            meeting_id=meeting.id,
            author_user_id=ctx.user.id,
            comment_text=payload.comment_text.strip(),
        )
        db.add(comment)
        db.flush()

        # Notify the meeting host without leaking comment content in preview
        create_notification(
            db,
            organisation_id=ctx.organisation.id,
            recipient_user_id=meeting.host_user_id,
            notification_type="meeting.comment_added",
            resource_type="meeting",
            resource_id=meeting.id,
            preview_text=f"New comment on '{meeting.title}'",
        )
        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="collaboration.comment.add",
            resource_type="meeting_comment",
            resource_id=comment.id,
            result="succeeded",
        )
        db.commit()
        db.refresh(comment)
        return {
            "comment_id": comment.id,
            "meeting_id": comment.meeting_id,
            "author_user_id": comment.author_user_id,
            "comment_text": comment.comment_text,
            "created_at": comment.created_at.isoformat(),
        }


class ShareGrantBody(BaseModel):
    resource_type: str = Field(min_length=3, max_length=64)
    resource_id: str = Field(min_length=1, max_length=64)
    grantee_user_id: str = Field(min_length=1, max_length=36)
    grantee_organisation_id: str | None = Field(default=None, max_length=36)
    permission: str = Field(default="view", max_length=32)
    expires_in_days: int = Field(default=7, ge=1, le=365)


@router.post("/share-grants", status_code=status.HTTP_201_CREATED)
def create_share_grant(
    payload: ShareGrantBody,
    ctx: TenantAccessContext = Depends(require_permission("document.share")),
    db: Session = Depends(get_db),
) -> dict:
    if payload.permission not in ALLOWED_PERMISSIONS:
        raise NexusAPIError(
            status_code=400,
            code="invalid_share_permission",
            message=f"Permission must be one of {sorted(ALLOWED_PERMISSIONS)}.",
        )
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        grant = ShareGrant(
            organisation_id=ctx.organisation.id,
            resource_type=payload.resource_type,
            resource_id=payload.resource_id,
            grantee_user_id=payload.grantee_user_id,
            grantee_organisation_id=payload.grantee_organisation_id,
            permission=payload.permission,
            granted_by_user_id=ctx.user.id,
            expires_at=utcnow() + timedelta(days=payload.expires_in_days),
        )
        db.add(grant)
        db.flush()

        create_notification(
            db,
            organisation_id=ctx.organisation.id,
            recipient_user_id=payload.grantee_user_id,
            notification_type="share.grant.created",
            resource_type=payload.resource_type,
            resource_id=payload.resource_id,
            preview_text="A record was shared with you",
        )
        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="collaboration.share.grant",
            resource_type="share_grant",
            resource_id=grant.id,
            result="succeeded",
            metadata={
                "resource_type": payload.resource_type,
                "permission": payload.permission,
                "expires_at": grant.expires_at.isoformat(),
            },
        )
        db.commit()
        db.refresh(grant)
        return {
            "share_grant_id": grant.id,
            "resource_type": grant.resource_type,
            "resource_id": grant.resource_id,
            "grantee_user_id": grant.grantee_user_id,
            "permission": grant.permission,
            "expires_at": grant.expires_at.isoformat(),
            "revoked_at": None,
        }


@router.post("/share-grants/{grant_id}/revoke")
def revoke_share_grant(
    grant_id: str,
    ctx: TenantAccessContext = Depends(require_permission("document.share")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        grant = db.scalars(
            select(ShareGrant).where(
                ShareGrant.id == grant_id,
                ShareGrant.organisation_id == ctx.organisation.id,
            )
        ).first()
        if grant is None:
            raise NexusAPIError(
                status_code=404,
                code="share_grant_not_found",
                message="Share grant not found in the active organisation.",
            )
        if grant.granted_by_user_id != ctx.user.id and "tenant.admin" not in ctx.permissions:
            raise NexusAPIError(
                status_code=403,
                code="share_revoke_not_permitted",
                message="Only the grantor or an administrator can revoke a share grant.",
            )
        if grant.revoked_at is None:
            grant.revoked_at = utcnow()
            record_audit_event(
                db,
                organisation_id=ctx.organisation.id,
                actor_user_id=ctx.user.id,
                action="collaboration.share.revoke",
                resource_type="share_grant",
                resource_id=grant.id,
                result="succeeded",
            )
            db.commit()
            db.refresh(grant)
        return {
            "share_grant_id": grant.id,
            "revoked_at": grant.revoked_at.isoformat(),
        }


def assert_share_grant_valid(
    db: Session,
    *,
    organisation_id: str,
    resource_type: str,
    resource_id: str,
    grantee_user_id: str,
) -> ShareGrant:
    """Time-limited, revocable grant validation used by share-protected access."""
    grant = db.scalars(
        select(ShareGrant).where(
            ShareGrant.organisation_id == organisation_id,
            ShareGrant.resource_type == resource_type,
            ShareGrant.resource_id == resource_id,
            ShareGrant.grantee_user_id == grantee_user_id,
            ShareGrant.revoked_at.is_(None),
        )
    ).first()
    if grant is None:
        raise NexusAPIError(
            status_code=403,
            code="share_grant_required",
            message="No active share grant for this resource.",
        )
    if grant.expires_at < utcnow():
        raise NexusAPIError(
            status_code=403,
            code="share_grant_expired",
            message="Share grant has expired.",
        )
    return grant


class ApprovalDecisionBody(BaseModel):
    approve: bool = Field(...)
    decision_note: str | None = Field(default=None, max_length=500)


@router.post("/approvals", status_code=status.HTTP_201_CREATED)
def request_approval(
    resource_type: str,
    resource_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        workflow = ApprovalWorkflow(
            organisation_id=ctx.organisation.id,
            resource_type=resource_type,
            resource_id=resource_id,
            requested_by_user_id=ctx.user.id,
            status="pending",
        )
        db.add(workflow)
        db.flush()
        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="collaboration.approval.request",
            resource_type="approval_workflow",
            resource_id=workflow.id,
            result="succeeded",
            metadata={"resource_type": resource_type, "resource_id": resource_id},
        )
        db.commit()
        db.refresh(workflow)
        return {
            "approval_id": workflow.id,
            "resource_type": workflow.resource_type,
            "resource_id": workflow.resource_id,
            "status": workflow.status,
        }


@router.post("/approvals/{approval_id}/decide")
def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionBody,
    ctx: TenantAccessContext = Depends(require_permission("transcript.edit")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        workflow = db.scalars(
            select(ApprovalWorkflow).where(
                ApprovalWorkflow.id == approval_id,
                ApprovalWorkflow.organisation_id == ctx.organisation.id,
            )
        ).first()
        if workflow is None:
            raise NexusAPIError(
                status_code=404,
                code="approval_not_found",
                message="Approval workflow not found in the active organisation.",
            )
        if workflow.status != "pending":
            raise NexusAPIError(
                status_code=409,
                code="approval_already_decided",
                message=f"Approval workflow already '{workflow.status}'.",
            )
        if workflow.requested_by_user_id == ctx.user.id:
            raise NexusAPIError(
                status_code=403,
                code="self_approval_denied",
                message="Requesting user cannot approve their own workflow.",
            )

        workflow.status = "approved" if payload.approve else "rejected"
        workflow.decided_by_user_id = ctx.user.id
        workflow.decision_note = payload.decision_note
        workflow.decided_at = utcnow()

        if payload.approve and workflow.resource_type == "meeting_summary":
            summary = db.scalars(
                select(MeetingSummary).where(
                    MeetingSummary.id == workflow.resource_id
                )
            ).first()
            if summary is not None:
                summary.review_status = "approved"
                summary.reviewed_by_user_id = ctx.user.id
                summary.reviewed_at = utcnow()

        create_notification(
            db,
            organisation_id=ctx.organisation.id,
            recipient_user_id=workflow.requested_by_user_id,
            notification_type="approval.decided",
            resource_type=workflow.resource_type,
            resource_id=workflow.resource_id,
            preview_text=f"Approval {workflow.status}",
        )
        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="collaboration.approval.decide",
            resource_type="approval_workflow",
            resource_id=workflow.id,
            result="succeeded",
            metadata={"decision": workflow.status},
        )
        db.commit()
        db.refresh(workflow)
        return {
            "approval_id": workflow.id,
            "status": workflow.status,
            "decided_by_user_id": workflow.decided_by_user_id,
            "decided_at": workflow.decided_at.isoformat(),
        }


class AssignmentBody(BaseModel):
    action_item_id: str = Field(min_length=1, max_length=36)
    assigned_to_user_id: str = Field(min_length=1, max_length=36)
    due_in_days: int | None = Field(default=7, ge=1, le=365)


@router.post("/assignments", status_code=status.HTTP_201_CREATED)
def assign_action_item(
    payload: AssignmentBody,
    ctx: TenantAccessContext = Depends(require_permission("transcript.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """Explicit human assignment only — the system never auto-assigns action items."""
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        action_item = db.scalars(
            select(ActionItem).where(
                ActionItem.id == payload.action_item_id,
                ActionItem.organisation_id == ctx.organisation.id,
            )
        ).first()
        if action_item is None:
            raise NexusAPIError(
                status_code=404,
                code="action_item_not_found",
                message="Action item not found in the active organisation.",
            )
        assignment = ActionAssignment(
            organisation_id=ctx.organisation.id,
            action_item_id=action_item.id,
            assigned_to_user_id=payload.assigned_to_user_id,
            assigned_by_user_id=ctx.user.id,
            status="open",
            due_date=(
                utcnow() + timedelta(days=payload.due_in_days)
                if payload.due_in_days
                else None
            ),
        )
        db.add(assignment)
        db.flush()

        create_notification(
            db,
            organisation_id=ctx.organisation.id,
            recipient_user_id=payload.assigned_to_user_id,
            notification_type="action.assigned",
            resource_type="action_item",
            resource_id=action_item.id,
            preview_text="An action item was assigned to you",
        )
        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="collaboration.assignment.create",
            resource_type="action_assignment",
            resource_id=assignment.id,
            result="succeeded",
            metadata={"action_item_id": action_item.id},
        )
        db.commit()
        db.refresh(assignment)
        return {
            "assignment_id": assignment.id,
            "action_item_id": assignment.action_item_id,
            "assigned_to_user_id": assignment.assigned_to_user_id,
            "status": assignment.status,
            "due_date": assignment.due_date.isoformat() if assignment.due_date else None,
        }


@router.get("/notifications")
def list_notifications(
    ctx: TenantAccessContext = Depends(get_active_tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        notifications = list(
            db.scalars(
                select(Notification)
                .where(Notification.recipient_user_id == ctx.user.id)
                .order_by(Notification.created_at.desc())
                .limit(100)
            ).all()
        )
        return {
            "items": [
                {
                    "id": n.id,
                    "notification_type": n.notification_type,
                    "resource_type": n.resource_type,
                    "resource_id": n.resource_id,
                    "preview_text": n.preview_text,
                    "read_at": n.read_at.isoformat() if n.read_at else None,
                    "created_at": n.created_at.isoformat(),
                }
                for n in notifications
            ]
        }


class WebhookBody(BaseModel):
    provider: str = Field(min_length=2, max_length=64)
    event_type: str = Field(min_length=2, max_length=64)
    payload_base64: str = Field(min_length=1, max_length=1000000)


@router.post("/integrations/webhooks", status_code=status.HTTP_202_ACCEPTED)
def receive_integration_webhook(
    payload: WebhookBody,
    x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
    ctx: TenantAccessContext = Depends(require_permission("tenant.admin")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Inbound integration webhook with mandatory HMAC signature verification and
    replay protection via payload digest uniqueness.
    """
    import base64

    raw_payload = base64.b64decode(payload.payload_base64, validate=True)
    payload_sha256 = hashlib.sha256(raw_payload).hexdigest()

    settings_signature_secret = "nexus-integration-webhook-secret"
    expected_sig = hmac.new(
        settings_signature_secret.encode("utf-8"),
        raw_payload,
        hashlib.sha256,
    ).hexdigest()

    signature_verified = bool(
        x_webhook_signature
        and hmac.compare_digest(expected_sig, x_webhook_signature)
    )

    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        duplicate = db.scalars(
            select(IntegrationEvent).where(
                IntegrationEvent.organisation_id == ctx.organisation.id,
                IntegrationEvent.payload_sha256 == payload_sha256,
                IntegrationEvent.processed_at.is_not(None),
            )
        ).first()
        if duplicate is not None:
            raise NexusAPIError(
                status_code=409,
                code="webhook_replay_detected",
                message="Webhook payload was already processed.",
            )

        event = IntegrationEvent(
            organisation_id=ctx.organisation.id,
            provider=payload.provider,
            event_type=payload.event_type,
            signature_verified=signature_verified,
            payload_sha256=payload_sha256,
            processed_at=utcnow() if signature_verified else None,
        )
        db.add(event)
        db.flush()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="collaboration.webhook.receive",
            resource_type="integration_event",
            resource_id=event.id,
            result="succeeded" if signature_verified else "signature_invalid",
            metadata={
                "provider": payload.provider,
                "event_type": payload.event_type,
                "signature_verified": signature_verified,
            },
        )
        db.commit()

    if not signature_verified:
        raise NexusAPIError(
            status_code=401,
            code="webhook_signature_invalid",
            message="Webhook signature verification failed.",
        )
    return {
        "integration_event_id": event.id,
        "signature_verified": True,
        "status": "processed",
    }
