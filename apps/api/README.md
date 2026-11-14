# NEXUS Meeting Intelligence — Backend & Worker Foundation

FastAPI backend for the Jotly (NEXUS Meeting Intelligence) platform:
multi-tenant foundation, recording/media, transcription, documents, TTS,
voice governance, meeting intelligence, collaboration, and release gate.

## Local setup

```bash
pip install -r requirements.txt
pytest                 # 52 automated security & behaviour tests
uvicorn app.main:app   # API on http://localhost:8000 (docs at /api/v1/docs)
```

## Package build

The project builds as a standard Python package (`setuptools` via
`pyproject.toml`); `migrations/` and `tests/` are excluded from the wheel.

## Deployment

Runs in Docker on a self-hosted Hostinger VPS via
`infra/hostinger/docker-compose.hostinger.yml` (see the repository root
`DEPLOYMENT_GUIDE_NONCODER.md`). Vercel hosts only the frontend (`apps/web`).
