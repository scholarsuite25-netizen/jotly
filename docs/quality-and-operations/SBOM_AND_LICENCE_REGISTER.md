# Software Bill of Materials (SBOM), Model & Licence Governance Register

> Maintained pursuant to `docs/quality-and-operations/OPEN_SOURCE_AND_LICENCE_GOVERNANCE.md`.

## 1. Phase 1 Application & Infrastructure Dependencies

| Component | Layer | Version / Constraint | Licence | Commercial Use Verified | Status |
|---|---|---|---|---|---|
| Python | Backend Runtime | 3.12+ | PSF-2.0 | Yes | Approved (Phase 1) |
| FastAPI | Backend API | >=0.110.0 | MIT | Yes | Approved (Phase 1) |
| SQLAlchemy | ORM & RLS Context | >=2.0.28 | MIT | Yes | Approved (Phase 1) |
| Alembic | DB Migrations | >=1.13.1 | MIT | Yes | Approved (Phase 1) |
| Pydantic / Settings | Schema Validation | >=2.6.0 | MIT | Yes | Approved (Phase 1) |
| PyJWT | Supabase JWT Verification | >=2.8.0 | MIT | Yes | Approved (Phase 1) |
| httpx | HTTP / Email Adapter | >=0.27.0 | BSD-3-Clause | Yes | Approved (Phase 1) |
| PostgreSQL 16 | Relational DB + RLS | 16-alpine | PostgreSQL Licence | Yes | Approved (Phase 1) |
| Redis 7 | Queue & Cache | 7-alpine | BSD-3-Clause (7.2) | Yes | Approved (Phase 1) |
| Next.js / React | Web Client (Vercel) | 14+ / 18+ | MIT | Yes | Approved (Phase 1) |

## 2. External Cloud & Self-Hosted Service Integrations

| Service | Role | Data Scope | Governance Notes |
|---|---|---|---|
| **Supabase Auth** | Identity Provider (OIDC/JWT) | Account identity (`sub`, `email`, `aal`) | Server-side JWT verification in FastAPI |
| **Vercel** | Frontend Hosting | Next.js web assets | No storage or model secrets in client bundle |
| **Cloudflare** | Edge WAF, Tunnel & R2 Storage | Encrypted API ingress & private object buckets | Short-lived presigned URLs only |
| **Hostinger VPS** | Self-Hosted Compute | FastAPI API, workers, PostgreSQL/Redis | Isolated internal Docker network |
| **Resend / Emailbump / Unipost** | Transactional Email Failover Chain | Invitations & security alerts only | Raw transcripts/voice samples strictly blocked |

## 3. AI & Media Models Register (Gated for Phases 2–7)

| Candidate | Target Phase | Gate Status |
|---|---|---|
| FFmpeg | Phase 2 | Pending build-flag LGPL/GPL review in Phase 2 |
| faster-whisper | Phase 3 | Pending weight checksum & benchmark in Phase 3 |
| WhisperX / Diarisation | Phase 3 | Pending model-card & access licence review |
| python-docx / LibreOffice / ReportLab | Phase 4 | Pending notice & visual regression harness |
| Kokoro / CosyVoice | Phase 5 | Pending voice-pack & phonemizer licence review |
| OpenVoice V2 | Phase 6 | **LOCKED OFF (`VOICE_CLONING_ENABLED=false`)** |
| Ollama + LLM Weights | Phase 7 | Pending specific model weight licence sign-off |
