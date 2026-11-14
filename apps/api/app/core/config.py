from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings for NEXUS Meeting Intelligence."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    nexus_env: str = Field(default="development", alias="NEXUS_ENV")
    nexus_app_name: str = Field(default="NEXUS Meeting Intelligence", alias="NEXUS_APP_NAME")
    nexus_api_prefix: str = Field(default="/api/v1", alias="NEXUS_API_PREFIX")
    nexus_allowed_origins: str = Field(
        default="http://localhost:3000,https://nexus-meeting.vercel.app",
        alias="NEXUS_ALLOWED_ORIGINS",
    )

    # Hard governance gate: Voice cloning MUST remain disabled until Phase 6 gates pass
    voice_cloning_enabled: bool = Field(default=False, alias="VOICE_CLONING_ENABLED")

    # Database
    database_url: str = Field(
        default="sqlite:///./nexus_dev.db",
        alias="DATABASE_URL",
    )
    db_echo: bool = Field(default=False, alias="DB_ECHO")

    # Object storage (S3-compatible: Supabase Storage S3 / Cloudflare R2 / MinIO).
    # When all four are configured, the real S3 adapter is used; otherwise the
    # in-memory adapter serves local tests and CI.
    s3_endpoint_url: str = Field(default="", alias="S3_ENDPOINT_URL")
    s3_access_key_id: str = Field(default="", alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str = Field(default="", alias="S3_SECRET_ACCESS_KEY")
    s3_bucket_media: str = Field(default="", alias="S3_BUCKET_MEDIA")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")

    # Supabase Auth (OIDC/JWT)
    supabase_url: str = Field(
        default="https://example-project.supabase.co",
        alias="SUPABASE_URL",
    )
    supabase_anon_key: str = Field(
        default="supabase-anon-placeholder",
        alias="SUPABASE_ANON_KEY",
    )
    supabase_jwt_secret: str = Field(
        default="nexus-local-dev-supabase-jwt-secret-key-min-32-bytes",
        alias="SUPABASE_JWT_SECRET",
    )
    supabase_jwt_audience: str = Field(
        default="authenticated",
        alias="SUPABASE_JWT_AUDIENCE",
    )
    require_admin_mfa: bool = Field(default=False, alias="REQUIRE_ADMIN_MFA")

    # Transactional Email Providers: Resend, Emailbump, Unipost
    email_primary_provider: str = Field(default="resend", alias="EMAIL_PRIMARY_PROVIDER")
    email_fallback_providers: str = Field(
        default="emailbump,unipost", alias="EMAIL_FALLBACK_PROVIDERS"
    )
    email_from_address: str = Field(
        default="noreply@nexus-meeting.example.com", alias="EMAIL_FROM_ADDRESS"
    )
    email_from_name: str = Field(
        default="NEXUS Meeting Intelligence", alias="EMAIL_FROM_NAME"
    )
    email_dry_run: bool = Field(default=True, alias="EMAIL_DRY_RUN")

    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    resend_api_base_url: str = Field(
        default="https://api.resend.com", alias="RESEND_API_BASE_URL"
    )
    emailbump_api_key: str = Field(default="", alias="EMAILBUMP_API_KEY")
    emailbump_api_base_url: str = Field(
        default="https://api.emailbump.com/v1", alias="EMAILBUMP_API_BASE_URL"
    )
    unipost_api_key: str = Field(default="", alias="UNIPOST_API_KEY")
    unipost_api_base_url: str = Field(
        default="https://api.unipost.co/v1", alias="UNIPOST_API_BASE_URL"
    )

    # Storage & Upload Defaults
    s3_presigned_url_ttl_seconds: int = Field(
        default=300, alias="S3_PRESIGNED_URL_TTL_SECONDS"
    )
    upload_chunk_size_bytes: int = Field(
        default=5 * 1024 * 1024, alias="UPLOAD_CHUNK_SIZE_BYTES"
    )
    upload_max_file_size_bytes: int = Field(
        default=2 * 1024 * 1024 * 1024, alias="UPLOAD_MAX_FILE_SIZE_BYTES"
    )

    @field_validator("voice_cloning_enabled")
    @classmethod
    def enforce_voice_cloning_disabled_in_phase1(cls, value: bool) -> bool:
        if value is True:
            raise ValueError(
                "VOICE_CLONING_ENABLED cannot be enabled before Phase 6 consent, "
                "identity verification, licensing, and security gates are approved."
            )
        return False

    @field_validator("database_url")
    @classmethod
    def normalize_database_url_scheme(cls, value: str) -> str:
        """Accepts standard PostgreSQL URLs (e.g. from Supabase) and maps them to the psycopg driver."""
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.nexus_allowed_origins.split(",") if o.strip()]

    @property
    def ordered_email_providers(self) -> list[str]:
        primary = self.email_primary_provider.strip().lower()
        fallbacks = [
            p.strip().lower()
            for p in self.email_fallback_providers.split(",")
            if p.strip()
        ]
        chain: list[str] = []
        for provider in [primary, *fallbacks]:
            if provider and provider not in chain:
                chain.append(provider)
        return chain


@lru_cache
def get_settings() -> Settings:
    return Settings()
