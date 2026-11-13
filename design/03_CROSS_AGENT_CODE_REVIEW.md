# Cross-Agent Code Review

## Review objective
The review agent independently evaluates correctness, maintainability, security, privacy, accessibility, and fit with the approved NEXUS specifications. It should identify issues, not merely approve or rewrite code stylistically.

## Review order
1. Requirements and acceptance criteria.
2. Data model, tenant isolation, authorization and RLS.
3. Privacy, recording consent, retention, export and deletion behavior.
4. API contracts, validation, error handling and rate limits.
5. Reliability, retries, idempotency and background processing.
6. UI states, accessibility, responsiveness and usability.
7. Tests, observability, performance and operational readiness.

## Finding severity
- **Blocker:** data exposure, cross-tenant access, credential leakage, consent bypass, destructive data loss, or release-stopping failure.
- **High:** major incorrect behavior, authorization flaw, privacy defect, or severe reliability issue.
- **Medium:** material edge-case defect, incomplete validation, accessibility barrier, or missing important tests.
- **Low:** minor usability, maintainability, or cosmetic issue.

## Required review output
```md
# Review: <task/PR>
## Verdict: Approve / Request changes / Needs evidence
## Findings
- [Severity] File/area — problem, impact, reproduction/evidence, recommended correction.
## Requirements not demonstrated
## Security and privacy assessment
## Test evidence reviewed
## Residual risks
```

## Independence rule
The reviewer must inspect the actual diff and evidence. Do not claim a test passed unless it was run and its output inspected. If the reviewer cannot run the application, label the review as static-only and list what remains unverified.
