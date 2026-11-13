# Phase Prompt — Phase 4: Document Studio (OpenCode Lead / Antigravity Review)

Implement document ingestion and export.

Requirements:
- Generate editable DOCX and printable PDF for transcripts, minutes, summaries, decisions, and action items.
- Support templates with organisation logo/brand colours, headers, footers, page numbers, confidentiality labels, and source metadata.
- Ingest DOCX/PDF/TXT.
- Extract paragraphs, headings, and tables where practical.
- Detect scanned PDF pages and route to a separately configured OCR step with a user-facing warning.
- Treat uploads as untrusted; never execute macros, scripts, or external links.
- Use python-docx for DOCX generation; LibreOffice headless for PDF rendering; ReportLab for controlled PDF-only layouts where suitable.
- Version exports and retain source linkage.
- Run visual regression checks for page breaks, tables, headers, fonts, and special characters.

Test malformed files, large files, scanned pages, tables, extraction fidelity, and tenant access.
