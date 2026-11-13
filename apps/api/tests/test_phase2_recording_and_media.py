import base64
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.permissions import bootstrap_organisation_roles
from app.core.security import create_supabase_test_jwt
from app.models.foundation import User, UserRole
from app.services.storage_media import create_signed_playback_url

_0002_mod = importlib.import_module("migrations.versions.0002_phase2_recording_and_media")


def _auth_headers(sub: str, email: str, org_id: str | None = None) -> dict[str, str]:
    token = create_supabase_test_jwt(sub=sub, email=email)
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organisation-ID"] = org_id
    return headers


def _make_sample_wav_bytes(body_size: int = 120) -> bytes:
    # Valid RIFF/WAVE header + synthetic PCM bytes
    header = b"RIFF" + (36 + body_size).to_bytes(4, "little") + b"WAVEfmt "
    header += (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
    header += (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little")
    header += (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    header += b"data" + body_size.to_bytes(4, "little")
    return header + (b"\x01\x02" * (body_size // 2))


def _chunk_payload(chunk_bytes: bytes) -> dict[str, str]:
    return {
        "data_base64": base64.b64encode(chunk_bytes).decode("ascii"),
        "sha256_checksum": hashlib.sha256(chunk_bytes).hexdigest(),
    }


def test_phase2_postgres_rls_migration_ddl() -> None:
    stmts = _0002_mod.get_phase2_postgres_rls_upgrade_sql()
    joined = "\n".join(stmts)
    for table in _0002_mod.PHASE2_TENANT_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in joined
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in joined
        assert f"CREATE POLICY tenant_isolation_{table} ON {table}" in joined
        assert "current_setting('app.current_organisation_id', true)" in joined


def test_recording_notice_required_before_upload(client: TestClient) -> None:
    headers = _auth_headers("sub-host-1", "host1@org.example.com")
    org = client.post("/api/v1/organisations", json={"name": "Notice Gate Org"}, headers=headers).json()
    org_id = org["id"]
    ws_id = org["default_workspace_id"]
    headers = _auth_headers("sub-host-1", "host1@org.example.com", org_id=org_id)

    meeting = client.post(
        "/api/v1/meetings",
        json={
            "workspace_id": ws_id,
            "title": "Q4 Strategy Review",
            "agenda": "1. Financials 2. Roadmap",
            "visibility": "workspace",
            "attendees": [
                {"email": "cfo@org.example.com", "display_name": "CFO", "role": "attendee"}
            ],
        },
        headers=headers,
    )
    assert meeting.status_code == 201
    meeting_id = meeting.json()["id"]
    assert meeting.json()["notice_confirmed"] is False

    wav_bytes = _make_sample_wav_bytes(64)
    # Attempt to initiate upload BEFORE confirming recording notice -> 403
    unconfirmed_resp = client.post(
        f"/api/v1/meetings/{meeting_id}/uploads",
        json={
            "file_name": "meeting.wav",
            "mime_type": "audio/wav",
            "declared_size_bytes": len(wav_bytes),
            "expected_sha256": hashlib.sha256(wav_bytes).hexdigest(),
        },
        headers=headers,
    )
    assert unconfirmed_resp.status_code == 403
    assert unconfirmed_resp.json()["error"]["code"] == "recording_notice_required"

    # Confirm recording notice
    confirm_resp = client.post(
        f"/api/v1/meetings/{meeting_id}/recording-notice-confirm",
        json={"notice_version": "2026-11-v1", "host_confirmed": True},
        headers=headers,
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["recording_state"] == "notice_confirmed"


def test_resumable_chunked_upload_duplicate_chunks_and_derivative_separation(
    client: TestClient,
) -> None:
    headers = _auth_headers("sub-host-2", "host2@org.example.com")
    org = client.post("/api/v1/organisations", json={"name": "Media Flow Org"}, headers=headers).json()
    org_id = org["id"]
    ws_id = org["default_workspace_id"]
    headers = _auth_headers("sub-host-2", "host2@org.example.com", org_id=org_id)

    meeting_id = client.post(
        "/api/v1/meetings",
        json={"workspace_id": ws_id, "title": "Board Recording"},
        headers=headers,
    ).json()["id"]

    client.post(
        f"/api/v1/meetings/{meeting_id}/recording-notice-confirm",
        json={"notice_version": "2026-11-v1", "host_confirmed": True},
        headers=headers,
    )

    wav_bytes = _make_sample_wav_bytes(160)
    full_sha256 = hashlib.sha256(wav_bytes).hexdigest()
    chunk_size = 80
    chunks = [
        wav_bytes[i : i + chunk_size] for i in range(0, len(wav_bytes), chunk_size)
    ]
    assert len(chunks) == 3

    init_resp = client.post(
        f"/api/v1/meetings/{meeting_id}/uploads",
        json={
            "file_name": "board-session.wav",
            "mime_type": "audio/wav",
            "declared_size_bytes": len(wav_bytes),
            "expected_sha256": full_sha256,
            "chunk_size_bytes": chunk_size,
        },
        headers=headers,
    )
    assert init_resp.status_code == 201
    session_id = init_resp.json()["upload_session_id"]
    assert init_resp.json()["total_chunks"] == 3

    # Upload chunk 0
    c0_resp = client.put(
        f"/api/v1/meetings/{meeting_id}/uploads/{session_id}/chunks/0",
        json=_chunk_payload(chunks[0]),
        headers=headers,
    )
    assert c0_resp.status_code == 200
    assert c0_resp.json()["idempotent_replay"] is False

    # Duplicate upload of chunk 0 with identical checksum -> idempotent 200 OK
    c0_dup = client.put(
        f"/api/v1/meetings/{meeting_id}/uploads/{session_id}/chunks/0",
        json=_chunk_payload(chunks[0]),
        headers=headers,
    )
    assert c0_dup.status_code == 200
    assert c0_dup.json()["idempotent_replay"] is True

    # Simulate network interruption: check session status before uploading chunks 1 and 2
    status_resp = client.get(
        f"/api/v1/meetings/{meeting_id}/uploads/{session_id}",
        headers=headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["received_chunks"] == [0]
    assert status_resp.json()["missing_chunks"] == [1, 2]

    # Attempting to complete upload while chunks 1 and 2 are missing -> 400
    premature_complete = client.post(
        f"/api/v1/meetings/{meeting_id}/uploads/{session_id}/complete",
        headers=headers,
    )
    assert premature_complete.status_code == 400
    assert premature_complete.json()["error"]["code"] == "incomplete_upload_chunks"

    # Resume and upload missing chunks 1 and 2
    for idx in (1, 2):
        resp = client.put(
            f"/api/v1/meetings/{meeting_id}/uploads/{session_id}/chunks/{idx}",
            json=_chunk_payload(chunks[idx]),
            headers=headers,
        )
        assert resp.status_code == 200

    # Finalise upload -> 202 Accepted + worker validates & generates derivative
    complete_resp = client.post(
        f"/api/v1/meetings/{meeting_id}/uploads/{session_id}/complete",
        headers=headers,
    )
    assert complete_resp.status_code == 202
    asset_id = complete_resp.json()["media_asset_id"]
    assert complete_resp.json()["status"] == "validated"

    # Inspect meeting media: original asset and normalized derivative must be distinct
    media_list = client.get(
        f"/api/v1/meetings/{meeting_id}/media",
        headers=headers,
    )
    assert media_list.status_code == 200
    items = media_list.json()["items"]
    assert len(items) == 1
    asset_item = items[0]
    assert asset_item["id"] == asset_id
    assert asset_item["sha256_checksum"] == full_sha256
    assert asset_item["size_bytes"] == len(wav_bytes)
    assert asset_item["codec"] == "pcm_wav"
    assert len(asset_item["derivatives"]) == 1
    derivative = asset_item["derivatives"][0]
    assert derivative["kind"] == "normalized_audio_wav_16k_mono"
    assert derivative["sha256_checksum"] != asset_item["sha256_checksum"]


def test_invalid_mime_disguised_signature_oversized_and_checksum_mismatch(
    client: TestClient,
) -> None:
    headers = _auth_headers("sub-sec", "sec@org.example.com")
    org = client.post("/api/v1/organisations", json={"name": "Media Validation Org"}, headers=headers).json()
    org_id = org["id"]
    ws_id = org["default_workspace_id"]
    headers = _auth_headers("sub-sec", "sec@org.example.com", org_id=org_id)

    meeting_id = client.post(
        "/api/v1/meetings",
        json={"workspace_id": ws_id, "title": "Validation Test Meeting"},
        headers=headers,
    ).json()["id"]
    client.post(
        f"/api/v1/meetings/{meeting_id}/recording-notice-confirm",
        json={"notice_version": "2026-11-v1", "host_confirmed": True},
        headers=headers,
    )

    # 1. Invalid MIME type rejected (415)
    bad_mime = client.post(
        f"/api/v1/meetings/{meeting_id}/uploads",
        json={
            "file_name": "malware.exe",
            "mime_type": "application/x-msdownload",
            "declared_size_bytes": 100,
            "expected_sha256": "a" * 64,
        },
        headers=headers,
    )
    assert bad_mime.status_code == 415
    assert bad_mime.json()["error"]["code"] == "unsupported_media_type"

    # 2. Oversized file rejected (413)
    oversized = client.post(
        f"/api/v1/meetings/{meeting_id}/uploads",
        json={
            "file_name": "huge.wav",
            "mime_type": "audio/wav",
            "declared_size_bytes": 10 * 1024 * 1024 * 1024,
            "expected_sha256": "b" * 64,
        },
        headers=headers,
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "upload_file_too_large"

    # 3. Executable ('MZ') disguised as audio/wav rejected on chunk 0 magic-byte check
    disguised_bytes = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    disguised_session = client.post(
        f"/api/v1/meetings/{meeting_id}/uploads",
        json={
            "file_name": "disguised.wav",
            "mime_type": "audio/wav",
            "declared_size_bytes": len(disguised_bytes),
            "expected_sha256": hashlib.sha256(disguised_bytes).hexdigest(),
        },
        headers=headers,
    ).json()["upload_session_id"]

    disguised_chunk_resp = client.put(
        f"/api/v1/meetings/{meeting_id}/uploads/{disguised_session}/chunks/0",
        json=_chunk_payload(disguised_bytes),
        headers=headers,
    )
    assert disguised_chunk_resp.status_code == 400
    assert (
        disguised_chunk_resp.json()["error"]["code"]
        == "malicious_or_disguised_file_signature"
    )

    # 4. Chunk checksum mismatch rejected (400)
    valid_wav = _make_sample_wav_bytes(64)
    mismatch_resp = client.put(
        f"/api/v1/meetings/{meeting_id}/uploads/{disguised_session}/chunks/0",
        json={
            "data_base64": base64.b64encode(valid_wav).decode("ascii"),
            "sha256_checksum": "0" * 64,
        },
        headers=headers,
    )
    assert mismatch_resp.status_code == 400
    assert mismatch_resp.json()["error"]["code"] == "chunk_checksum_mismatch"


def test_cross_tenant_media_denial_permission_denial_and_signed_playback_expiry(
    client: TestClient, db_session: Session
) -> None:
    # Tenant A setup
    headers_a = _auth_headers("sub-media-a", "a@tenant-a.example.com")
    org_a = client.post("/api/v1/organisations", json={"name": "Media Tenant A"}, headers=headers_a).json()
    org_a_id = org_a["id"]
    ws_a_id = org_a["default_workspace_id"]
    headers_a = _auth_headers("sub-media-a", "a@tenant-a.example.com", org_id=org_a_id)

    meeting_a_id = client.post(
        "/api/v1/meetings",
        json={"workspace_id": ws_a_id, "title": "Tenant A Confidential Meeting"},
        headers=headers_a,
    ).json()["id"]
    client.post(
        f"/api/v1/meetings/{meeting_a_id}/recording-notice-confirm",
        json={"notice_version": "2026-11-v1", "host_confirmed": True},
        headers=headers_a,
    )

    wav_bytes = _make_sample_wav_bytes(80)
    session_a_id = client.post(
        f"/api/v1/meetings/{meeting_a_id}/uploads",
        json={
            "file_name": "confidential.wav",
            "mime_type": "audio/wav",
            "declared_size_bytes": len(wav_bytes),
            "expected_sha256": hashlib.sha256(wav_bytes).hexdigest(),
        },
        headers=headers_a,
    ).json()["upload_session_id"]
    client.put(
        f"/api/v1/meetings/{meeting_a_id}/uploads/{session_a_id}/chunks/0",
        json=_chunk_payload(wav_bytes),
        headers=headers_a,
    )
    asset_a_id = client.post(
        f"/api/v1/meetings/{meeting_a_id}/uploads/{session_a_id}/complete",
        headers=headers_a,
    ).json()["media_asset_id"]

    # Add a Participant (read-only) in Tenant A
    part_user = User(
        supabase_sub="sub-part-a",
        email="part@tenant-a.example.com",
        full_name="Participant A",
        is_active=True,
    )
    db_session.add(part_user)
    db_session.flush()
    roles_a = bootstrap_organisation_roles(db_session, org_a_id)
    db_session.add(
        UserRole(
            organisation_id=org_a_id,
            user_id=part_user.id,
            role_id=roles_a["participant"].id,
            status="active",
        )
    )
    db_session.commit()
    headers_part_a = _auth_headers(
        "sub-part-a", "part@tenant-a.example.com", org_id=org_a_id
    )

    # Participant cannot create a meeting (`meeting.record` required) -> 403
    part_create = client.post(
        "/api/v1/meetings",
        json={"workspace_id": ws_a_id, "title": "Denied Meeting"},
        headers=headers_part_a,
    )
    assert part_create.status_code == 403
    assert part_create.json()["error"]["code"] == "insufficient_permissions"

    # Tenant B setup
    headers_b = _auth_headers("sub-media-b", "b@tenant-b.example.com")
    org_b = client.post("/api/v1/organisations", json={"name": "Media Tenant B"}, headers=headers_b).json()
    org_b_id = org_b["id"]
    headers_b = _auth_headers("sub-media-b", "b@tenant-b.example.com", org_id=org_b_id)

    # Tenant B cannot access Tenant A's meeting or media playback URL -> 404 (RLS isolated)
    assert client.get(f"/api/v1/meetings/{meeting_a_id}", headers=headers_b).status_code == 404
    assert (
        client.get(f"/api/v1/media/{asset_a_id}/playback-url", headers=headers_b).status_code
        == 404
    )

    # Tenant A requests valid short-lived playback URL and streams audio
    pb_resp = client.get(
        f"/api/v1/media/{asset_a_id}/playback-url", headers=headers_a
    )
    assert pb_resp.status_code == 200
    playback_url = pb_resp.json()["playback_url"]

    stream_resp = client.get(playback_url)
    assert stream_resp.status_code == 200
    assert stream_resp.content == wav_bytes

    # Expired signed playback URL is rejected with 403
    expired_signed = create_signed_playback_url(
        organisation_id=org_a_id,
        asset_id=asset_a_id,
        ttl_seconds=-10,
        now=datetime.now(timezone.utc) - timedelta(seconds=20),
    )
    expired_stream = client.get(str(expired_signed["url"]))
    assert expired_stream.status_code == 403
    assert expired_stream.json()["error"]["code"] == "playback_url_expired"

    # Tampered signature or cross-tenant org_id on playback URL is rejected with 403
    tampered_url = str(playback_url).replace(f"org_id={org_a_id}", f"org_id={org_b_id}")
    tampered_stream = client.get(tampered_url)
    assert tampered_stream.status_code == 403
    assert tampered_stream.json()["error"]["code"] == "invalid_playback_signature"
