# Shared Project Context — NEXUS Meeting Intelligence

## Purpose
This is the compact orientation document both OpenCode and Antigravity must read before substantial work. The detailed product and technical specifications remain authoritative for their respective subjects.

## Product identity
NEXUS Meeting Intelligence is the product described by the approved blueprint and the requirements in this repository. Do not add capabilities, pricing, integrations, or policies not supported by the approved requirements or a recorded owner decision.

## Canonical sources
- `README.md`: repository map, getting started and document index.
- `00_PRODUCT_REQUIREMENTS.md`: product scope and requirements.
- `01_ARCHITECTURE.md`: architecture principles and system boundaries.
- `03_DOMAIN_MODEL_AND_DATABASE.md`: domain entities and persistence.
- `04_API_AND_INTEGRATION_CONTRACTS.md`: interfaces and external integrations.
- `05_SECURITY_THREAT_MODEL.md`: threat and security controls.
- `06_PRIVACY_RECORDING_AND_VOICE_CONSENT.md`: recording, consent and voice governance.
- `14_DECISIONS_AND_ASSUMPTIONS.md` and `DECISIONS.md`: decisions and unresolved assumptions.
- `design/`: multi-agent collaboration operating rules.

If documents conflict, do not choose silently. Identify the conflict, cite the affected sections, and request owner direction or record a proposed resolution for approval.

## Technology choices
Use the stack explicitly established in the current repository and blueprint. Do not silently substitute frameworks, databases, hosting providers, AI services, or media pipelines. If the repository differs from the documentation, report the difference and propose a reconciliation.

## Agent behavior
- Inspect before modifying.
- Prefer small, reversible, testable changes.
- Preserve existing conventions unless an approved change says otherwise.
- Do not create duplicate implementations of auth, tenancy, storage, transcription, document generation, or voice governance.
- Do not expose secrets in code, logs, screenshots, prompts, or documentation.
- Treat recordings, transcripts, meeting documents and voice profiles as sensitive user content.
- Record assumptions and decisions rather than inventing policy.

## Current work snapshot
Keep this section updated by the project owner or lead agent:
- Current release/milestone: Not yet recorded.
- Active branch: Not yet recorded.
- Implemented features: Must be verified from repository and tests.
- Known blockers: Not yet recorded.
- Next approved task: Not yet recorded.
