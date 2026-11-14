import hashlib
import importlib
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_supabase_test_jwt

_0003_mod = importlib.import_module("migrations.versions.0003_phase3_transcription")

REFERENCE_SCRIPT = (
    "Good morning everyone. Let's review yesterday's action items. "
    "Sarah will lead the follow-up on the client proposal. "
    "The deadline for the revised draft is Friday."
)


def _auth_headers(sub: str, email: str, org_id: str | None = None) -> dict[str, str]:
    token = create_supabase_test_jwt(sub=sub, email=email)
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organisation-ID"] = org_id
    return headers


def _create_meeting_and_asset(client: TestClient, sub: str, email: str) -> tuple[str, dict[str, str]]:
    headers = _auth_headers(sub, email)
    org = client.post("/api/v1/organisations", json={"name": f"Org {sub}"}, headers=headers).json()
    org_id = org["id"]
    ws_id = org["default_workspace_id"]
    headers = _auth_headers(sub, email, org_id=org_id)

    meeting_id = client.post(
        "/api/v1/meetings",
        json={"workspace_id": ws_id, "title": f"Meeting {sub}"},
        headers=headers,
    ).json()["id"]

    client.post(
        f"/api/v1/meetings/{meeting_id}/recording-notice-confirm",
        json={"notice_version": "2026-11-v1", "host_confirmed": True},
        headers=headers,
    )

    # Build a validated WAV asset directly by completing the upload flow
    header = b"RIFF" + (36 + 64).to_bytes(4, "little") + b"WAVEfmt "
    header += (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
    header += (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little")
    header += (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    header += b"data" + (64).to_bytes(4, "little")
    wav_bytes = header + (b"\x01\x02" * 32)

    session_id = client.post(
        f"/api/v1/meetings/{meeting_id}/uploads",
        json={
            "file_name": f"{sub}.wav",
            "mime_type": "audio/wav",
            "declared_size_bytes": len(wav_bytes),
            "expected_sha256": hashlib.sha256(wav_bytes).hexdigest(),
        },
        headers=headers,
    ).json()["upload_session_id"]
    client.put(
        f"/api/v1/meetings/{meeting_id}/uploads/{session_id}/chunks/0",
        json={
            "data_base64": __import__("base64").b64encode(wav_bytes).decode("ascii"),
            "sha256_checksum": hashlib.sha256(wav_bytes).hexdigest(),
        },
        headers=headers,
    )
    asset_id = client.post(
        f"/api/v1/meetings/{meeting_id}/uploads/{session_id}/complete",
        headers=headers,
    ).json()["media_asset_id"]
    return asset_id, headers


def test_phase3_postgres_rls_migration_ddl() -> None:
    stmts = _0003_mod.get_phase3_postgres_rls_upgrade_sql()
    joined = "\n".join(stmts)
    for table in _0003_mod.PHASE3_TENANT_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in joined
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in joined
        assert f"CREATE POLICY tenant_isolation_{table} ON {table}" in joined


def test_transcription_queue_execute_segments_and_confidence(
    client: TestClient,
) -> None:
    asset_id, headers = _create_meeting_and_asset(client, "sub-tx-1", "tx1@org.example.com")

    queue_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    assert queue_resp.status_code == 202
    job_id = queue_resp.json()["job_id"]

    exec_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions/{job_id}/execute",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    assert exec_resp.status_code == 200
    transcript_id = exec_resp.json()["transcript_id"]
    assert exec_resp.json()["asr_model_id"] == "stub-asr-deterministic"
    assert exec_resp.json()["detected_language"] == "en"

    detail_resp = client.get(f"/api/v1/transcripts/{transcript_id}", headers=headers)
    assert detail_resp.status_code == 200
    body = detail_resp.json()
    assert len(body["segments"]) >= 1
    assert body["segments"][0]["original_asr_text"]
    assert body["segments"][0]["confidence"] >= 0.80
    assert body["segments"][0]["start_ms"] == 0

    # Segment timestamps are non-negative and sequence numbering is deterministic
    for idx, seg in enumerate(body["segments"]):
        assert seg["sequence_number"] == idx
        assert seg["start_ms"] >= 0
        assert seg["end_ms"] > seg["start_ms"]


def test_human_edit_undo_and_revision_history(
    client: TestClient,
) -> None:
    asset_id, headers = _create_meeting_and_asset(client, "sub-tx-2", "tx2@org.example.com")
    queue_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    job_id = queue_resp.json()["job_id"]

    # Use transcript id from execute response directly (second call replays idempotently)
    exec_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions/{job_id}/execute",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    transcript_id = exec_resp.json()["transcript_id"]

    detail = client.get(f"/api/v1/transcripts/{transcript_id}", headers=headers).json()
    segment_id = detail["segments"][0]["id"]
    original_text = detail["segments"][0]["original_asr_text"]

    # Human edit
    edit_resp = client.patch(
        f"/api/v1/transcripts/{transcript_id}/segments/{segment_id}",
        json={"new_text": "Good afternoon everyone."},
        headers=headers,
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["current_text"] == "Good afternoon everyone."
    assert edit_resp.json()["original_asr_text"] == original_text
    assert edit_resp.json()["is_edited"] is True
    assert edit_resp.json()["changed"] is True

    # Undo restores the previous text
    undo_resp = client.post(
        f"/api/v1/transcripts/{transcript_id}/segments/{segment_id}/undo",
        headers=headers,
    )
    assert undo_resp.status_code == 200
    assert undo_resp.json()["current_text"] == original_text
    assert undo_resp.json()["is_edited"] is False

    # Revision history records text_edit AND undo changes
    detail_after = client.get(
        f"/api/v1/transcripts/{transcript_id}", headers=headers
    ).json()
    change_types = [r["change_type"] for r in detail_after["revisions"]]
    assert "text_edit" in change_types
    assert "undo" in change_types
    assert len(detail_after["revisions"]) == 2


def test_speaker_diarisation_suggestion_and_relabel_not_identity_verification(
    client: TestClient,
) -> None:
    asset_id, headers = _create_meeting_and_asset(client, "sub-tx-3", "tx3@org.example.com")
    queue_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions",
        json={"language_code": "en", "enable_diarisation": True},
        headers=headers,
    )
    job_id = queue_resp.json()["job_id"]
    exec_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions/{job_id}/execute",
        json={"language_code": "en", "enable_diarisation": True},
        headers=headers,
    )
    transcript_id = exec_resp.json()["transcript_id"]

    detail = client.get(f"/api/v1/transcripts/{transcript_id}", headers=headers).json()
    assert detail["diarisation_enabled"] is True
    speakers = detail["speakers"]
    assert len(speakers) >= 1

    # Diarisation labels MUST be model suggestions, never verified identity
    for speaker in speakers:
        assert speaker["is_model_suggestion"] is True
        assert speaker["identity_verified"] is False

    for seg in detail["segments"]:
        if seg["speaker_id"] is not None:
            assert seg["speaker_is_model_suggestion"] is True

    # Human relabel renames the speaker; still a suggestion, still not verified identity
    speaker_id = speakers[0]["id"]
    relabel_resp = client.post(
        f"/api/v1/transcripts/{transcript_id}/speakers/{speaker_id}/relabel",
        json={"display_name": "Sarah Chen"},
        headers=headers,
    )
    assert relabel_resp.status_code == 200
    assert relabel_resp.json()["display_name"] == "Sarah Chen"
    assert relabel_resp.json()["is_model_suggestion"] is True
    assert relabel_resp.json()["identity_verified"] is False


def test_find_replace_preview_and_apply(
    client: TestClient,
) -> None:
    asset_id, headers = _create_meeting_and_asset(client, "sub-tx-4", "tx4@org.example.com")
    queue_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    job_id = queue_resp.json()["job_id"]
    exec_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions/{job_id}/execute",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    transcript_id = exec_resp.json()["transcript_id"]

    # Preview lists affected segments before applying
    preview = client.post(
        f"/api/v1/transcripts/{transcript_id}/find-replace",
        json={"find_text": "welcome", "replace_text": "Greetings", "case_sensitive": False},
        headers=headers,
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["transcript_id"] == transcript_id
    assert preview_body["replacement_count"] >= 1
    assert len(preview_body["replacements"]) == preview_body["replacement_count"]
    assert preview_body["revision_number"] is not None

    # Replay with a term that appears nowhere -> zero replacements
    none_resp = client.post(
        f"/api/v1/transcripts/{transcript_id}/find-replace",
        json={"find_text": "nonexistent-term", "replace_text": "x", "case_sensitive": False},
        headers=headers,
    )
    assert none_resp.status_code == 200
    assert none_resp.json()["replacement_count"] == 0


def test_export_txt_srt_vtt_formats(
    client: TestClient,
) -> None:
    asset_id, headers = _create_meeting_and_asset(client, "sub-tx-5", "tx5@org.example.com")
    queue_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    job_id = queue_resp.json()["job_id"]
    exec_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions/{job_id}/execute",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    transcript_id = exec_resp.json()["transcript_id"]

    for fmt, marker in (
        ("txt", "welcome everyone to the quarterly review"),
        ("srt", "00:00:00,000"),
        ("vtt", "WEBVTT"),
    ):
        export_resp = client.post(
            f"/api/v1/transcripts/{transcript_id}/exports",
            json={"format": fmt},
            headers=headers,
        )
        assert export_resp.status_code == 201
        assert marker in export_resp.json()["content"]

    bad_format = client.post(
        f"/api/v1/transcripts/{transcript_id}/exports",
        json={"format": "docx"},
        headers=headers,
    )
    assert bad_format.status_code == 415


def test_cross_tenant_transcript_and_job_isolation(client: TestClient) -> None:
    asset_id_a, headers_a = _create_meeting_and_asset(
        client, "sub-iso-a", "iso-a@tenant-a.example.com"
    )
    asset_id_b, headers_b = _create_meeting_and_asset(
        client, "sub-iso-b", "iso-b@tenant-b.example.com"
    )

    queue_b = client.post(
        f"/api/v1/media/{asset_id_b}/transcriptions",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers_b,
    )
    job_b_id = queue_b.json()["job_id"]

    # Tenant B queues and executes; transcript stays in Tenant B
    exec_b = client.post(
        f"/api/v1/media/{asset_id_b}/transcriptions/{job_b_id}/execute",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers_b,
    )
    transcript_b_id = exec_b.json()["transcript_id"]

    # Tenant A cannot read Tenant B's transcript (RLS isolation) -> 404
    resp = client.get(
        f"/api/v1/transcripts/{transcript_b_id}", headers=headers_a
    )
    assert resp.status_code == 404

    # Tenant A cannot execute Tenant B's queued job -> tenant isolation violation
    resp = client.post(
        f"/api/v1/media/{asset_id_b}/transcriptions/{job_b_id}/execute",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers_a,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "worker_tenant_isolation_violation"


def test_wer_evaluation_harness(client: TestClient) -> None:
    asset_id, headers = _create_meeting_and_asset(client, "sub-tx-6", "tx6@org.example.com")
    queue_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    job_id = queue_resp.json()["job_id"]
    exec_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions/{job_id}/execute",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    transcript_id = exec_resp.json()["transcript_id"]

    eval_resp = client.post(
        f"/api/v1/transcripts/{transcript_id}/evaluation",
        json={"reference_script": REFERENCE_SCRIPT},
        headers=headers,
    )
    assert eval_resp.status_code == 200
    body = eval_resp.json()
    assert 0.0 <= body["wer"] <= 2.0
    assert body["accuracy"] == round(max(0.0, 1.0 - body["wer"]), 4)
    assert body["disclaimer"] is not None
    assert body["reference_word_count"] > 0
    assert body["hypothesis_word_count"] > 0
    assert len(body["segments"]) >= 1

    # Per-segment metrics present
    assert all("segment_wer" in s for s in body["segments"])


def test_meeting_transcript_listing_and_tenant_isolation(client: TestClient) -> None:
    """Dashboard discovery: list transcripts per meeting, empty state, 404, isolation."""
    asset_id, headers = _create_meeting_and_asset(
        client, "sub-tx-list", "txlist@org.example.com"
    )
    meeting_id = client.get("/api/v1/meetings", headers=headers).json()["items"][0]["id"]

    # Empty before any transcription: UI can render an explicit empty state.
    empty = client.get(f"/api/v1/meetings/{meeting_id}/transcripts", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["items"] == []

    queue_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    exec_resp = client.post(
        f"/api/v1/media/{asset_id}/transcriptions/{queue_resp.json()['job_id']}/execute",
        json={"language_code": "en", "enable_diarisation": False},
        headers=headers,
    )
    transcript_id = exec_resp.json()["transcript_id"]

    listing = client.get(f"/api/v1/meetings/{meeting_id}/transcripts", headers=headers)
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == transcript_id
    assert items[0]["status"] == "completed"
    assert items[0]["media_asset_id"] == asset_id

    # Unknown meeting -> 404 (same contract as the media listing)
    missing = client.get(
        "/api/v1/meetings/00000000-0000-0000-0000-000000000000/transcripts",
        headers=headers,
    )
    assert missing.status_code == 404

    # Cross-tenant: another organisation cannot enumerate this meeting's transcripts
    other = _auth_headers("sub-tx-other", "txother@org.example.com")
    other_org = client.post(
        "/api/v1/organisations", json={"name": "Org other-tx-list"}, headers=other
    ).json()
    other_headers = _auth_headers(
        "sub-tx-other", "txother@org.example.com", org_id=other_org["id"]
    )
    cross = client.get(
        f"/api/v1/meetings/{meeting_id}/transcripts", headers=other_headers
    )
    assert cross.status_code in (403, 404)
