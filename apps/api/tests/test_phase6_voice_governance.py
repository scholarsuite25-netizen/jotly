import base64
import hashlib
import importlib

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_supabase_test_jwt
from app.models.foundation import User
from app.workers.voice_worker import run_voice_synthesis_worker

_0006_mod = importlib.import_module("migrations.versions.0006_phase6_voice_governance")


def _auth_headers(sub: str, email: str, org_id: str | None = None) -> dict[str, str]:
    token = create_supabase_test_jwt(sub=sub, email=email)
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organisation-ID"] = org_id
    return headers


def _bootstrap_voice_org(client: TestClient, sub: str, email: str):
    headers = _auth_headers(sub, email)
    client.post("/api/v1/organisations", json={"name": f"VoiceOrg {sub}"}, headers=headers)
    me = client.get("/api/v1/me", headers=headers).json()
    org_id = me["active_organisation"]["id"]
    headers = _auth_headers(sub, email, org_id=org_id)
    return org_id, headers, me["user"]["id"]


def _enrol_profile(client: TestClient, headers: dict[str, str]) -> str:
    consent = client.post(
        "/api/v1/voice/consents",
        json={
            "consent_text_version": "2026-11-v1",
            "verification_reference": "challenge-abc-123",
            "verification_passed": True,
        },
        headers=headers,
    )
    assert consent.status_code == 201, consent.text
    consent_id = consent.json()["consent_id"]

    sample_bytes = b"RIFF" + (36 + 64).to_bytes(4, "little") + b"WAVEfmt " + (b"\x01\x02" * 32)
    profile = client.post(
        "/api/v1/voice/profiles",
        json={
            "consent_id": consent_id,
            "display_name": "Owner Voice",
            "sample_content_base64": base64.b64encode(sample_bytes).decode("ascii"),
        },
        headers=headers,
    )
    assert profile.status_code == 201, profile.text
    return profile.json()["voice_profile_id"]


def test_phase6_postgres_rls_migration_ddl() -> None:
    stmts = _0006_mod.get_phase6_postgres_rls_upgrade_sql()
    joined = "\n".join(stmts)
    for table in _0006_mod.PHASE6_TENANT_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in joined
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in joined
        assert f"CREATE POLICY tenant_isolation_{table} ON {table}" in joined


def test_consent_enrolment_and_private_profile_creation(client: TestClient) -> None:
    org_id, headers, owner_user_id = _bootstrap_voice_org(
        client, "sub-vc-1", "vc1@org.example.com"
    )
    profile_id = _enrol_profile(client, headers)

    profile_detail = None
    audit_resp = client.get(
        f"/api/v1/voice/profiles/{profile_id}/audit",
        headers=headers,
    )
    assert audit_resp.status_code == 200
    actions = [e["action"] for e in audit_resp.json()["items"]]
    assert "voice.profile.enrol" in actions

    # Owner can enqueue synthesis for own profile
    synthesis = client.post(
        f"/api/v1/voice/profiles/{profile_id}/synthesis",
        json={"text_content": "Hello from the voice governance test suite."},
        headers=headers,
    )
    assert synthesis.status_code == 202, synthesis.text
    voice_job_id = synthesis.json()["voice_job_id"]

    audit_after = client.get(
        f"/api/v1/voice/profiles/{profile_id}/audit", headers=headers
    ).json()["items"]
    assert any(
        e["action"] == "voice.synthesis.authorise" and e["result"] == "succeeded"
        for e in audit_after
    )

    # Job stays queued until a worker executes it (no inline execution exposed).
    result = client.get(f"/api/v1/voice/jobs/{voice_job_id}/result", headers=headers)
    assert result.status_code == 200
    assert result.json()["status"] == "queued"


def test_synthesis_denied_without_owner_permission_and_revocation_blocks_immediately(
    client: TestClient, db_session: Session
) -> None:
    org_id, owner_headers, owner_user_id = _bootstrap_voice_org(
        client, "sub-vc-2", "vc2@org.example.com"
    )
    profile_id = _enrol_profile(client, owner_headers)

    # Second user in same org without any grant (participant role via owner grant flow)
    grantee = User(
        supabase_sub="sub-vc-grantee",
        email="grantee@org.example.com",
        full_name="Grantee User",
        is_active=True,
    )
    db_session.add(grantee)
    db_session.commit()

    from app.auth.permissions import bootstrap_organisation_roles
    from app.models.foundation import UserRole

    roles = bootstrap_organisation_roles(db_session, org_id)
    db_session.add(
        UserRole(
            organisation_id=org_id,
            user_id=grantee.id,
            role_id=roles["participant"].id,
            status="active",
        )
    )
    db_session.commit()

    denied = client.post(
        f"/api/v1/voice/profiles/{profile_id}/synthesis",
        json={"text_content": "Should be denied."},
        headers=_auth_headers("sub-vc-grantee", "grantee@org.example.com", org_id=org_id),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "voice_permission_required"

    # Owner grants an expiring permission
    grant = client.post(
        f"/api/v1/voice/profiles/{profile_id}/permissions",
        json={"grantee_user_id": grantee.id, "allowed_use": "internal_synthesis"},
        headers=owner_headers,
    )
    assert grant.status_code == 201
    permission_id = grant.json()["permission_id"]

    # Grantee can now request synthesis
    allowed = client.post(
        f"/api/v1/voice/profiles/{profile_id}/synthesis",
        json={"text_content": "Permitted synthesis."},
        headers=_auth_headers("sub-vc-grantee", "grantee@org.example.com", org_id=org_id),
    )
    assert allowed.status_code == 202

    # Owner revokes the grant; immediate subsequent synthesis must be blocked
    revoke = client.post(
        f"/api/v1/voice/profiles/{profile_id}/permissions/{permission_id}/revoke",
        headers=owner_headers,
    )
    assert revoke.status_code == 200

    blocked = client.post(
        f"/api/v1/voice/profiles/{profile_id}/synthesis",
        json={"text_content": "Must be blocked after revocation."},
        headers=_auth_headers("sub-vc-grantee", "grantee@org.example.com", org_id=org_id),
    )
    assert blocked.status_code == 403

    # Owner revokes the whole profile; even the owner is blocked
    profile_revoke = client.post(
        f"/api/v1/voice/profiles/{profile_id}/revoke",
        headers=owner_headers,
    )
    assert profile_revoke.status_code == 200
    assert profile_revoke.json()["status"] == "revoked"

    owner_blocked = client.post(
        f"/api/v1/voice/profiles/{profile_id}/synthesis",
        json={"text_content": "Owner also blocked after profile revocation."},
        headers=owner_headers,
    )
    assert owner_blocked.status_code == 403
    assert owner_blocked.json()["error"]["code"] == "voice_profile_unavailable"


def test_expired_consent_and_verification_failure_block_enrolment(
    client: TestClient, db_session: Session
) -> None:
    org_id, headers, _ = _bootstrap_voice_org(client, "sub-vc-3", "vc3@org.example.com")

    # Verification NOT passed -> profile enrolment denied
    bad_consent = client.post(
        "/api/v1/voice/consents",
        json={
            "consent_text_version": "2026-11-v1",
            "verification_reference": "challenge-fail",
            "verification_passed": False,
        },
        headers=headers,
    )
    assert bad_consent.status_code == 201
    bad_consent_id = bad_consent.json()["consent_id"]

    sample = base64.b64encode(b"RIFF WAVE sample bytes").decode("ascii")
    enrol_denied = client.post(
        "/api/v1/voice/profiles",
        json={
            "consent_id": bad_consent_id,
            "display_name": "Unverified Voice",
            "sample_content_base64": sample,
        },
        headers=headers,
    )
    assert enrol_denied.status_code == 403
    assert enrol_denied.json()["error"]["code"] == "consent_verification_failed"

    # Expired consent -> enrolment denied
    from datetime import timedelta

    expired_consent = client.post(
        "/api/v1/voice/consents",
        json={
            "consent_text_version": "2026-11-v1",
            "verification_reference": "challenge-expired",
            "verification_passed": True,
            "expires_in_days": 1,
        },
        headers=headers,
    )
    assert expired_consent.status_code == 201
    expired_id = expired_consent.json()["consent_id"]

    # Manually expire the consent in the test DB
    from sqlalchemy import select

    from app.models.voice_governance import VoiceConsent

    consent_row = db_session.scalars(
        select(VoiceConsent).where(VoiceConsent.id == expired_id)
    ).first()
    assert consent_row is not None
    consent_row.expires_at = consent_row.expires_at - timedelta(days=2)
    db_session.commit()

    enrol_expired = client.post(
        "/api/v1/voice/profiles",
        json={
            "consent_id": expired_id,
            "display_name": "Expired Voice",
            "sample_content_base64": sample,
        },
        headers=headers,
    )
    assert enrol_expired.status_code == 403
    assert enrol_expired.json()["error"]["code"] == "consent_expired"


def test_cross_tenant_voice_profile_denial(client: TestClient) -> None:
    org_a, headers_a, _ = _bootstrap_voice_org(client, "sub-vc-a", "vca@tenant-a.example.com")
    profile_id = _enrol_profile(client, headers_a)

    org_b, headers_b, _ = _bootstrap_voice_org(client, "sub-vc-b", "vcb@tenant-b.example.com")

    # Tenant B cannot see or synthesize Tenant A's profile (RLS isolation)
    denied = client.post(
        f"/api/v1/voice/profiles/{profile_id}/synthesis",
        json={"text_content": "Cross tenant attempt."},
        headers=headers_b,
    )
    assert denied.status_code == 404

    # Tenant B cannot grant permissions on Tenant A's profile
    grant_denied = client.post(
        f"/api/v1/voice/profiles/{profile_id}/permissions",
        json={"grantee_user_id": "someone"},
        headers=headers_b,
    )
    assert grant_denied.status_code == 404

    # Audit trail also tenant-isolated
    audit_denied = client.get(
        f"/api/v1/voice/profiles/{profile_id}/audit", headers=headers_b
    )
    assert audit_denied.status_code == 404
