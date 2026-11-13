# 06 — Privacy, Recording and Voice Consent Policy Requirements

> This is a product and engineering requirements document, not legal advice. Obtain qualified counsel for each target jurisdiction and customer sector.

## 1. Data categories
NEXUS may process:
- meeting audio/video and transcripts
- participant names and meeting metadata
- workplace, business, academic, or operational discussions
- uploaded documents and generated exports
- voice samples and derived voice representations
- account, access, audit, and usage metadata

Treat voice samples and derived voice representations as restricted, highly identifying personal data.

## 2. Recording notice and consent
Before recording:
- Display a clear recording notice.
- Remind the host to obtain consent appropriate to the meeting context and applicable law.
- Record the host's confirmation and the notice version.
- Make recording state visible throughout capture.
- Provide a way to stop recording.
- Do not represent host confirmation as proof that every participant has consented where separate consent is required.

## 3. Voice cloning consent is separate
Agreement to record a meeting is **not** permission to clone a participant's voice.

Before clone enrolment:
1. Explain what cloning does and the intended processing.
2. Explain where samples are stored, who can use the profile, permitted purposes, retention, and revocation.
3. Obtain explicit affirmative consent from the voice owner or verifiable authority.
4. Apply identity/authority verification proportionate to risk.
5. Capture a fresh challenge/live sample or other suitable anti-replay verification where required by risk assessment.
6. Store consent text version, owner, purpose, jurisdiction, verification method, time, expiry, and permitted uses.
7. Keep the profile private by default.
8. Require approval and permission checks before every synthesis job.

## 4. Prohibited or restricted use
- No anonymous or bulk voice cloning.
- No cloning of another person without verified authorisation.
- No default public gallery of user clones.
- Do not use generated speech for authentication, financial authorisation, emergency instructions, or identity verification.
- Do not misrepresent synthetic audio as an authentic live recording.
- Do not train on customer recordings by default. Any separate opt-in requires legal review and technically enforceable controls.

## 5. Revocation and deletion
The owner must be able to inspect use, revoke grants, disable a profile, and request deletion of samples and derived artefacts. Revocation must block subsequent synthesis immediately after the authoritative permission state is updated. Record exceptions for legal holds and explain backup expiry timelines.

## 6. AI-generated audio disclosure
Label generated audio in the interface and, where feasible, embed provenance metadata or suitable audible/visual disclosure. Record model version, voice profile, job, requester, and output.

## 7. Jurisdiction review
For Nigeria, review the Nigeria Data Protection Act 2023 and applicable NDPC guidance with qualified counsel. For international sales, assess GDPR/UK GDPR, US state privacy and biometric/voice laws, employment rules, and sector-specific requirements. Do not claim certification or compliance solely because technical controls exist.

## 8. Required product records
- Recording notice version and host confirmation
- Participant consent status where the product collects it
- Voice consent record and verification evidence reference
- Voice permission grants, expiry, and revocation
- Data retention policy and legal hold
- Access, export, playback, synthesis, and deletion audit events
- User-facing privacy and deletion explanations
