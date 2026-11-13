"""Document ingestion: DOCX/PDF/TXT extraction with scanned-page OCR detection."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import NexusAPIError

ALLOWED_DOCUMENT_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/pdf",
        "text/plain",
    }
)

MAX_INGEST_FILE_SIZE_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class DocumentIngestResult:
    extracted_text: str
    ocr_applied: bool
    ocr_pages_detected: int
    paragraph_count: int


def _detect_scanned_pdf_pages(pdf_bytes: bytes) -> int:
    """
    Deterministic heuristic detecting image-only (scanned) PDF pages:
    pages containing XObject image streams without extractable text operators.
    """
    if b"/Image" in pdf_bytes or b"/DCTDecode" in pdf_bytes or b"/JPXDecode" in pdf_bytes:
        # Count image-bearing pages conservatively (each XObject entry).
        image_markers = (
            pdf_bytes.count(b"/Subtype /Image")
            + pdf_bytes.count(b"/Subtype/Image")
        )
        text_ops = pdf_bytes.count(b"BT") + pdf_bytes.count(b"Tj")
        if text_ops == 0:
            return max(1, image_markers)
        return max(0, image_markers - max(1, text_ops // 100))
    return 0


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        import PyPDF2  # type: ignore

        reader = PyPDF2.PdfReader(io := __import__("io").BytesIO(pdf_bytes))
        parts: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            parts.append(text.strip())
        return "\n\n".join(p for p in parts if p)
    except ImportError:
        # Fallback deterministic extraction of parenthesised PDF text operators.
        import io
        import re

        matches = re.findall(rb"\((?:[^()\\]|\\.)*\)", pdf_bytes)
        words: list[str] = []
        for match in matches:
            word = match[1:-1].decode("latin-1", errors="ignore").strip()
            if word and not word.startswith("/"):
                words.append(word)
        return " ".join(words)


def _extract_docx_text(docx_bytes: bytes) -> str:
    try:
        import io

        import docx  # type: ignore

        document = docx.Document(io.BytesIO(docx_bytes))
        paragraphs: list[str] = []
        for para in document.paragraphs:
            if para.text and para.text.strip():
                paragraphs.append(para.text.strip())
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
                if cells:
                    paragraphs.append(" | ".join(cells))
        return "\n".join(paragraphs)
    except Exception:
        # Fallback: deterministic plain-XML text scrape from DOCX zip.
        import io
        import re
        import zipfile

        try:
            with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
                xml_bytes = zf.read("word/document.xml")
            text_nodes = re.findall(rb"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", xml_bytes)
            decoded = [t.decode("utf-8", errors="ignore").strip() for t in text_nodes]
            return "\n".join(t for t in decoded if t)
        except Exception as exc:
            raise NexusAPIError(
                status_code=400,
                code="document_parse_failed",
                message="Uploaded DOCX file could not be parsed safely.",
            ) from exc


def ingest_document_bytes(
    *,
    file_name: str,
    mime_type: str,
    payload: bytes,
) -> DocumentIngestResult:
    """
    Validates and extracts text from uploaded DOCX/PDF/TXT documents.
    Treats uploads strictly as untrusted data — never executes macros, scripts,
    or embedded links; extraction is read-only and sandboxed to in-memory bytes.
    """
    normalized = mime_type.split(";")[0].strip().lower()
    if normalized not in ALLOWED_DOCUMENT_MIME_TYPES:
        raise NexusAPIError(
            status_code=415,
            code="unsupported_document_type",
            message=f"MIME type '{normalized}' is not on the approved document allowlist.",
        )
    if len(payload) > MAX_INGEST_FILE_SIZE_BYTES:
        raise NexusAPIError(
            status_code=413,
            code="document_too_large",
            message=f"Document exceeds the {MAX_INGEST_FILE_SIZE_BYTES} byte ingest limit.",
        )
    if not payload:
        raise NexusAPIError(
            status_code=400,
            code="document_empty",
            message="Uploaded document is empty.",
        )

    ocr_applied = False
    ocr_pages = 0

    if normalized == "text/plain":
        try:
            extracted = payload.decode("utf-8")
        except UnicodeDecodeError:
            extracted = payload.decode("latin-1", errors="ignore")
    elif normalized == "application/pdf":
        ocr_pages = _detect_scanned_pdf_pages(payload)
        extracted = _extract_pdf_text(payload)
        ocr_applied = ocr_pages > 0
    else:
        extracted = _extract_docx_text(payload)

    paragraphs = [p for p in extracted.split("\n") if p.strip()]
    if not paragraphs:
        # Scanned/image-only documents legitimately have no extractable text layer;
        # route them through the OCR review path instead of hard-failing ingestion.
        if normalized == "application/pdf":
            ocr_pages = max(1, _detect_scanned_pdf_pages(payload))
            ocr_applied = True
            extracted = ""
            paragraphs = []
        else:
            raise NexusAPIError(
                status_code=422,
                code="document_no_extractable_text",
                message="No extractable text found in the uploaded document.",
            )

    return DocumentIngestResult(
        extracted_text=extracted.strip(),
        ocr_applied=ocr_applied,
        ocr_pages_detected=ocr_pages,
        paragraph_count=len(paragraphs),
    )
