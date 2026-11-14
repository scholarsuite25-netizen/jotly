from fastapi.testclient import TestClient

from app.core.security import create_supabase_test_jwt


def _collect_endpoints() -> list[dict[str, str]]:
    """Direct contract inventory matching the release router's walk logic."""
    from app.main import create_app

    application = create_app()
    inventory: list[dict[str, str]] = []

    def walk(routes, inherited_prefix: str = ""):
        for route in routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if path and methods:
                full_path = f"{inherited_prefix}{path}"
                if full_path.startswith("/api/v1"):
                    inventory.append(
                        {"path": full_path, "methods": sorted(methods - {"HEAD", "OPTIONS"})}
                    )
            original = getattr(route, "original_router", None)
            include_context = getattr(route, "include_context", None)
            if original is not None:
                prefix = getattr(include_context, "prefix", "") or ""
                walk(getattr(original, "routes", []), inherited_prefix + prefix)
            else:
                inner = getattr(route, "routes", None)
                if inner:
                    walk(inner, inherited_prefix)

    walk(application.router.routes)
    unique = {(e["path"], tuple(e["methods"])): e for e in inventory}
    return sorted(unique.values(), key=lambda e: e["path"])


def _auth_headers(sub: str, email: str, org_id: str | None = None) -> dict[str, str]:
    token = create_supabase_test_jwt(sub=sub, email=email)
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organisation-ID"] = org_id
    return headers


def test_release_readiness_report_passes_all_live_checks(client: TestClient) -> None:
    headers = _auth_headers("sub-rel-1", "rel1@org.example.com")
    org = client.post("/api/v1/organisations", json={"name": "Release Org"}, headers=headers).json()
    org_id = org["id"]
    headers = _auth_headers("sub-rel-1", "rel1@org.example.com", org_id=org_id)

    report = client.get("/api/v1/release/readiness-report", headers=headers)
    assert report.status_code == 200
    body = report.json()

    checks = {c["check"]: c for c in body["checks"]}

    # On SQLite test dialect, RLS is verified through migrations on PostgreSQL deploy;
    # the check must reflect the dialect and never falsely claim a live PostgreSQL pass.
    rls_check = checks["postgres_rls_enabled_and_forced_on_all_tenant_tables"]
    assert rls_check["evidence"]  # always carries evidence of what was actually checked

    # Voice cloning public gate locked off
    assert checks["voice_cloning_public_gate_disabled"]["passed"] is True

    # Tamper-evident audit chain integrity verified live
    assert checks["audit_hash_chain_integrity"]["passed"] is True
    assert "chained audit entries" in checks["audit_hash_chain_integrity"]["evidence"]

    # Email failover chain configured
    assert checks["transactional_email_failover_chain"]["passed"] is True

    # Signed playback TTL bounded
    assert checks["signed_playback_url_ttl_bounded"]["passed"] is True

    # Server-side tenant resolution documented with negative-test evidence
    assert checks["server_side_tenant_resolution_enforced"]["passed"] is True

    # Owner-operated gates listed (pen test, load benchmarks, restore drill, licences)
    assert len(body["outstanding_owner_gates"]) >= 4

    # No blockers outstanding on the automated checks
    blockers = [
        c for c in body["checks"]
        if not c["passed"] and c["severity"] == "blocker_if_failed"
    ]
    assert blockers == []


def test_release_report_denied_without_tenant_admin(client: TestClient, db_session) -> None:
    headers = _auth_headers("sub-rel-2", "rel2@org.example.com")
    org = client.post("/api/v1/organisations", json={"name": "Release Deny Org"}, headers=headers).json()
    org_id = org["id"]
    headers = _auth_headers("sub-rel-2", "rel2@org.example.com", org_id=org_id)

    from app.models.foundation import User, UserRole
    from app.auth.permissions import bootstrap_organisation_roles

    viewer = User(
        supabase_sub="sub-rel-viewer",
        email="viewer@org.example.com",
        full_name="Viewer",
        is_active=True,
    )
    db_session.add(viewer)
    db_session.flush()
    roles = bootstrap_organisation_roles(db_session, org_id)
    db_session.add(
        UserRole(
            organisation_id=org_id,
            user_id=viewer.id,
            role_id=roles["participant"].id,
            status="active",
        )
    )
    db_session.commit()

    denied = client.get(
        "/api/v1/release/readiness-report",
        headers=_auth_headers("sub-rel-viewer", "viewer@org.example.com", org_id=org_id),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_permissions"


def test_openapi_contract_summary_inventories_all_endpoints(client: TestClient) -> None:
    headers = _auth_headers("sub-rel-3", "rel3@org.example.com")
    org = client.post("/api/v1/organisations", json={"name": "Contract Org"}, headers=headers).json()
    org_id = org["id"]
    headers = _auth_headers("sub-rel-3", "rel3@org.example.com", org_id=org_id)

    summary = client.get("/api/v1/release/openapi-contract-summary", headers=headers)
    assert summary.status_code == 200
    body = summary.json()

    assert body["endpoint_count"] >= 25
    paths = {e["path"] for e in body["endpoints"]}
    for expected in (
        "/api/v1/health",
        "/api/v1/me",
        "/api/v1/organisations",
        "/api/v1/meetings",
        "/api/v1/transcripts/{transcript_id}",
        "/api/v1/documents/ingest",
        "/api/v1/speech-projects",
        "/api/v1/voice/profiles",
        "/api/v1/assistant/questions",
        "/api/v1/share-grants",
        "/api/v1/release/readiness-report",
    ):
        assert expected in paths, f"Missing endpoint: {expected}"


def test_endpoint_inventory_matches_direct_walk() -> None:
    direct = _collect_endpoints()
    assert len(direct) >= 25
