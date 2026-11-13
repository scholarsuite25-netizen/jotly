# 11 — Deployment and Operations

## 1. Environments
### Development
- Docker Compose
- Synthetic/test data
- Local model weights
- No production secrets or real customer recordings

### Staging
- Production-like topology
- Anonymised or explicitly authorised test data
- Upgrade, load, restore, and integration tests

### Production
- Hardened secrets
- Private object storage
- Monitored workers and model services
- Backup schedule and tested restore
- Incident response and rollback procedures

## 2. Health checks
Provide health/readiness checks for:
- API
- PostgreSQL
- Redis
- object storage
- each model worker and inference service
- job queue consumers

## 3. Operational metrics
- Queue depth and wait time
- Processing latency and real-time factor
- Job success/failure/retry rate
- CPU, RAM, GPU and disk use
- Storage growth and lifecycle backlog
- Per-tenant usage and quota
- ASR/TTS model version and performance
- API latency and error rate

## 4. Logging and tracing
- Structured logs with correlation IDs.
- Do not log transcript content, raw voice samples, secrets, access tokens, or unnecessary personal data.
- Record model/job metadata without exposing sensitive content.
- Restrict access to audit and operational logs.

## 5. Backup and disaster recovery
- Back up PostgreSQL and object storage.
- Encrypt backups.
- Define RPO and RTO per service tier.
- Periodically restore into an isolated environment.
- Document retention and expiry of backup copies.
- Include application, schema, configuration, and model rollback plans.

## 6. Runbooks
Create and test runbooks for:
- stuck jobs
- corrupt uploads
- failed exports
- model worker outage
- queue backlog
- database failover
- storage outage
- suspected voice abuse
- security incident
- data deletion request
- restore and rollback

## 7. On-premises release
Provide supported hardware matrix, installation guide, network/security requirements, offline model distribution procedure, backup/restore, upgrade, and support policy.
