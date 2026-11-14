BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_phase1_foundation

CREATE TABLE organisations (
    id VARCHAR(36) NOT NULL, 
    slug VARCHAR(120) NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    status VARCHAR(32) DEFAULT 'active' NOT NULL, 
    retention_days INTEGER DEFAULT '365' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (slug)
);

CREATE TABLE users (
    id VARCHAR(36) NOT NULL, 
    supabase_sub VARCHAR(128) NOT NULL, 
    email VARCHAR(320) NOT NULL, 
    full_name VARCHAR(255) NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    mfa_verified BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (supabase_sub), 
    UNIQUE (email)
);

CREATE TABLE permissions (
    id VARCHAR(36) NOT NULL, 
    code VARCHAR(100) NOT NULL, 
    description VARCHAR(255) NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (code)
);

CREATE TABLE workspaces (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    description VARCHAR(500), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT
);

CREATE INDEX ix_workspaces_org_id ON workspaces (organisation_id, id);

CREATE TABLE departments (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT
);

CREATE INDEX ix_departments_org_id ON departments (organisation_id, id);

CREATE TABLE roles (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    code VARCHAR(80) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    is_system BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_roles_org_code ON roles (organisation_id, code);

CREATE TABLE role_permissions (
    id VARCHAR(36) NOT NULL, 
    role_id VARCHAR(36) NOT NULL, 
    permission_id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
    FOREIGN KEY(permission_id) REFERENCES permissions (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_role_permissions_unique ON role_permissions (role_id, permission_id);

CREATE TABLE user_roles (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    role_id VARCHAR(36) NOT NULL, 
    status VARCHAR(32) DEFAULT 'active' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE RESTRICT
);

CREATE INDEX ix_user_roles_org_user ON user_roles (organisation_id, user_id);

CREATE TABLE invitations (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    email VARCHAR(320) NOT NULL, 
    role_code VARCHAR(80) NOT NULL, 
    invited_by_user_id VARCHAR(36) NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
    email_provider VARCHAR(32), 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(invited_by_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    UNIQUE (token_hash)
);

CREATE INDEX ix_invitations_org_email ON invitations (organisation_id, email);

CREATE TABLE sessions (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    token_jti VARCHAR(128) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_sessions_org_user ON sessions (organisation_id, user_id);

CREATE TABLE audit_logs (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    actor_user_id VARCHAR(36), 
    action VARCHAR(120) NOT NULL, 
    resource_type VARCHAR(80) NOT NULL, 
    resource_id VARCHAR(64) NOT NULL, 
    result VARCHAR(32) NOT NULL, 
    correlation_id VARCHAR(64) NOT NULL, 
    metadata_json TEXT DEFAULT '{}' NOT NULL, 
    previous_hash VARCHAR(64) NOT NULL, 
    entry_hash VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_audit_logs_org_created ON audit_logs (organisation_id, created_at);

CREATE TABLE background_jobs (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    job_type VARCHAR(80) NOT NULL, 
    source_entity_type VARCHAR(80) NOT NULL, 
    source_entity_id VARCHAR(64) NOT NULL, 
    status VARCHAR(32) DEFAULT 'queued' NOT NULL, 
    progress INTEGER DEFAULT '0' NOT NULL, 
    retry_count INTEGER DEFAULT '0' NOT NULL, 
    max_retries INTEGER DEFAULT '3' NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    worker_version VARCHAR(64) DEFAULT '0.1.0' NOT NULL, 
    error_code VARCHAR(64), 
    error_message VARCHAR(255), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_background_jobs_org_idempotency ON background_jobs (organisation_id, idempotency_key);

ALTER TABLE organisations ENABLE ROW LEVEL SECURITY;;

ALTER TABLE organisations FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_organisations ON organisations USING (id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;;

ALTER TABLE workspaces FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_workspaces ON workspaces USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE departments ENABLE ROW LEVEL SECURITY;;

ALTER TABLE departments FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_departments ON departments USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE roles ENABLE ROW LEVEL SECURITY;;

ALTER TABLE roles FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_roles ON roles USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;;

ALTER TABLE user_roles FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_user_roles ON user_roles USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;;

ALTER TABLE invitations FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_invitations ON invitations USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;;

ALTER TABLE sessions FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_sessions ON sessions USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;;

ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_audit_logs ON audit_logs USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE background_jobs ENABLE ROW LEVEL SECURITY;;

ALTER TABLE background_jobs FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_background_jobs ON background_jobs USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

INSERT INTO alembic_version (version_num) VALUES ('0001_phase1_foundation') RETURNING alembic_version.version_num;

-- Running upgrade 0001_phase1_foundation -> 0002_phase2_recording_media

CREATE TABLE meetings (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    department_id VARCHAR(36), 
    host_user_id VARCHAR(36) NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    agenda TEXT, 
    scheduled_start_at TIMESTAMP WITH TIME ZONE, 
    scheduled_end_at TIMESTAMP WITH TIME ZONE, 
    visibility VARCHAR(32) DEFAULT 'workspace' NOT NULL, 
    recording_state VARCHAR(32) DEFAULT 'idle' NOT NULL, 
    notice_version VARCHAR(32), 
    notice_confirmed_at TIMESTAMP WITH TIME ZONE, 
    notice_confirmed_by_user_id VARCHAR(36), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT, 
    FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE RESTRICT, 
    FOREIGN KEY(host_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    FOREIGN KEY(notice_confirmed_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_meetings_org_workspace ON meetings (organisation_id, workspace_id);

CREATE TABLE meeting_participants (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    meeting_id VARCHAR(36) NOT NULL, 
    email VARCHAR(320) NOT NULL, 
    display_name VARCHAR(255) NOT NULL, 
    role VARCHAR(32) DEFAULT 'attendee' NOT NULL, 
    consent_status VARCHAR(32) DEFAULT 'notified' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(meeting_id) REFERENCES meetings (id) ON DELETE CASCADE
);

CREATE INDEX ix_meeting_participants_org_meeting ON meeting_participants (organisation_id, meeting_id);

CREATE TABLE media_upload_sessions (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    meeting_id VARCHAR(36) NOT NULL, 
    initiated_by_user_id VARCHAR(36) NOT NULL, 
    file_name VARCHAR(255) NOT NULL, 
    mime_type VARCHAR(100) NOT NULL, 
    declared_size_bytes INTEGER NOT NULL, 
    chunk_size_bytes INTEGER NOT NULL, 
    total_chunks INTEGER NOT NULL, 
    expected_sha256 VARCHAR(64) NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    status VARCHAR(32) DEFAULT 'initiated' NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(meeting_id) REFERENCES meetings (id) ON DELETE RESTRICT, 
    FOREIGN KEY(initiated_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_media_upload_sessions_org_idem ON media_upload_sessions (organisation_id, idempotency_key);

CREATE TABLE media_chunks (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    upload_session_id VARCHAR(36) NOT NULL, 
    chunk_index INTEGER NOT NULL, 
    size_bytes INTEGER NOT NULL, 
    sha256_checksum VARCHAR(64) NOT NULL, 
    object_key VARCHAR(512) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(upload_session_id) REFERENCES media_upload_sessions (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_media_chunks_session_idx ON media_chunks (organisation_id, upload_session_id, chunk_index);

CREATE TABLE media_assets (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    meeting_id VARCHAR(36) NOT NULL, 
    upload_session_id VARCHAR(36) NOT NULL, 
    uploaded_by_user_id VARCHAR(36) NOT NULL, 
    object_key VARCHAR(512) NOT NULL, 
    file_name VARCHAR(255) NOT NULL, 
    mime_type VARCHAR(100) NOT NULL, 
    size_bytes INTEGER NOT NULL, 
    sha256_checksum VARCHAR(64) NOT NULL, 
    codec VARCHAR(64), 
    duration_ms INTEGER, 
    sample_rate_hz INTEGER, 
    channels INTEGER, 
    encryption_alg VARCHAR(32) DEFAULT 'AES-256-GCM' NOT NULL, 
    retention_until TIMESTAMP WITH TIME ZONE NOT NULL, 
    status VARCHAR(32) DEFAULT 'uploaded' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(meeting_id) REFERENCES meetings (id) ON DELETE RESTRICT, 
    UNIQUE (upload_session_id), 
    FOREIGN KEY(upload_session_id) REFERENCES media_upload_sessions (id) ON DELETE RESTRICT, 
    FOREIGN KEY(uploaded_by_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    UNIQUE (object_key)
);

CREATE INDEX ix_media_assets_org_meeting ON media_assets (organisation_id, meeting_id);

CREATE TABLE media_derivatives (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    media_asset_id VARCHAR(36) NOT NULL, 
    meeting_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(64) NOT NULL, 
    object_key VARCHAR(512) NOT NULL, 
    mime_type VARCHAR(100) NOT NULL, 
    size_bytes INTEGER NOT NULL, 
    sha256_checksum VARCHAR(64) NOT NULL, 
    processing_version VARCHAR(32) DEFAULT 'ffmpeg-norm-1.0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(media_asset_id) REFERENCES media_assets (id) ON DELETE RESTRICT, 
    FOREIGN KEY(meeting_id) REFERENCES meetings (id) ON DELETE RESTRICT, 
    UNIQUE (object_key)
);

CREATE INDEX ix_media_derivatives_org_asset ON media_derivatives (organisation_id, media_asset_id);

CREATE TABLE media_processing_jobs (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    media_asset_id VARCHAR(36) NOT NULL, 
    background_job_id VARCHAR(36) NOT NULL, 
    stage VARCHAR(64) DEFAULT 'validate_and_normalise' NOT NULL, 
    status VARCHAR(32) DEFAULT 'queued' NOT NULL, 
    details_json TEXT DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(media_asset_id) REFERENCES media_assets (id) ON DELETE RESTRICT, 
    FOREIGN KEY(background_job_id) REFERENCES background_jobs (id) ON DELETE RESTRICT
);

CREATE INDEX ix_media_proc_jobs_org_asset ON media_processing_jobs (organisation_id, media_asset_id);

ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;;

ALTER TABLE meetings FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_meetings ON meetings USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE meeting_participants ENABLE ROW LEVEL SECURITY;;

ALTER TABLE meeting_participants FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_meeting_participants ON meeting_participants USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE media_upload_sessions ENABLE ROW LEVEL SECURITY;;

ALTER TABLE media_upload_sessions FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_media_upload_sessions ON media_upload_sessions USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE media_chunks ENABLE ROW LEVEL SECURITY;;

ALTER TABLE media_chunks FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_media_chunks ON media_chunks USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE media_assets ENABLE ROW LEVEL SECURITY;;

ALTER TABLE media_assets FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_media_assets ON media_assets USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE media_derivatives ENABLE ROW LEVEL SECURITY;;

ALTER TABLE media_derivatives FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_media_derivatives ON media_derivatives USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE media_processing_jobs ENABLE ROW LEVEL SECURITY;;

ALTER TABLE media_processing_jobs FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_media_processing_jobs ON media_processing_jobs USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

UPDATE alembic_version SET version_num='0002_phase2_recording_media' WHERE alembic_version.version_num = '0001_phase1_foundation';

-- Running upgrade 0002_phase2_recording_media -> 0003_phase3_transcription

CREATE TABLE transcripts (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    meeting_id VARCHAR(36) NOT NULL, 
    media_asset_id VARCHAR(36) NOT NULL, 
    background_job_id VARCHAR(36) NOT NULL, 
    language_code VARCHAR(16) DEFAULT 'en' NOT NULL, 
    detected_language VARCHAR(16) DEFAULT 'en' NOT NULL, 
    language_confidence FLOAT DEFAULT '0.95' NOT NULL, 
    asr_model_id VARCHAR(120) DEFAULT 'faster-whisper-large-v3' NOT NULL, 
    asr_model_version VARCHAR(64) DEFAULT '1.0.3' NOT NULL, 
    diarisation_enabled BOOLEAN DEFAULT false NOT NULL, 
    diarisation_model_id VARCHAR(120), 
    config_json TEXT DEFAULT '{}' NOT NULL, 
    status VARCHAR(32) DEFAULT 'completed' NOT NULL, 
    current_revision_number INTEGER DEFAULT '1' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(meeting_id) REFERENCES meetings (id) ON DELETE RESTRICT, 
    FOREIGN KEY(media_asset_id) REFERENCES media_assets (id) ON DELETE RESTRICT, 
    FOREIGN KEY(background_job_id) REFERENCES background_jobs (id) ON DELETE RESTRICT
);

CREATE INDEX ix_transcripts_org_meeting ON transcripts (organisation_id, meeting_id);

CREATE INDEX ix_transcripts_org_media ON transcripts (organisation_id, media_asset_id);

CREATE TABLE transcript_speakers (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    transcript_id VARCHAR(36) NOT NULL, 
    speaker_key VARCHAR(64) NOT NULL, 
    display_name VARCHAR(120) NOT NULL, 
    is_model_suggestion BOOLEAN DEFAULT true NOT NULL, 
    identity_verified BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(transcript_id) REFERENCES transcripts (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_transcript_speakers_org_tx_key ON transcript_speakers (organisation_id, transcript_id, speaker_key);

CREATE TABLE speaker_labels (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    transcript_id VARCHAR(36) NOT NULL, 
    speaker_id VARCHAR(36) NOT NULL, 
    previous_display_name VARCHAR(120), 
    new_display_name VARCHAR(120) NOT NULL, 
    changed_by_user_id VARCHAR(36), 
    source VARCHAR(32) DEFAULT 'model_suggestion' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(transcript_id) REFERENCES transcripts (id) ON DELETE CASCADE, 
    FOREIGN KEY(speaker_id) REFERENCES transcript_speakers (id) ON DELETE CASCADE, 
    FOREIGN KEY(changed_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_speaker_labels_org_tx ON speaker_labels (organisation_id, transcript_id);

CREATE TABLE transcript_segments (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    transcript_id VARCHAR(36) NOT NULL, 
    sequence_number INTEGER NOT NULL, 
    start_ms INTEGER NOT NULL, 
    end_ms INTEGER NOT NULL, 
    original_asr_text TEXT NOT NULL, 
    current_text TEXT NOT NULL, 
    confidence FLOAT DEFAULT '0.9' NOT NULL, 
    speaker_id VARCHAR(36), 
    speaker_is_model_suggestion BOOLEAN DEFAULT true NOT NULL, 
    is_edited BOOLEAN DEFAULT false NOT NULL, 
    updated_by_user_id VARCHAR(36), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(transcript_id) REFERENCES transcripts (id) ON DELETE CASCADE, 
    FOREIGN KEY(speaker_id) REFERENCES transcript_speakers (id) ON DELETE SET NULL, 
    FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_transcript_segments_org_tx_seq ON transcript_segments (organisation_id, transcript_id, sequence_number);

CREATE TABLE transcript_revisions (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    transcript_id VARCHAR(36) NOT NULL, 
    segment_id VARCHAR(36), 
    revision_number INTEGER NOT NULL, 
    change_type VARCHAR(32) NOT NULL, 
    previous_text TEXT, 
    new_text TEXT, 
    previous_speaker_id VARCHAR(36), 
    new_speaker_id VARCHAR(36), 
    editor_user_id VARCHAR(36), 
    summary VARCHAR(255) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(transcript_id) REFERENCES transcripts (id) ON DELETE CASCADE, 
    FOREIGN KEY(segment_id) REFERENCES transcript_segments (id) ON DELETE SET NULL, 
    FOREIGN KEY(editor_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_transcript_revisions_org_tx_rev ON transcript_revisions (organisation_id, transcript_id, revision_number);

CREATE TABLE transcript_exports (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    transcript_id VARCHAR(36) NOT NULL, 
    format VARCHAR(16) NOT NULL, 
    revision_number INTEGER NOT NULL, 
    created_by_user_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(transcript_id) REFERENCES transcripts (id) ON DELETE RESTRICT, 
    FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_transcript_exports_org_tx ON transcript_exports (organisation_id, transcript_id);

ALTER TABLE transcripts ENABLE ROW LEVEL SECURITY;;

ALTER TABLE transcripts FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_transcripts ON transcripts USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE transcript_speakers ENABLE ROW LEVEL SECURITY;;

ALTER TABLE transcript_speakers FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_transcript_speakers ON transcript_speakers USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE speaker_labels ENABLE ROW LEVEL SECURITY;;

ALTER TABLE speaker_labels FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_speaker_labels ON speaker_labels USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE transcript_segments ENABLE ROW LEVEL SECURITY;;

ALTER TABLE transcript_segments FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_transcript_segments ON transcript_segments USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE transcript_revisions ENABLE ROW LEVEL SECURITY;;

ALTER TABLE transcript_revisions FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_transcript_revisions ON transcript_revisions USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE transcript_exports ENABLE ROW LEVEL SECURITY;;

ALTER TABLE transcript_exports FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_transcript_exports ON transcript_exports USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

UPDATE alembic_version SET version_num='0003_phase3_transcription' WHERE alembic_version.version_num = '0002_phase2_recording_media';

-- Running upgrade 0003_phase3_transcription -> 0004_phase4_document_studio

CREATE TABLE documents (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    document_type VARCHAR(32) NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    uploaded_by_user_id VARCHAR(36) NOT NULL, 
    source_media_asset_id VARCHAR(36), 
    source_transcript_id VARCHAR(36), 
    status VARCHAR(32) DEFAULT 'draft' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(uploaded_by_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    FOREIGN KEY(source_media_asset_id) REFERENCES media_assets (id) ON DELETE RESTRICT, 
    FOREIGN KEY(source_transcript_id) REFERENCES transcripts (id) ON DELETE RESTRICT
);

CREATE INDEX ix_documents_org_type ON documents (organisation_id, document_type);

CREATE TABLE document_versions (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    document_id VARCHAR(36) NOT NULL, 
    version_number INTEGER NOT NULL, 
    source_object_key VARCHAR(512), 
    source_file_name VARCHAR(255), 
    source_mime_type VARCHAR(100), 
    source_size_bytes INTEGER, 
    source_sha256_checksum VARCHAR(64), 
    extracted_text TEXT, 
    ocr_applied BOOLEAN DEFAULT false NOT NULL, 
    ocr_pages_detected INTEGER DEFAULT '0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_document_versions_org_doc ON document_versions (organisation_id, document_id, version_number);

CREATE TABLE document_templates (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    template_name VARCHAR(120) NOT NULL, 
    template_type VARCHAR(32) DEFAULT 'transcript' NOT NULL, 
    organisation_logo TEXT, 
    brand_primary_color VARCHAR(16) DEFAULT '#1F3A5F' NOT NULL, 
    brand_secondary_color VARCHAR(16) DEFAULT '#5A7C9F' NOT NULL, 
    header_text VARCHAR(255), 
    footer_text VARCHAR(255), 
    include_page_numbers BOOLEAN DEFAULT true NOT NULL, 
    confidentiality_label VARCHAR(64) DEFAULT 'Confidential' NOT NULL, 
    created_by_user_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_document_templates_org_name ON document_templates (organisation_id, template_name);

CREATE TABLE document_exports (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    document_id VARCHAR(36) NOT NULL, 
    document_version_id VARCHAR(36) NOT NULL, 
    template_id VARCHAR(36), 
    export_format VARCHAR(16) NOT NULL, 
    object_key VARCHAR(512) NOT NULL, 
    size_bytes INTEGER NOT NULL, 
    sha256_checksum VARCHAR(64) NOT NULL, 
    created_by_user_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    FOREIGN KEY(document_version_id) REFERENCES document_versions (id) ON DELETE RESTRICT, 
    FOREIGN KEY(template_id) REFERENCES document_templates (id) ON DELETE RESTRICT, 
    UNIQUE (object_key), 
    FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_document_exports_org_doc ON document_exports (organisation_id, document_id);

CREATE TABLE document_shares (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    document_id VARCHAR(36) NOT NULL, 
    shared_with_user_id VARCHAR(36) NOT NULL, 
    permission VARCHAR(32) DEFAULT 'view' NOT NULL, 
    granted_by_user_id VARCHAR(36) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    FOREIGN KEY(shared_with_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    FOREIGN KEY(granted_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_document_shares_org_doc ON document_shares (organisation_id, document_id);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;;

ALTER TABLE documents FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_documents ON documents USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE document_versions ENABLE ROW LEVEL SECURITY;;

ALTER TABLE document_versions FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_document_versions ON document_versions USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE document_templates ENABLE ROW LEVEL SECURITY;;

ALTER TABLE document_templates FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_document_templates ON document_templates USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE document_exports ENABLE ROW LEVEL SECURITY;;

ALTER TABLE document_exports FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_document_exports ON document_exports USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE document_shares ENABLE ROW LEVEL SECURITY;;

ALTER TABLE document_shares FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_document_shares ON document_shares USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

UPDATE alembic_version SET version_num='0004_phase4_document_studio' WHERE alembic_version.version_num = '0003_phase3_transcription';

-- Running upgrade 0004_phase4_document_studio -> 0005_phase5_voice_studio

CREATE TABLE speech_projects (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    source_document_id VARCHAR(36), 
    source_document_version_id VARCHAR(36), 
    title VARCHAR(255) NOT NULL, 
    language_code VARCHAR(16) DEFAULT 'en' NOT NULL, 
    voice_id VARCHAR(64) NOT NULL, 
    speed_percent INTEGER DEFAULT '100' NOT NULL, 
    output_format VARCHAR(16) DEFAULT 'wav' NOT NULL, 
    text_content TEXT NOT NULL, 
    reviewed_by_user_id VARCHAR(36) NOT NULL, 
    status VARCHAR(32) DEFAULT 'queued' NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    tts_model_id VARCHAR(120) DEFAULT 'stub-kokoro' NOT NULL, 
    tts_model_version VARCHAR(64) DEFAULT '1.0.0' NOT NULL, 
    chunk_count INTEGER DEFAULT '0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(source_document_id) REFERENCES documents (id) ON DELETE RESTRICT, 
    FOREIGN KEY(source_document_version_id) REFERENCES document_versions (id) ON DELETE RESTRICT, 
    FOREIGN KEY(reviewed_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_speech_projects_org_idem ON speech_projects (organisation_id, idempotency_key);

CREATE TABLE speech_chunks (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    speech_project_id VARCHAR(36) NOT NULL, 
    chunk_index INTEGER NOT NULL, 
    chunk_text TEXT NOT NULL, 
    pronunciation_overrides_json TEXT DEFAULT '{}' NOT NULL, 
    object_key VARCHAR(512) NOT NULL, 
    duration_ms INTEGER DEFAULT '0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(speech_project_id) REFERENCES speech_projects (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_speech_chunks_org_project_idx ON speech_chunks (organisation_id, speech_project_id, chunk_index);

CREATE TABLE audio_assets (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    speech_project_id VARCHAR(36) NOT NULL, 
    object_key VARCHAR(512) NOT NULL, 
    output_format VARCHAR(16) NOT NULL, 
    size_bytes INTEGER NOT NULL, 
    sha256_checksum VARCHAR(64) NOT NULL, 
    duration_ms INTEGER DEFAULT '0' NOT NULL, 
    loudness_normalised BOOLEAN DEFAULT true NOT NULL, 
    synthetic_disclosure VARCHAR(255) DEFAULT 'AI-generated speech' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(speech_project_id) REFERENCES speech_projects (id) ON DELETE RESTRICT, 
    UNIQUE (object_key)
);

CREATE INDEX ix_audio_assets_org_project ON audio_assets (organisation_id, speech_project_id);

CREATE TABLE audio_chapters (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    audio_asset_id VARCHAR(36) NOT NULL, 
    chapter_index INTEGER NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    start_ms INTEGER NOT NULL, 
    end_ms INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(audio_asset_id) REFERENCES audio_assets (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_audio_chapters_org_asset ON audio_chapters (organisation_id, audio_asset_id, chapter_index);

CREATE TABLE pronunciation_entries (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    word VARCHAR(120) NOT NULL, 
    phonetic_hint VARCHAR(255) NOT NULL, 
    language_code VARCHAR(16) DEFAULT 'en' NOT NULL, 
    created_by_user_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_pronunciation_entries_org_word ON pronunciation_entries (organisation_id, word);

ALTER TABLE speech_projects ENABLE ROW LEVEL SECURITY;;

ALTER TABLE speech_projects FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_speech_projects ON speech_projects USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE speech_chunks ENABLE ROW LEVEL SECURITY;;

ALTER TABLE speech_chunks FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_speech_chunks ON speech_chunks USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE audio_assets ENABLE ROW LEVEL SECURITY;;

ALTER TABLE audio_assets FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_audio_assets ON audio_assets USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE audio_chapters ENABLE ROW LEVEL SECURITY;;

ALTER TABLE audio_chapters FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_audio_chapters ON audio_chapters USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE pronunciation_entries ENABLE ROW LEVEL SECURITY;;

ALTER TABLE pronunciation_entries FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_pronunciation_entries ON pronunciation_entries USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

UPDATE alembic_version SET version_num='0005_phase5_voice_studio' WHERE alembic_version.version_num = '0004_phase4_document_studio';

-- Running upgrade 0005_phase5_voice_studio -> 0006_phase6_voice_governance

CREATE TABLE voice_consents (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    owner_user_id VARCHAR(36) NOT NULL, 
    consent_text_version VARCHAR(32) NOT NULL, 
    permitted_uses TEXT DEFAULT 'internal_synthesis' NOT NULL, 
    jurisdiction VARCHAR(64) DEFAULT 'NG' NOT NULL, 
    verification_method VARCHAR(64) DEFAULT 'challenge_live_sample' NOT NULL, 
    verification_reference VARCHAR(128) NOT NULL, 
    verification_passed BOOLEAN DEFAULT false NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    revocation_at TIMESTAMP WITH TIME ZONE, 
    signed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_voice_consents_org_owner ON voice_consents (organisation_id, owner_user_id);

CREATE TABLE voice_profiles (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    owner_user_id VARCHAR(36) NOT NULL, 
    consent_record_id VARCHAR(36) NOT NULL, 
    display_name VARCHAR(120) NOT NULL, 
    status VARCHAR(32) DEFAULT 'active' NOT NULL, 
    model_id VARCHAR(120) DEFAULT 'stub-openvoice-v2' NOT NULL, 
    model_version VARCHAR(64) DEFAULT '1.0.0' NOT NULL, 
    public_gallery BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    FOREIGN KEY(consent_record_id) REFERENCES voice_consents (id) ON DELETE RESTRICT
);

CREATE INDEX ix_voice_profiles_org_owner ON voice_profiles (organisation_id, owner_user_id);

CREATE TABLE voice_samples (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    voice_profile_id VARCHAR(36) NOT NULL, 
    object_key VARCHAR(512) NOT NULL, 
    duration_ms INTEGER NOT NULL, 
    sha256_checksum VARCHAR(64) NOT NULL, 
    source_type VARCHAR(32) DEFAULT 'challenge_live_sample' NOT NULL, 
    consent_scope VARCHAR(64) DEFAULT 'internal_synthesis' NOT NULL, 
    retention_until TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(voice_profile_id) REFERENCES voice_profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_voice_samples_org_profile ON voice_samples (organisation_id, voice_profile_id);

CREATE TABLE voice_permissions (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    voice_profile_id VARCHAR(36) NOT NULL, 
    grantee_user_id VARCHAR(36) NOT NULL, 
    allowed_use VARCHAR(64) NOT NULL, 
    granted_by_user_id VARCHAR(36) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(voice_profile_id) REFERENCES voice_profiles (id) ON DELETE CASCADE, 
    FOREIGN KEY(grantee_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    FOREIGN KEY(granted_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_voice_permissions_org_profile_grantee ON voice_permissions (organisation_id, voice_profile_id, grantee_user_id);

CREATE TABLE voice_jobs (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    voice_profile_id VARCHAR(36) NOT NULL, 
    background_job_id VARCHAR(36) NOT NULL, 
    requester_user_id VARCHAR(36) NOT NULL, 
    text_sha256 VARCHAR(64) NOT NULL, 
    output_object_key VARCHAR(512), 
    disclosure_flag VARCHAR(255) DEFAULT 'AI-generated voice clone' NOT NULL, 
    status VARCHAR(32) DEFAULT 'queued' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(voice_profile_id) REFERENCES voice_profiles (id) ON DELETE RESTRICT, 
    FOREIGN KEY(background_job_id) REFERENCES background_jobs (id) ON DELETE RESTRICT, 
    FOREIGN KEY(requester_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_voice_jobs_org_profile ON voice_jobs (organisation_id, voice_profile_id);

CREATE TABLE voice_audit_events (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    voice_profile_id VARCHAR(36), 
    voice_job_id VARCHAR(36), 
    actor_user_id VARCHAR(36), 
    action VARCHAR(64) NOT NULL, 
    result VARCHAR(32) NOT NULL, 
    reason VARCHAR(255), 
    permitted_ip_metadata VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(voice_profile_id) REFERENCES voice_profiles (id) ON DELETE RESTRICT, 
    FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_voice_audit_org_profile ON voice_audit_events (organisation_id, voice_profile_id);

ALTER TABLE voice_consents ENABLE ROW LEVEL SECURITY;;

ALTER TABLE voice_consents FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_voice_consents ON voice_consents USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE voice_profiles ENABLE ROW LEVEL SECURITY;;

ALTER TABLE voice_profiles FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_voice_profiles ON voice_profiles USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE voice_samples ENABLE ROW LEVEL SECURITY;;

ALTER TABLE voice_samples FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_voice_samples ON voice_samples USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE voice_permissions ENABLE ROW LEVEL SECURITY;;

ALTER TABLE voice_permissions FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_voice_permissions ON voice_permissions USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE voice_jobs ENABLE ROW LEVEL SECURITY;;

ALTER TABLE voice_jobs FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_voice_jobs ON voice_jobs USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE voice_audit_events ENABLE ROW LEVEL SECURITY;;

ALTER TABLE voice_audit_events FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_voice_audit_events ON voice_audit_events USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

UPDATE alembic_version SET version_num='0006_phase6_voice_governance' WHERE alembic_version.version_num = '0005_phase5_voice_studio';

-- Running upgrade 0006_phase6_voice_governance -> 0007_phase7_meeting_intelligence

CREATE TABLE meeting_summaries (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    meeting_id VARCHAR(36) NOT NULL, 
    transcript_id VARCHAR(36) NOT NULL, 
    background_job_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(32) DEFAULT 'summary' NOT NULL, 
    content_text TEXT NOT NULL, 
    llm_model_id VARCHAR(120) DEFAULT 'stub-llm' NOT NULL, 
    llm_model_version VARCHAR(64) DEFAULT '1.0.0' NOT NULL, 
    prompt_template_version VARCHAR(64) DEFAULT 'summary-v1' NOT NULL, 
    is_ai_interpretation BOOLEAN DEFAULT true NOT NULL, 
    review_status VARCHAR(32) DEFAULT 'pending_review' NOT NULL, 
    reviewed_by_user_id VARCHAR(36), 
    reviewed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(meeting_id) REFERENCES meetings (id) ON DELETE RESTRICT, 
    FOREIGN KEY(transcript_id) REFERENCES transcripts (id) ON DELETE RESTRICT, 
    FOREIGN KEY(background_job_id) REFERENCES background_jobs (id) ON DELETE RESTRICT, 
    FOREIGN KEY(reviewed_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_meeting_summaries_org_meeting ON meeting_summaries (organisation_id, meeting_id);

CREATE TABLE decisions (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    meeting_id VARCHAR(36) NOT NULL, 
    summary_id VARCHAR(36) NOT NULL, 
    decision_text TEXT NOT NULL, 
    is_ai_interpretation BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(meeting_id) REFERENCES meetings (id) ON DELETE RESTRICT, 
    FOREIGN KEY(summary_id) REFERENCES meeting_summaries (id) ON DELETE CASCADE
);

CREATE INDEX ix_decisions_org_meeting ON decisions (organisation_id, meeting_id);

CREATE TABLE action_items (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    meeting_id VARCHAR(36) NOT NULL, 
    summary_id VARCHAR(36) NOT NULL, 
    action_text TEXT NOT NULL, 
    owner_hint VARCHAR(255), 
    due_hint VARCHAR(64), 
    is_ai_interpretation BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(meeting_id) REFERENCES meetings (id) ON DELETE RESTRICT, 
    FOREIGN KEY(summary_id) REFERENCES meeting_summaries (id) ON DELETE CASCADE
);

CREATE INDEX ix_action_items_org_meeting ON action_items (organisation_id, meeting_id);

CREATE TABLE ai_questions (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    meeting_id VARCHAR(36), 
    asked_by_user_id VARCHAR(36) NOT NULL, 
    question_text TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(meeting_id) REFERENCES meetings (id) ON DELETE RESTRICT, 
    FOREIGN KEY(asked_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_ai_questions_org_meeting ON ai_questions (organisation_id, meeting_id);

CREATE TABLE ai_answers (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    question_id VARCHAR(36) NOT NULL, 
    answer_text TEXT NOT NULL, 
    abstained BOOLEAN DEFAULT false NOT NULL, 
    is_ai_interpretation BOOLEAN DEFAULT true NOT NULL, 
    llm_model_id VARCHAR(120) DEFAULT 'stub-llm' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(question_id) REFERENCES ai_questions (id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_answers_org_question ON ai_answers (organisation_id, question_id);

CREATE TABLE evidence_links (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    summary_id VARCHAR(36), 
    answer_id VARCHAR(36), 
    decision_id VARCHAR(36), 
    action_item_id VARCHAR(36), 
    transcript_id VARCHAR(36) NOT NULL, 
    segment_id VARCHAR(36) NOT NULL, 
    start_ms INTEGER NOT NULL, 
    end_ms INTEGER NOT NULL, 
    evidence_kind VARCHAR(32) DEFAULT 'quote' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(summary_id) REFERENCES meeting_summaries (id) ON DELETE CASCADE, 
    FOREIGN KEY(answer_id) REFERENCES ai_answers (id) ON DELETE CASCADE, 
    FOREIGN KEY(decision_id) REFERENCES decisions (id) ON DELETE CASCADE, 
    FOREIGN KEY(action_item_id) REFERENCES action_items (id) ON DELETE CASCADE, 
    FOREIGN KEY(transcript_id) REFERENCES transcripts (id) ON DELETE RESTRICT, 
    FOREIGN KEY(segment_id) REFERENCES transcript_segments (id) ON DELETE RESTRICT
);

CREATE INDEX ix_evidence_links_org_summary ON evidence_links (organisation_id, summary_id);

CREATE TABLE ai_job_logs (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    background_job_id VARCHAR(36) NOT NULL, 
    job_kind VARCHAR(32) NOT NULL, 
    llm_model_id VARCHAR(120) NOT NULL, 
    prompt_template_version VARCHAR(64) NOT NULL, 
    retrieved_segment_count INTEGER DEFAULT '0' NOT NULL, 
    permission_filter_applied BOOLEAN DEFAULT true NOT NULL, 
    injection_attempts_detected INTEGER DEFAULT '0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(background_job_id) REFERENCES background_jobs (id) ON DELETE RESTRICT
);

CREATE INDEX ix_ai_job_logs_org_job ON ai_job_logs (organisation_id, background_job_id);

ALTER TABLE meeting_summaries ENABLE ROW LEVEL SECURITY;;

ALTER TABLE meeting_summaries FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_meeting_summaries ON meeting_summaries USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE decisions ENABLE ROW LEVEL SECURITY;;

ALTER TABLE decisions FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_decisions ON decisions USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE action_items ENABLE ROW LEVEL SECURITY;;

ALTER TABLE action_items FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_action_items ON action_items USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE ai_questions ENABLE ROW LEVEL SECURITY;;

ALTER TABLE ai_questions FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_ai_questions ON ai_questions USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE ai_answers ENABLE ROW LEVEL SECURITY;;

ALTER TABLE ai_answers FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_ai_answers ON ai_answers USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE evidence_links ENABLE ROW LEVEL SECURITY;;

ALTER TABLE evidence_links FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_evidence_links ON evidence_links USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE ai_job_logs ENABLE ROW LEVEL SECURITY;;

ALTER TABLE ai_job_logs FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_ai_job_logs ON ai_job_logs USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

UPDATE alembic_version SET version_num='0007_phase7_meeting_intelligence' WHERE alembic_version.version_num = '0006_phase6_voice_governance';

-- Running upgrade 0007_phase7_meeting_intelligence -> 0008_phase8_collaboration

CREATE TABLE meeting_comments (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    meeting_id VARCHAR(36) NOT NULL, 
    author_user_id VARCHAR(36) NOT NULL, 
    comment_text TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(meeting_id) REFERENCES meetings (id) ON DELETE CASCADE, 
    FOREIGN KEY(author_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_meeting_comments_org_meeting ON meeting_comments (organisation_id, meeting_id);

CREATE TABLE share_grants (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    resource_type VARCHAR(64) NOT NULL, 
    resource_id VARCHAR(64) NOT NULL, 
    grantee_user_id VARCHAR(36) NOT NULL, 
    grantee_organisation_id VARCHAR(36), 
    permission VARCHAR(32) DEFAULT 'view' NOT NULL, 
    granted_by_user_id VARCHAR(36) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(grantee_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    FOREIGN KEY(grantee_organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(granted_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_share_grants_org_resource ON share_grants (organisation_id, resource_type, resource_id);

CREATE TABLE notifications (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    recipient_user_id VARCHAR(36) NOT NULL, 
    notification_type VARCHAR(64) NOT NULL, 
    resource_type VARCHAR(64) NOT NULL, 
    resource_id VARCHAR(64) NOT NULL, 
    preview_text VARCHAR(255) DEFAULT '' NOT NULL, 
    read_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(recipient_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_notifications_org_user ON notifications (organisation_id, recipient_user_id);

CREATE TABLE approval_workflows (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    resource_type VARCHAR(64) NOT NULL, 
    resource_id VARCHAR(64) NOT NULL, 
    requested_by_user_id VARCHAR(36) NOT NULL, 
    status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
    decided_by_user_id VARCHAR(36), 
    decision_note VARCHAR(500), 
    decided_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(requested_by_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    FOREIGN KEY(decided_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_approval_workflows_org_resource ON approval_workflows (organisation_id, resource_type, resource_id);

CREATE TABLE action_assignments (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    action_item_id VARCHAR(36) NOT NULL, 
    assigned_to_user_id VARCHAR(36) NOT NULL, 
    assigned_by_user_id VARCHAR(36) NOT NULL, 
    status VARCHAR(32) DEFAULT 'open' NOT NULL, 
    due_date TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(action_item_id) REFERENCES action_items (id) ON DELETE CASCADE, 
    FOREIGN KEY(assigned_to_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    FOREIGN KEY(assigned_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_action_assignments_org_action ON action_assignments (organisation_id, action_item_id);

CREATE TABLE integration_events (
    id VARCHAR(36) NOT NULL, 
    organisation_id VARCHAR(36) NOT NULL, 
    provider VARCHAR(64) NOT NULL, 
    event_type VARCHAR(64) NOT NULL, 
    signature_verified BOOLEAN DEFAULT false NOT NULL, 
    payload_sha256 VARCHAR(64) NOT NULL, 
    processed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organisation_id) REFERENCES organisations (id) ON DELETE RESTRICT
);

CREATE INDEX ix_integration_events_org_provider ON integration_events (organisation_id, provider);

ALTER TABLE meeting_comments ENABLE ROW LEVEL SECURITY;;

ALTER TABLE meeting_comments FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_meeting_comments ON meeting_comments USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE share_grants ENABLE ROW LEVEL SECURITY;;

ALTER TABLE share_grants FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_share_grants ON share_grants USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;;

ALTER TABLE notifications FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_notifications ON notifications USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE approval_workflows ENABLE ROW LEVEL SECURITY;;

ALTER TABLE approval_workflows FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_approval_workflows ON approval_workflows USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE action_assignments ENABLE ROW LEVEL SECURITY;;

ALTER TABLE action_assignments FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_action_assignments ON action_assignments USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

ALTER TABLE integration_events ENABLE ROW LEVEL SECURITY;;

ALTER TABLE integration_events FORCE ROW LEVEL SECURITY;;

CREATE POLICY tenant_isolation_integration_events ON integration_events USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));;

UPDATE alembic_version SET version_num='0008_phase8_collaboration' WHERE alembic_version.version_num = '0007_phase7_meeting_intelligence';

COMMIT;

