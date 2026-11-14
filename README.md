# Jotly — NEXUS Meeting Intelligence

**Every Conversation Becomes Knowledge. Every Document Finds Its Voice.**

A standalone, multi-tenant enterprise platform for meeting recording, transcription,
speaker-aware records, document creation, document-to-speech, and consent-gated
voice profiles.

## What is in this repository

```text
apps/api/     FastAPI backend + background workers (Phases 1–9: tenancy, RLS, media,
              transcription, documents, TTS, voice governance, RAG intelligence,
              collaboration, release gate)
apps/web/     Next.js frontend (sign-in, dashboard, recorder, transcript editor)
infra/        Cloudflare edge worker + Hostinger self-hosting Docker Compose
docs/         Product & engineering specifications (source of truth)
design/       Dual-agent collaboration rules (OpenCode + Antigravity)
prompts/      Phase-by-phase build prompts
```

## Quality status

- **69 automated tests** across backend (53) and frontend (16) — all passing
- **GitHub Actions CI** runs 3 quality gates on every push: secret scan +
  voice-cloning lock, backend security suite, frontend typecheck/tests
- **8 reversible Alembic migrations** with PostgreSQL Row-Level Security on all
  49 tenant tables
- Voice cloning is hard-locked OFF (`VOICE_CLONING_ENABLED=false`) until the
  documented consent, verification, licensing and abuse-prevention gates pass

## Run it locally

Backend:
```bash
cd apps/api
pip install -r requirements.txt
pytest                 # runs the full security & behaviour suite
uvicorn app.main:app   # starts the API on http://localhost:8000
```

Frontend:
```bash
cd apps/web
npm install
npm run dev            # starts the web client on http://localhost:3000
```

## Deploy it (no coding required)

Follow **[DEPLOYMENT_GUIDE_NONCODER.md](DEPLOYMENT_GUIDE_NONCODER.md)** — a
click-by-click guide for Supabase (auth), Vercel (frontend), Hostinger (backend),
and Cloudflare (public address & protection).

## Operating model

OpenCode is the primary implementation agent; Antigravity is the complementary
design/review agent. Specifications under `docs/` and decision records in
`docs/architecture/DECISION_LOG.md` (ADR-001…ADR-005) govern all changes.

