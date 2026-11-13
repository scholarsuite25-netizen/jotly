# Phase Prompt — Phase 6: Consent-Gated Voice Governance (OpenCode Lead / Antigravity Review)

This phase is high risk. Do not enable public voice cloning. Build governance and a restricted evaluation environment first.

Requirements:
- Explicit voice-owner consent and proportionate identity/authority verification.
- Consent text version, purpose, permitted uses, jurisdiction, expiry, verification method, timestamp, and revocation.
- Private-by-default voice profile.
- Owner-controlled permission scopes and expiry.
- Server-side checks for owner, tenant, consent status, grantee, use case, expiry, quota, and revocation before every synthesis.
- Immediate blocking after revocation.
- Audit clone enrolment, sample access, profile access, synthesis, export, revocation, and deletion.
- Rate limits, abuse detection, suspicious-use review, and escalation.
- AI-generated/synthetic disclosure and provenance metadata.
- Deletion workflow for samples and derived artefacts, subject to documented legal holds and backup expiry.
- No anonymous or bulk cloning; no public gallery by default.
- No use for authentication, financial authorisation, emergency instructions, or identity verification.
- Do not use real third-party voice data without documented authorisation.

Evaluate OpenVoice V2 and alternatives only after reviewing exact code, checkpoint, dependencies, asset terms, and intended commercial use. Add negative tests proving unauthorised, expired, revoked, cross-tenant, and out-of-scope synthesis is denied.

Keep the public feature flag disabled until legal, security, licensing, abuse, quality, and operational gates are signed off.
