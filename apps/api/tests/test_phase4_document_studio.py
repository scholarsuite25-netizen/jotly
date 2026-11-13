import base64
import hashlib
import importlib
import io
import zipfile

from fastapi.testclient import TestClient

from app.core.security import create_supabase_test_jwt

_0004_mod = importlib.import_module("migrations.versions.0004_phase4_document_studio")

DOCX_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
    "<w:body>"
    "<w:p><w:r><w:t>Board minutes from the quarterly review meeting.</w:t></w:r></w:p>"
    "<w:p><w:r><w:t>Action items: Sarah leads the proposal follow-up.</w:t></w:r></w:p>"
    "</w:body></w:document>"
)


def _make_docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        zf.writestr("word/document.xml", DOCX_XML)
    return buffer.getvalue()


def _auth_headers(sub: str, email: str, org_id: str | None = None) -> dict[str, str]:
    token = create_supabase_test_jwt(sub=sub, email=email)
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organisation-ID"] = org_id
    return headers


def _make_simple_pdf_bytes(with_text: bool = True) -> bytes:
    if with_text:
        content_stream = b"BT /F1 12 Tf 100 700 Td (Quarterly financial summary extracted from text layer.) Tj ET"
    else:
        content_stream = b""
    pdf = b"%PDF-1.4\n"
    pdf += b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    pdf += b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
    pdf += (
        b"3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R "
        b"/Resources << /XObject << /Im1 5 0 R >> >> >> endobj\n"
    )
    pdf += b"4 0 obj << /Length " + str(len(content_stream)).encode() + b" >> stream\n"
    pdf += content_stream + b"\nendstream endobj\n"
    pdf += (
        b"5 0 obj << /Type /XObject /Subtype /Image /Width 100 /Height 100 "
        b"/Filter /DCTDecode >> stream\n"
    )
    pdf += b"\xff\xd8\xff\xe0JFIF-synthetic-jpeg-payload\xff\xd9\nendstream endobj\n"
    pdf += b"trailer << /Root 1 0 R >>\n%%EOF\n"
    return pdf


def test_phase4_postgres_rls_migration_ddl() -> None:
    stmts = _0004_mod.get_phase4_postgres_rls_upgrade_sql()
    joined = "\n".join(stmts)
    for table in _0004_mod.PHASE4_TENANT_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in joined
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in joined
        assert f"CREATE POLICY tenant_isolation_{table} ON {table}" in joined


def test_document_ingest_docx_pdf_txt_and_ocr_detection(client: TestClient) -> None:
    headers = _auth_headers("sub-doc-1", "doc1@org.example.com")
    client.post("/api/v1/organisations", json={"name": "Doc Org"}, headers=headers)
    me = client.get("/api/v1/me", headers=headers).json()
    org_id = me["active_organisation"]["id"]
    headers = _auth_headers("sub-doc-1", "doc1@org.example.com", org_id=org_id)

    # DOCX ingest with paragraph extraction
    docx_bytes = _make_docx_bytes()
    docx_resp = client.post(
        "/api/v1/documents/ingest",
        json={
            "title": "Q4 Board Minutes",
            "document_type": "ingested",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "file_name": "board-minutes.docx",
            "content_base64": base64.b64encode(docx_bytes).decode("ascii"),
        },
        headers=headers,
    )
    assert docx_resp.status_code == 202
    body = docx_resp.json()
    assert body["paragraph_count"] >= 2
    assert "Board minutes" in body["extracted_text_preview"]
    assert body["ocr_applied"] is False

    # PDF with text layer -> no OCR warning
    pdf_text = _make_simple_pdf_bytes(with_text=True)
    pdf_resp = client.post(
        "/api/v1/documents/ingest",
        json={
            "title": "Financial Summary",
            "document_type": "ingested",
            "mime_type": "application/pdf",
            "file_name": "summary.pdf",
            "content_base64": base64.b64encode(pdf_text).decode("ascii"),
        },
        headers=headers,
    )
    assert pdf_resp.status_code == 202
    pdf_body = pdf_resp.json()
    assert pdf_body["paragraph_count"] >= 1
    assert pdf_body["ocr_applied"] is False
    assert pdf_body["ocr_review_warning"] is None

    # Scanned (image-only) PDF -> OCR detection + user-facing review warning
    pdf_scanned = _make_simple_pdf_bytes(with_text=False)
    scanned_resp = client.post(
        "/api/v1/documents/ingest",
        json={
            "title": "Scanned Contract",
            "document_type": "ingested",
            "mime_type": "application/pdf",
            "file_name": "contract-scan.pdf",
            "content_base64": base64.b64encode(pdf_scanned).decode("ascii"),
        },
        headers=headers,
    )
    assert scanned_resp.status_code == 202
    scanned_body = scanned_resp.json()
    assert scanned_body["ocr_applied"] is True
    assert scanned_body["ocr_pages_detected"] >= 1
    assert scanned_body["ocr_review_warning"] is not None
    assert "requires human review" in scanned_body["ocr_review_warning"]

    # TXT ingest
    txt_bytes = b"Meeting notes from the strategy session.\nAction item one.\nAction item two."
    txt_resp = client.post(
        "/api/v1/documents/ingest",
        json={
            "title": "Strategy Notes",
            "document_type": "ingested",
            "mime_type": "text/plain",
            "file_name": "notes.txt",
            "content_base64": base64.b64encode(txt_bytes).decode("ascii"),
        },
        headers=headers,
    )
    assert txt_resp.status_code == 202
    assert txt_resp.json()["paragraph_count"] == 3

    # Invalid MIME rejected
    bad_resp = client.post(
        "/api/v1/documents/ingest",
        json={
            "title": "Macro Doc",
            "document_type": "ingested",
            "mime_type": "application/x-msdownload",
            "file_name": "macro.exe",
            "content_base64": base64.b64encode(b"MZ\x90\x00").decode("ascii"),
        },
        headers=headers,
    )
    assert bad_resp.status_code == 415


def test_branded_docx_pdf_txt_export_with_template_and_source_linkage(
    client: TestClient,
) -> None:
    headers = _auth_headers("sub-doc-2", "doc2@org.example.com")
    client.post("/api/v1/organisations", json={"name": "Export Org"}, headers=headers)
    me = client.get("/api/v1/me", headers=headers).json()
    org_id = me["active_organisation"]["id"]
    headers = _auth_headers("sub-doc-2", "doc2@org.example.com", org_id=org_id)

    template_resp = client.post(
        "/api/v1/documents/templates",
        json={
            "template_name": "Corporate Branded",
            "brand_primary_color": "#0B4F6C",
            "header_text": "Acme Legal — Confidential Working Document",
            "footer_text": "Acme Legal © 2026",
            "confidentiality_label": "Internal Use Only",
        },
        headers=headers,
    )
    assert template_resp.status_code == 201
    template_id = template_resp.json()["template_id"]

    # Create document from a transcript for branded export
    doc_resp = client.post(
        "/api/v1/documents/ingest",
        json={
            "title": "Branded Report",
            "document_type": "ingested",
            "mime_type": "text/plain",
            "file_name": "report.txt",
            "content_base64": base64.b64encode(b"Quarterly review narrative content.").decode("ascii"),
        },
        headers=headers,
    )
    assert doc_resp.status_code == 202
    document_id = doc_resp.json()["document_id"]

    for fmt, min_bytes in (("docx", 10), ("pdf", 10), ("txt", 10)):
        export_resp = client.post(
            f"/api/v1/documents/{document_id}/export",
            json={"export_format": fmt, "template_id": template_id},
            headers=headers,
        )
        assert export_resp.status_code == 200, export_resp.text
        body = export_resp.json()
        assert body["format"] == fmt
        assert body["size_bytes"] >= min_bytes
        assert len(body["sha256_checksum"]) == 64
        assert body["template_id"] == template_id
        assert body["object_key"].startswith(f"tenants/{org_id}/documents/{document_id}/exports/")

    # Unsupported format rejected
    bad_export = client.post(
        f"/api/v1/documents/{document_id}/export",
        json={"export_format": "xlsx"},
        headers=headers,
    )
    assert bad_export.status_code == 415

    exports_list = client.get(
        f"/api/v1/documents/{document_id}/exports", headers=headers
    )
    assert exports_list.status_code == 200
    assert len(exports_list.json()["items"]) == 3


def test_template_duplicate_and_tenant_isolation(client: TestClient) -> None:
    headers = _auth_headers("sub-doc-3", "doc3@org.example.com")
    client.post("/api/v1/organisations", json={"name": "Template Org"}, headers=headers)
    me = client.get("/api/v1/me", headers=headers).json()
    org_id = me["active_organisation"]["id"]
    headers = _auth_headers("sub-doc-3", "doc3@org.example.com", org_id=org_id)

    first = client.post(
        "/api/v1/documents/templates",
        json={"template_name": "Standard Minutes", "confidentiality_label": "Restricted"},
        headers=headers,
    )
    assert first.status_code == 201
    template_id = first.json()["template_id"]

    duplicate = client.post(
        "/api/v1/documents/templates",
        json={"template_name": "Standard Minutes"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    # Ingest a document in this org
    doc_resp = client.post(
        "/api/v1/documents/ingest",
        json={
            "title": "Private Document",
            "document_type": "ingested",
            "mime_type": "text/plain",
            "file_name": "private.txt",
            "content_base64": base64.b64encode(b"Private narrative").decode("ascii"),
        },
        headers=headers,
    )
    document_id = doc_resp.json()["document_id"]

    # Tenant B cannot export Tenant A's document
    other_headers = _auth_headers("sub-doc-b", "doc-b@other.example.com")
    client.post("/api/v1/organisations", json={"name": "Other Org"}, headers=other_headers)
    me_b = client.get("/api/v1/me", headers=other_headers).json()
    org_b = me_b["active_organisation"]["id"]
    other_headers = _auth_headers("sub-doc-b", "doc-b@other.example.com", org_id=org_b)

    cross_export = client.post(
        f"/api/v1/documents/{document_id}/export",
        json={"export_format": "txt"},
        headers=other_headers,
    )
    assert cross_export.status_code == 404

    # Tenant A exports using its own template successfully
    ok_export = client.post(
        f"/api/v1/documents/{document_id}/export",
        json={"export_format": "txt", "template_id": template_id},
        headers=headers,
    )
    assert ok_export.status_code == 200
    assert "Private narrative" in ok_export.content.decode("utf-8", errors="ignore") or ok_export.json()["size_bytes"] > 0
