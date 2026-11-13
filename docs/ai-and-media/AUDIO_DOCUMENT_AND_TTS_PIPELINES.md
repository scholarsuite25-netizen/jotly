# 08 — Audio, Document and Speech Processing Pipelines

## 1. Audio-to-document pipeline
Capture → encrypted upload → media validation → audio extraction → resampling/normalisation → optional voice activity detection → chunking → ASR → timestamp alignment → diarisation → transcript merge → human review → AI enrichment → export.

Preserve original media separately from processed derivatives. Store checksums, codec, sample rate, channels, duration, upload actor, and processing versions. Do not load entire long recordings into web application memory.

## 2. Media formats and validation
- Maintain an explicit supported-format allowlist.
- Validate file signature as well as declared MIME type.
- Enforce size and duration limits by plan and infrastructure capacity.
- Scan and process in isolated workers.
- Never execute embedded macros, scripts, or external links.
- Record source checksum and processing metadata.

## 3. Transcription
- Use a replaceable ASR adapter.
- Support language selection and timestamped segments.
- Record confidence metadata where available.
- Chunk long audio and merge segments deterministically.
- Preserve original transcript and subsequent human revisions.
- Benchmark word error rate by language, accent, noise, and meeting type.
- Do not claim perfect accuracy.

## 4. Speaker diarisation
- Treat speaker turns as model suggestions.
- Provide human correction and merge/split tools.
- Do not claim diarisation identifies a real person.
- Review each diarisation model's exact access and licence terms.

## 5. Document ingestion
- DOCX: parse text, paragraphs, headings, and tables where practical.
- PDF: extract text first; detect scanned pages and route to OCR.
- TXT/Markdown: decode safely and preserve paragraph boundaries.
- Display extraction/OCR warnings and allow user review.
- Do not execute macros, scripts, or external links in uploaded files.

## 6. Document export
Generate DOCX where editable output is needed. Render PDF with LibreOffice headless and compare output in automated visual tests. Use ReportLab for controlled PDF-only layouts where appropriate. Support organisation logo, brand colours, page numbers, headers, footers, confidentiality labels, meeting metadata, and revision information.

## 7. Document-to-speech pipeline
Upload/write text → extract → user review → choose approved language/voice/pronunciation/speed → permission check if clone → chunk at paragraph/sentence boundaries → queued synthesis → normalize loudness → join chunks → add optional chapters → export configured audio format → playback/download.

## 8. TTS requirements
- Standard TTS is independent of voice cloning.
- Choose language/voice from the actually supported catalogue.
- Store model ID/version and synthesis settings.
- Chunk long content and make jobs resumable.
- Test pronunciation, intelligibility, naturalness, continuity, and long-document reliability.
- Support WAV/MP3/OGG as configured.
- Include synthetic-audio disclosure when appropriate.

## 9. Job reliability
Every long task has queued/running/succeeded/failed/cancelled states, progress, retry count, idempotency key, worker version, and safe error message. Retries must not create duplicate exports or duplicate charges. Use bounded queues and tenant-aware concurrency limits.
