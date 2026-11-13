from datetime import timedelta
import importlib
import json
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import bootstrap_organisation_roles
from app.core.config import Settings
from app.core.db import tenant_db_context
from app.core.errors import NexusAPIError
from app.core.security import create_supabase_test_jwt
from app.models.foundation import AuditLog, Organisation, User, UserRole, Workspace
from app.services.audit import record_audit_event, verify_organisation_audit_chain
from app.services.email import EmailMessage, MultiProviderEmailService
from app.workers.context import enqueue_tenant_job, execute_job_in_tenant_context

_0001_mod = importlib.import_module("migrations.versions.0001_phase1_foundation_and_rls")


def _auth_headers(sub: str, email: str, org_id: str | None = None, aal: str = "aal1") -> dict[str, str]:
    token = create_supabase_test_jwt(sub=sub, email=email, aal=aal)
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organisation-ID"] = org_id
    return headers


def test_health_and_voice_cloning_gate_locked(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert "X-Correlation-ID" in resp.headers
    body = resp.json()
    assert body["status"] == "ok"
    assert body["voice_cloning_enabled"] is False
    assert body["email_providers"] == ["resend", "emailbump", "unipost"]
    assert body["topology"] == {
        "frontend": "vercel",
        "edge_gateway": "cloudflare",
        "compute_host": "hostinger-self-hosted",
        "auth": "supabase-auth",
    }

    with pytest.raises(ValidationError):
        Settings(VOICE_CLONING_ENABLED=True)


def test_postgres_rls_migration_ddl_completeness() -> None:
    sql_statements = _0001_mod.get_postgres_rls_upgrade_sql()
    joined = "\n".join(sql_statements)
    assert "ALTER TABLE organisations ENABLE ROW LEVEL SECURITY;" in joined
    assert "ALTER TABLE organisations FORCE ROW LEVEL SECURITY;" in joined
    for table in _0001_mod.TENANT_ISOLATED_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in joined
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in joined
        assert f"CREATE POLICY tenant_isolation_{table} ON {table}" in joined
        assert "current_setting('app.current_organisation_id', true)" in joined


def test_unauthenticated_and_expired_jwt_rejected(client: TestClient) -> None:
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "authentication_required"

    expired_token = create_supabase_test_jwt(
        sub="user-expired",
        email="expired@example.com",
        expires_delta=timedelta(minutes=-5),
    )
    resp_expired = client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert resp_expired.status_code == 401
    assert resp_expired.json()["error"]["code"] == "invalid_or_expired_token"


def test_cross_tenant_api_and_guessed_id_denial(
    client: TestClient, db_session: Session
) -> None:
    # Tenant A Admin creates Organisation A and a confidential workspace
    headers_a = _auth_headers("sub-alice", "alice@org-a.example.com")
    org_a_resp = client.post(
        "/api/v1/organisations",
        json={"name": "Alpha Legal LLP", "slug": "alpha-legal"},
        headers=headers_a,
    )
    assert org_a_resp.status_code == 201
    org_a_id = org_a_resp.json()["id"]

    ws_a_resp = client.post(
        f"/api/v1/organisations/{org_a_id}/workspaces",
        json={"name": "Board Confidential Workspace"},
        headers=headers_a,
    )
    assert ws_a_resp.status_code == 201
    ws_a_id = ws_a_resp.json()["id"]

    # Tenant B Admin creates Organisation B
    headers_b = _auth_headers("sub-bob", "bob@org-b.example.com")
    org_b_resp = client.post(
        "/api/v1/organisations",
        json={"name": "Beta Advisory Ltd", "slug": "beta-advisory"},
        headers=headers_b,
    )
    assert org_b_resp.status_code == 201
    org_b_id = org_b_resp.json()["id"]

    # 1. Tenant B attempts direct access to Tenant A organisation endpoint -> 403 Forbidden
    cross_org_resp = client.get(
        f"/api/v1/organisations/{org_a_id}",
        headers=headers_b,
    )
    assert cross_org_resp.status_code == 403
    assert cross_org_resp.json()["error"]["code"] == "tenant_access_denied"

    # 2. Tenant B supplies forged X-Organisation-ID header for Tenant A on /me -> 403 Forbidden
    forged_header_resp = client.get(
        "/api/v1/me",
        headers=_auth_headers("sub-bob", "bob@org-b.example.com", org_id=org_a_id),
    )
    assert forged_header_resp.status_code == 403
    assert forged_header_resp.json()["error"]["code"] == "tenant_access_denied"

    # 3. Tenant B guesses Tenant A's workspace UUID inside Tenant B's path -> 404 Not Found (RLS filtered)
    guessed_ws_resp = client.get(
        f"/api/v1/organisations/{org_b_id}/workspaces/{ws_a_id}",
        headers=headers_b,
    )
    assert guessed_ws_resp.status_code == 404
    assert guessed_ws_resp.json()["error"]["code"] == "workspace_not_found"

    # 4. Verify that Tenant B's denied attempt against Tenant A was recorded in Tenant A's audit log
    audit_resp = client.get(
        "/api/v1/audit-events",
        headers=_auth_headers("sub-alice", "alice@org-a.example.com", org_id=org_a_id),
    )
    assert audit_resp.status_code == 200
    audit_items = audit_resp.json()["items"]
    denied_events = [e for e in audit_items if e["result"] == "denied"]
    assert len(denied_events) >= 2


def test_orm_rls_context_blocks_cross_tenant_reads_and_writes(
    client: TestClient, db_session: Session
) -> None:
    headers_a = _auth_headers("sub-t1", "t1@example.com")
    org_a_id = client.post(
        "/api/v1/organisations", json={"name": "Org One"}, headers=headers_a
    ).json()["id"]

    headers_b = _auth_headers("sub-t2", "t2@example.com")
    org_b_id = client.post(
        "/api/v1/organisations", json={"name": "Org Two"}, headers=headers_b
    ).json()["id"]

    with tenant_db_context(db_session, organisation_id=org_a_id):
        visible_workspaces = list(db_session.scalars(select(Workspace)).all())
        assert len(visible_workspaces) == 1
        assert all(w.organisation_id == org_a_id for w in visible_workspaces)

        # Attempting to insert a Workspace for Org B while in Org A's tenant_db_context must fail
        with pytest.raises(PermissionError, match="RLS write violation"):
            db_session.add(
                Workspace(organisation_id=org_b_id, name="Illegal Cross-Tenant Write")
            )
            db_session.flush()
        db_session.rollback()


def test_granular_rbac_blocks_unauthorised_role_escalation(
    client: TestClient, db_session: Session
) -> None:
    headers_admin = _auth_headers("sub-owner", "owner@acme.example.com")
    org_id = client.post(
        "/api/v1/organisations", json={"name": "Acme Corp"}, headers=headers_admin
    ).json()["id"]

    # Create a participant user in the same organisation
    participant = User(
        supabase_sub="sub-participant",
        email="viewer@acme.example.com",
        full_name="Viewer User",
        is_active=True,
    )
    db_session.add(participant)
    db_session.flush()
    roles = bootstrap_organisation_roles(db_session, org_id)
    db_session.add(
        UserRole(
            organisation_id=org_id,
            user_id=participant.id,
            role_id=roles["participant"].id,
            status="active",
        )
    )
    db_session.commit()

    headers_participant = _auth_headers(
        "sub-participant", "viewer@acme.example.com", org_id=org_id
    )

    # Participant can view workspaces (`meeting.view`)
    list_resp = client.get(
        f"/api/v1/organisations/{org_id}/workspaces", headers=headers_participant
    )
    assert list_resp.status_code == 200

    # Participant CANNOT create a workspace (`tenant.admin` required)
    create_ws_resp = client.post(
        f"/api/v1/organisations/{org_id}/workspaces",
        json={"name": "Unauthorised Workspace"},
        headers=headers_participant,
    )
    assert create_ws_resp.status_code == 403
    assert create_ws_resp.json()["error"]["code"] == "insufficient_permissions"

    # Participant CANNOT read audit logs (`audit.view` required)
    audit_resp = client.get("/api/v1/audit-events", headers=headers_participant)
    assert audit_resp.status_code == 403
    assert audit_resp.json()["error"]["code"] == "insufficient_permissions"


def test_background_worker_tenant_context_and_job_isolation(
    client: TestClient, db_session: Session
) -> None:
    headers_a = _auth_headers("sub-job-a", "job-a@example.com")
    org_a_id = client.post(
        "/api/v1/organisations", json={"name": "Job Org A"}, headers=headers_a
    ).json()["id"]
    me_a = client.get("/api/v1/me", headers=headers_a).json()["user"]["id"]

    headers_b = _auth_headers("sub-job-b", "job-b@example.com")
    org_b_id = client.post(
        "/api/v1/organisations", json={"name": "Job Org B"}, headers=headers_b
    ).json()["id"]

    # Enqueue idempotent job in Org A
    job_a = enqueue_tenant_job(
        db_session,
        organisation_id=org_a_id,
        actor_user_id=me_a,
        job_type="media.validate",
        source_entity_type="media_asset",
        source_entity_id="asset-001",
        idempotency_key="idem-001",
    )
    duplicate_job = enqueue_tenant_job(
        db_session,
        organisation_id=org_a_id,
        actor_user_id=me_a,
        job_type="media.validate",
        source_entity_type="media_asset",
        source_entity_id="asset-001",
        idempotency_key="idem-001",
    )
    assert job_a.id == duplicate_job.id

    # Tenant B cannot query Tenant A's job ID via API -> 404 Not Found
    cross_job_resp = client.get(
        f"/api/v1/jobs/{job_a.id}",
        headers=_auth_headers("sub-job-b", "job-b@example.com", org_id=org_b_id),
    )
    assert cross_job_resp.status_code == 404

    # Worker attempting to run Org A's job inside Org B's tenant context is blocked
    with pytest.raises(NexusAPIError) as exc_info:
        execute_job_in_tenant_context(
            db_session,
            job_id=job_a.id,
            expected_organisation_id=org_b_id,
            handler=lambda s, j: "should-never-run",
        )
    assert exc_info.value.code == "worker_tenant_isolation_violation"

    # Worker running Org A's job inside Org A's verified tenant context succeeds
    output = execute_job_in_tenant_context(
        db_session,
        job_id=job_a.id,
        expected_organisation_id=org_a_id,
        handler=lambda s, j: f"processed:{j.source_entity_id}",
    )
    assert output == "processed:asset-001"


def test_tamper_evident_audit_hash_chain_and_redaction(
    client: TestClient, db_session: Session
) -> None:
    headers = _auth_headers("sub-auditor", "auditor@example.com")
    org_id = client.post(
        "/api/v1/organisations", json={"name": "Audit Integrity Org"}, headers=headers
    ).json()["id"]
    user_id = client.get("/api/v1/me", headers=headers).json()["user"]["id"]

    # Record event containing sensitive keys that MUST be redacted automatically
    entry = record_audit_event(
        db_session,
        organisation_id=org_id,
        actor_user_id=user_id,
        action="security.sensitive_test",
        resource_type="test",
        resource_id="res-1",
        result="succeeded",
        metadata={
            "safe_field": "allowed-value",
            "transcript_text": "Confidential board discussion should never be logged",
            "voice_sample": "raw-biometric-audio",
            "access_token": "secret-jwt-value",
        },
    )
    db_session.commit()

    parsed_meta = json.loads(entry.metadata_json)
    assert parsed_meta["safe_field"] == "allowed-value"
    assert parsed_meta["transcript_text"] == "[REDACTED]"
    assert parsed_meta["voice_sample"] == "[REDACTED]"
    assert parsed_meta["access_token"] == "[REDACTED]"

    # Verify audit chain via API endpoint
    verify_resp = client.get(
        "/api/v1/audit-events/verify",
        headers=_auth_headers("sub-auditor", "auditor@example.com", org_id=org_id),
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["chain_valid"] is True
    assert verify_resp.json()["entries_verified"] >= 2

    # Simulate tampering with an audit log record in the database
    entry.action = "tampered.action"
    db_session.commit()

    is_valid, _, broken_id = verify_organisation_audit_chain(db_session, org_id)
    assert is_valid is False
    assert broken_id == entry.id


def test_multi_provider_email_failover_resend_emailbump_unipost() -> None:
    attempts: list[str] = []

    def simulated_transport(provider: str, message: EmailMessage) -> str:
        attempts.append(provider)
        if provider in ("resend", "emailbump"):
            raise RuntimeError(f"{provider} temporary outage")
        return "unipost-msg-999"

    service = MultiProviderEmailService(transport_override=simulated_transport)
    result = service.send(
        EmailMessage(
            to_email="invitee@example.com",
            subject="Welcome to NEXUS",
            text_body="Your organisation invitation is ready.",
        )
    )
    assert result.provider == "unipost"
    assert result.message_id == "unipost-msg-999"
    assert result.attempted_providers == ["resend", "emailbump", "unipost"]
    assert attempts == ["resend", "emailbump", "unipost"]

    # Verify privacy guard blocks sensitive transcript or voice content in email
    with pytest.raises(ValueError, match="Email privacy policy violation"):
        service.send(
            EmailMessage(
                to_email="leak@example.com",
                subject="Leak attempt",
                text_body="transcript_segment: confidential text",
            )
        )


def test_organisation_invitation_and_readiness_endpoints(
    client: TestClient,
) -> None:
    ready_resp = client.get("/api/v1/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "ready"
    assert ready_resp.json()["database"] == "connected"

    headers_admin = _auth_headers("sub-inviter", "inviter@org.example.com")
    org_id = client.post(
        "/api/v1/organisations",
        json={"name": "Invite Test Org"},
        headers=headers_admin,
    ).json()["id"]

    inv_resp = client.post(
        f"/api/v1/organisations/{org_id}/invitations",
        json={"email": "new.member@org.example.com", "role_code": "meeting_host"},
        headers=headers_admin,
    )
    assert inv_resp.status_code == 201
    inv_body = inv_resp.json()
    assert inv_body["organisation_id"] == org_id
    assert inv_body["email"] == "new.member@org.example.com"
    assert inv_body["role_code"] == "meeting_host"
    assert inv_body["status"] == "pending"
    assert inv_body["email_provider"] == "resend"

