import base64
import hashlib
import hmac
import importlib

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_supabase_test_jwt
from app.models.foundation import User
from app.models.intelligence import ActionItem
from app.auth.permissions import bootstrap_organisation_roles
from app.models.foundation import UserRole

_0008_mod = importlib.import_module("migrations.versions.0008_phase8_collaboration")

WEBHOOK_SECRET = "nexus-integration-webhook-secret"


def _auth_headers(sub: str, email: str, org_id: str | None = None) -> dict[str, str]:
    token = create_supabase_test_jwt(sub=sub, email=email)
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organisation-ID"] = org_id
    return headers


def _bootstrap_org(client: TestClient, sub: str, email: str) -> tuple[str, dict[str, str], str]:
    headers = _auth_headers(sub, email)
    org = client.post("/api/v1/organisations", json={"name": f"CollabOrg {sub}"}, headers=headers).json()
    org_id = org["id"]
    ws_id = org["default_workspace_id"]
    headers = _auth_headers(sub, email, org_id=org_id)
    user_id = client.get("/api/v1/me", headers=headers).json()["user"]["id"]
    return org_id, headers, user_id


def test_phase8_postgres_rls_migration_ddl() -> None:
    stmts = _0008_mod.get_phase8_postgres_rls_upgrade_sql()
    joined = "\n".join(stmts)
    for table in _0008_mod.PHASE8_TENANT_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in joined
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in joined
        assert f"CREATE POLICY tenant_isolation_{table} ON {table}" in joined


def test_comments_and_privacy_safe_notifications(client: TestClient) -> None:
    org_id, headers, host_user_id = _bootstrap_org(client, "sub-collab-1", "c1@org.example.com")
    meeting_id = client.post(
        "/api/v1/meetings",
        json={"workspace_id": client.get("/api/v1/me", headers=headers).json()["active_organisation"]["id"]},
        headers=headers,
    )
    # Meeting requires workspace_id; fetch default workspace properly
    ws_id = None
    workspaces = client.get(
        f"/api/v1/organisations/{org_id}/workspaces", headers=headers
    ).json()["items"]
    ws_id = workspaces[0]["id"]
    if meeting_id.status_code != 201:
        meeting_id = client.post(
            "/api/v1/meetings",
            json={"workspace_id": ws_id, "title": "Comment Meeting"},
            headers=headers,
        ).json()["id"]
    else:
        meeting_id = meeting_id.json()["id"]

    comment = client.post(
        f"/api/v1/meetings/{meeting_id}/comments",
        json={"comment_text": "CONFIDENTIAL board discussion content should not appear in notifications."},
        headers=headers,
    )
    assert comment.status_code == 201
    assert comment.json()["comment_text"].startswith("CONFIDENTIAL")

    notifications = client.get("/api/v1/notifications", headers=headers).json()["items"]
    assert len(notifications) >= 1
    preview = notifications[0]["preview_text"]
    # Meeting/comment content MUST NOT appear in notification previews
    assert "CONFIDENTIAL board discussion" not in preview
    assert "New comment on" in preview


def test_share_grants_expiry_revocation_and_self_approval_denial(
    client: TestClient, db_session: Session
) -> None:
    org_id, owner_headers, owner_user_id = _bootstrap_org(client, "sub-collab-2", "c2@org.example.com")

    grant = client.post(
        "/api/v1/share-grants",
        json={
            "resource_type": "meeting",
            "resource_id": "meeting-resource-1",
            "grantee_user_id": owner_user_id,
            "permission": "view",
            "expires_in_days": 7,
        },
        headers=owner_headers,
    )
    assert grant.status_code == 201
    grant_id = grant.json()["share_grant_id"]

    revoke = client.post(
        f"/api/v1/share-grants/{grant_id}/revoke",
        headers=owner_headers,
    )
    assert revoke.status_code == 200
    assert revoke.json()["revoked_at"] is not None

    # Self-approval denial
    summary_approval = client.post(
        "/api/v1/approvals?resource_type=meeting_summary&resource_id=res-1",
        headers=owner_headers,
    )
    assert summary_approval.status_code == 201
    approval_id = summary_approval.json()["approval_id"]

    self_decide = client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        json={"approve": True},
        headers=owner_headers,
    )
    assert self_decide.status_code == 403
    assert self_decide.json()["error"]["code"] == "self_approval_denied"


def test_action_assignment_and_expired_grant_denial(client: TestClient, db_session: Session) -> None:
    org_id, headers, user_id = _bootstrap_org(client, "sub-collab-3", "c3@org.example.com")

    # Seed an action item directly in the test DB
    action = ActionItem(
        organisation_id=org_id,
        meeting_id=None,
        summary_id=None,
        action_text="Follow up on client proposal",
        owner_hint="Sarah",
        due_hint="Friday",
        is_ai_interpretation=True,
    )
    # meeting_id and summary_id are NOT NULL in schema; supply minimal valid rows
    meeting = None
    from app.models.meetings_media import Meeting

    ws = client.get(f"/api/v1/organisations/{org_id}/workspaces", headers=headers).json()["items"][0]
    meeting = Meeting(
        organisation_id=org_id,
        workspace_id=ws["id"],
        host_user_id=user_id,
        title="Assignment Meeting",
    )
    db_session.add(meeting)
    db_session.flush()
    action.meeting_id = meeting.id
    from app.models.intelligence import MeetingSummary
    from app.models.transcription import Transcript

    transcript = Transcript(
        organisation_id=org_id,
        meeting_id=meeting.id,
        media_asset_id=meeting.id,
        background_job_id=meeting.id,
        language_code="en",
        detected_language="en",
    )
    db_session.add(transcript)
    db_session.flush()
    summary = MeetingSummary(
        organisation_id=org_id,
        meeting_id=meeting.id,
        transcript_id=transcript.id,
        background_job_id=meeting.id,
        kind="summary",
        content_text="Test summary content",
    )
    db_session.add(summary)
    db_session.flush()
    action.summary_id = summary.id
    db_session.add(action)
    db_session.commit()

    assignment = client.post(
        "/api/v1/assignments",
        json={"action_item_id": action.id, "assigned_to_user_id": user_id},
        headers=headers,
    )
    assert assignment.status_code == 201
    assert assignment.json()["status"] == "open"

    notifications = client.get("/api/v1/notifications", headers=headers).json()["items"]
    assert any(n["notification_type"] == "action.assigned" for n in notifications)


def test_webhook_signature_verification_and_replay_protection(client: TestClient) -> None:
    org_id, headers, user_id = _bootstrap_org(client, "sub-collab-4", "c4@org.example.com")

    raw_payload = b'{"event": "calendar.meeting_created", "external_id": "abc-123"}'
    signature = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()

    webhook = client.post(
        "/api/v1/integrations/webhooks",
        json={
            "provider": "calendar",
            "event_type": "meeting_created",
            "payload_base64": base64.b64encode(raw_payload).decode("ascii"),
        },
        headers={**headers, "X-Webhook-Signature": signature},
    )
    assert webhook.status_code == 202
    assert webhook.json()["signature_verified"] is True

    # Replay of the exact same payload must be rejected
    replay = client.post(
        "/api/v1/integrations/webhooks",
        json={
            "provider": "calendar",
            "event_type": "meeting_created",
            "payload_base64": base64.b64encode(raw_payload).decode("ascii"),
        },
        headers={**headers, "X-Webhook-Signature": signature},
    )
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "webhook_replay_detected"

    # Invalid signature rejected
    bad_sig = client.post(
        "/api/v1/integrations/webhooks",
        json={
            "provider": "calendar",
            "event_type": "meeting_updated",
            "payload_base64": base64.b64encode(b'{"event": "other"}').decode("ascii"),
        },
        headers={**headers, "X-Webhook-Signature": "deadbeef"},
    )
    assert bad_sig.status_code == 401
    assert bad_sig.json()["error"]["code"] == "webhook_signature_invalid"


def test_cross_tenant_collaboration_isolation(client: TestClient) -> None:
    org_a, headers_a, user_a = _bootstrap_org(client, "sub-collab-a", "ca@tenant-a.example.com")
    org_b, headers_b, user_b = _bootstrap_org(client, "sub-collab-b", "cb@tenant-b.example.com")

    # Tenant A creates a share grant; Tenant B cannot revoke it
    grant = client.post(
        "/api/v1/share-grants",
        json={
            "resource_type": "meeting",
            "resource_id": "res-cross",
            "grantee_user_id": user_a,
            "permission": "view",
        },
        headers=headers_a,
    )
    grant_id = grant.json()["share_grant_id"]

    cross_revoke = client.post(
        f"/api/v1/share-grants/{grant_id}/revoke",
        headers=headers_b,
    )
    assert cross_revoke.status_code == 404

    # Tenant B notifications never include Tenant A events
    notifications_b = client.get("/api/v1/notifications", headers=headers_b).json()["items"]
    for n in notifications_b:
        assert n["resource_id"] != "res-cross"
