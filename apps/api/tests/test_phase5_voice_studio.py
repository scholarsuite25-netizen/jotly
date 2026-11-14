import importlib

from fastapi.testclient import TestClient

from app.core.security import create_supabase_test_jwt

_0005_mod = importlib.import_module("migrations.versions.0005_phase5_voice_studio")


def _auth_headers(sub: str, email: str, org_id: str | None = None) -> dict[str, str]:
    token = create_supabase_test_jwt(sub=sub, email=email)
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organisation-ID"] = org_id
    return headers


def test_phase5_postgres_rls_migration_ddl() -> None:
    stmts = _0005_mod.get_phase5_postgres_rls_upgrade_sql()
    joined = "\n".join(stmts)
    for table in _0005_mod.PHASE5_TENANT_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in joined
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in joined
        assert f"CREATE POLICY tenant_isolation_{table} ON {table}" in joined


def test_speech_project_synthesis_chunks_chapters_and_disclosure(
    client: TestClient,
) -> None:
    headers = _auth_headers("sub-speech-1", "sp1@org.example.com")
    client.post("/api/v1/organisations", json={"name": "Voice Org"}, headers=headers)
    me = client.get("/api/v1/me", headers=headers).json()
    org_id = me["active_organisation"]["id"]
    headers = _auth_headers("sub-speech-1", "sp1@org.example.com", org_id=org_id)

    paragraph_one = " ".join(["The quarterly budget is approved."] * 6)
    paragraph_two = " ".join(["Hiring remains on track this quarter."] * 6)
    text = f"{paragraph_one}\n\n{paragraph_two}"

    resp = client.post(
        "/api/v1/speech-projects",
        json={
            "title": "Q4 Board Narrative",
            "language_code": "en",
            "voice_id": "female_01",
            "speed_percent": 110,
            "output_format": "wav",
            "text_content": text,
            "add_chapters": True,
        },
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["chunk_count"] >= 2
    assert body["duration_ms"] > 0
    assert "AI-generated speech" in body["synthetic_disclosure"]
    asset_id = body["audio_asset_id"]

    detail = client.get(
        f"/api/v1/speech-projects/{body['speech_project_id']}", headers=headers
    ).json()
    assert detail["status"] == "completed"
    assert detail["audio_asset"]["loudness_normalised"] is True
    assert len(detail["audio_asset"]["chapters"]) == detail["chunk_count"]
    first_chapter = detail["audio_asset"]["chapters"][0]
    assert first_chapter["start_ms"] == 0
    assert first_chapter["end_ms"] > 0

    # Signed playback URL works and exposes the synthetic-audio disclosure header
    pb = client.get(f"/api/v1/audio/{asset_id}/playback-url", headers=headers)
    assert pb.status_code == 200
    stream = client.get(pb.json()["playback_url"])
    assert stream.status_code == 200
    assert stream.headers.get("X-Synthetic-Audio-Disclosure") == "AI-generated speech (standard voice)"
    assert stream.content[:4] == b"RIFF"


def test_speech_validation_unknown_voice_language_speed_and_format(
    client: TestClient,
) -> None:
    headers = _auth_headers("sub-speech-2", "sp2@org.example.com")
    client.post("/api/v1/organisations", json={"name": "Voice Validation Org"}, headers=headers)
    me = client.get("/api/v1/me", headers=headers).json()
    org_id = me["active_organisation"]["id"]
    headers = _auth_headers("sub-speech-2", "sp2@org.example.com", org_id=org_id)

    base = {
        "title": "Narrative",
        "language_code": "en",
        "voice_id": "female_01",
        "text_content": "Some review content to synthesize here.",
    }

    # Unknown voice for language
    bad_voice = client.post(
        "/api/v1/speech-projects",
        json={**base, "voice_id": "does_not_exist"},
        headers=headers,
    )
    assert bad_voice.status_code == 400
    assert bad_voice.json()["error"]["code"] == "unknown_voice"

    # Unsupported language
    bad_lang = client.post(
        "/api/v1/speech-projects",
        json={**base, "language_code": "xx"},
        headers=headers,
    )
    assert bad_lang.status_code == 400
    assert bad_lang.json()["error"]["code"] == "unsupported_language"

    # Speed out of range
    bad_speed = client.post(
        "/api/v1/speech-projects",
        json={**base, "speed_percent": 300},
        headers=headers,
    )
    assert bad_speed.status_code == 422

    # Unsupported output format
    bad_format = client.post(
        "/api/v1/speech-projects",
        json={**base, "output_format": "flac"},
        headers=headers,
    )
    assert bad_format.status_code == 400
    assert bad_format.json()["error"]["code"] == "unsupported_output_format"


def test_pronunciation_entry_upsert_and_override_application(
    client: TestClient,
) -> None:
    from app.services.tts_adapter import apply_pronunciation_overrides

    headers = _auth_headers("sub-speech-3", "sp3@org.example.com")
    client.post("/api/v1/organisations", json={"name": "Pron Org"}, headers=headers)
    me = client.get("/api/v1/me", headers=headers).json()
    org_id = me["active_organisation"]["id"]
    headers = _auth_headers("sub-speech-3", "sp3@org.example.com", org_id=org_id)

    created = client.post(
        "/api/v1/speech-projects/pronunciations",
        json={
            "word": "Kokoro",
            "phonetic_hint": "KOH-koh-roh",
            "language_code": "en",
        },
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["updated_existing"] is False

    # Upsert updates the same entry
    updated = client.post(
        "/api/v1/speech-projects/pronunciations",
        json={
            "word": "kokoro",
            "phonetic_hint": "KO-koro",
            "language_code": "en",
        },
        headers=headers,
    )
    assert updated.status_code == 201
    assert updated.json()["updated_existing"] is True
    assert updated.json()["phonetic_hint"] == "KO-koro"

    # Override application is case-insensitive word-boundary aware
    text = "The kokoro engine powers Kokoro TTS."
    result = apply_pronunciation_overrides(text, {"kokoro": "KO-koro"})
    assert "KO-koro engine" in result
    assert "KO-koro TTS" in result


def test_cross_tenant_speech_isolation(client: TestClient) -> None:
    headers_a = _auth_headers("sub-speech-a", "spa@tenant-a.example.com")
    client.post("/api/v1/organisations", json={"name": "Speech Tenant A"}, headers=headers_a)
    me_a = client.get("/api/v1/me", headers=headers_a).json()
    org_a = me_a["active_organisation"]["id"]
    headers_a = _auth_headers("sub-speech-a", "spa@tenant-a.example.com", org_id=org_a)

    resp_a = client.post(
        "/api/v1/speech-projects",
        json={
            "title": "Confidential Narrative",
            "language_code": "en",
            "voice_id": "female_01",
            "text_content": "Tenant A private synthesis content.",
        },
        headers=headers_a,
    )
    assert resp_a.status_code == 202
    project_a_id = resp_a.json()["speech_project_id"]
    asset_a_id = resp_a.json()["audio_asset_id"]

    headers_b = _auth_headers("sub-speech-b", "spb@tenant-b.example.com")
    client.post("/api/v1/organisations", json={"name": "Speech Tenant B"}, headers=headers_b)
    me_b = client.get("/api/v1/me", headers=headers_b).json()
    org_b = me_b["active_organisation"]["id"]
    headers_b = _auth_headers("sub-speech-b", "spb@tenant-b.example.com", org_id=org_b)

    # Tenant B cannot read Tenant A's project or playback URL
    assert (
        client.get(f"/api/v1/speech-projects/{project_a_id}", headers=headers_b).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/audio/{asset_a_id}/playback-url", headers=headers_b).status_code
        == 404
    )

    # Tampered/cross-tenant signed stream is rejected
    pb = client.get(f"/api/v1/audio/{asset_a_id}/playback-url", headers=headers_a)
    stream_url = pb.json()["playback_url"]
    tampered = stream_url.replace(f"org_id={org_a}", f"org_id={org_b}")
    assert client.get(tampered).status_code == 403
