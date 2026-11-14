from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import uuid

import jwt
from jwt import InvalidTokenError, PyJWKClient

from app.core.config import Settings, get_settings
from app.core.errors import NexusAPIError


@dataclass(frozen=True)
class VerifiedSupabaseClaims:
    """Server-verified identity claims extracted from a Supabase Auth JWT."""

    sub: str
    email: str
    full_name: str
    aal: str
    jti: str
    exp: int

    @property
    def is_mfa_verified(self) -> bool:
        return self.aal == "aal2"


_JWKS_CLIENT_CACHE: dict[str, PyJWKClient] = {}


def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    client = _JWKS_CLIENT_CACHE.get(jwks_url)
    if client is None:
        # Cache JWKS keys to avoid fetching on every request (important for serverless warm instances).
        client = PyJWKClient(jwks_url, cache_keys=True)
        _JWKS_CLIENT_CACHE[jwks_url] = client
    return client


def verify_supabase_jwt(
    token: str,
    settings: Optional[Settings] = None,
) -> VerifiedSupabaseClaims:
    """
    Verifies a Supabase Auth JWT token server-side.
    Supports Supabase's current asymmetric JWT signing keys (e.g. ES256 via JWKS)
    and falls back to legacy HS256 verification with the project's JWT secret.
    Validates signature, expiration, audience, and required subject/email claims.
    Never trusts unverified token payloads.
    """
    cfg = settings or get_settings()
    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError as exc:
        raise NexusAPIError(
            status_code=401,
            code="invalid_or_expired_token",
            message="Authentication token is invalid or expired.",
        ) from exc

    alg = str(header.get("alg") or "")
    payload: dict[str, Any] | None = None
    decode_errors: list[Exception] = []

    # Prefer JWKS verification for asymmetric algorithms (Supabase's newer default).
    if alg and alg != "HS256":
        jwks_url = f"{cfg.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        try:
            signing_key = _get_jwks_client(jwks_url).get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience=cfg.supabase_jwt_audience,
                options={"require": ["sub", "exp", "aud"]},
            )
        except Exception as exc:  # noqa: BLE001 - any JWKS/verification issue falls through to legacy attempt
            decode_errors.append(exc)

    # Legacy HS256 projects (or environments/tests using a shared JWT secret).
    if payload is None:
        try:
            payload = jwt.decode(
                token,
                cfg.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=cfg.supabase_jwt_audience,
                options={"require": ["sub", "exp", "aud"]},
            )
        except InvalidTokenError as exc:
            decode_errors.append(exc)

    if payload is None:
        raise NexusAPIError(
            status_code=401,
            code="invalid_or_expired_token",
            message="Authentication token is invalid or expired.",
        ) from (decode_errors[-1] if decode_errors else None)

    sub = str(payload.get("sub", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    if not sub or not email:
        raise NexusAPIError(
            status_code=401,
            code="missing_identity_claims",
            message="Token is missing required identity claims (sub, email).",
        )

    user_meta = payload.get("user_metadata") or {}
    full_name = str(user_meta.get("full_name") or email.split("@")[0]).strip()
    aal = str(payload.get("aal") or "aal1").strip()
    jti = str(payload.get("jti") or payload.get("session_id") or uuid.uuid4())
    exp = int(payload["exp"])

    return VerifiedSupabaseClaims(
        sub=sub,
        email=email,
        full_name=full_name,
        aal=aal,
        jti=jti,
        exp=exp,
    )


def create_supabase_test_jwt(
    *,
    sub: str,
    email: str,
    full_name: str = "Test User",
    aal: str = "aal1",
    expires_delta: timedelta = timedelta(hours=1),
    secret: Optional[str] = None,
    audience: Optional[str] = None,
) -> str:
    """Helper for generating signed Supabase-compatible JWTs in automated tests."""
    cfg = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "email": email,
        "aud": audience or cfg.supabase_jwt_audience,
        "aal": aal,
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "user_metadata": {"full_name": full_name},
    }
    return jwt.encode(
        payload,
        secret or cfg.supabase_jwt_secret,
        algorithm="HS256",
    )
