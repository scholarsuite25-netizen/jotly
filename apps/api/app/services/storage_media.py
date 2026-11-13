from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Optional
from urllib.parse import urlencode

from app.core.config import Settings, get_settings
from app.core.errors import NexusAPIError

ALLOWED_MEDIA_MIME_TYPES: frozenset[str] = frozenset(
    {
        "audio/webm",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
        "audio/mpeg",
        "audio/mp4",
        "video/webm",
        "video/mp4",
    }
)

FORBIDDEN_MAGIC_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"MZ", "Windows PE executable"),
    (b"\x7fELF", "Linux ELF executable"),
    (b"#!/", "Shell script"),
    (b"<script", "Embedded HTML/script"),
    (b"PK\x03\x04", "ZIP/Macro archive disguised as media"),
)


def validate_media_mime_type(mime_type: str) -> str:
    normalized = mime_type.split(";")[0].strip().lower()
    if normalized not in ALLOWED_MEDIA_MIME_TYPES:
        raise NexusAPIError(
            status_code=415,
            code="unsupported_media_type",
            message=f"MIME type '{normalized}' is not on the approved media allowlist.",
        )
    return normalized


def validate_media_magic_bytes(mime_type: str, header_bytes: bytes) -> str:
    """
    Inspects file header signature (magic bytes) on the first chunk to ensure the binary
    container matches the declared audio/video MIME type and rejects disguised executables/scripts.
    Returns the detected container/codec label.
    """
    normalized = validate_media_mime_type(mime_type)
    if len(header_bytes) < 4:
        raise NexusAPIError(
            status_code=400,
            code="invalid_media_signature",
            message="Media header is too short to verify file signature.",
        )

    for forbidden_sig, reason in FORBIDDEN_MAGIC_SIGNATURES:
        if header_bytes.startswith(forbidden_sig):
            raise NexusAPIError(
                status_code=400,
                code="malicious_or_disguised_file_signature",
                message=f"Rejected upload: file signature matches {reason}.",
            )

    if normalized in ("audio/wav", "audio/x-wav"):
        if not (header_bytes.startswith(b"RIFF") and b"WAVE" in header_bytes[:16]):
            raise NexusAPIError(
                status_code=400,
                code="invalid_media_signature",
                message="File signature does not match WAV (RIFF/WAVE) container.",
            )
        return "pcm_wav"

    if normalized in ("audio/webm", "video/webm"):
        if not header_bytes.startswith(b"\x1a\x45\xdf\xa3"):
            raise NexusAPIError(
                status_code=400,
                code="invalid_media_signature",
                message="File signature does not match WebM/EBML container.",
            )
        return "opus_webm"

    if normalized == "audio/ogg":
        if not header_bytes.startswith(b"OggS"):
            raise NexusAPIError(
                status_code=400,
                code="invalid_media_signature",
                message="File signature does not match Ogg container.",
            )
        return "opus_ogg"

    if normalized == "audio/mpeg":
        if not (
            header_bytes.startswith(b"ID3")
            or header_bytes[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
        ):
            raise NexusAPIError(
                status_code=400,
                code="invalid_media_signature",
                message="File signature does not match MP3/ID3 audio stream.",
            )
        return "mp3"

    if normalized in ("audio/mp4", "video/mp4"):
        if b"ftyp" not in header_bytes[:16]:
            raise NexusAPIError(
                status_code=400,
                code="invalid_media_signature",
                message="File signature does not match ISO Base Media (MP4/ftyp) container.",
            )
        return "aac_mp4"

    raise NexusAPIError(
        status_code=415,
        code="unsupported_media_type",
        message="Unsupported media format.",
    )


class PrivateObjectStorageAdapter:
    """
    Private S3-compatible (Cloudflare R2 / MinIO) object storage adapter.
    Enforces strict tenant key prefixing (`tenants/{organisation_id}/...`)
    and never exposes underlying storage credentials or public bucket URLs.
    """

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    @staticmethod
    def _assert_tenant_key_prefix(organisation_id: str, object_key: str) -> None:
        expected_prefix = f"tenants/{organisation_id}/"
        if not object_key.startswith(expected_prefix) or ".." in object_key:
            raise PermissionError(
                f"Storage tenant isolation violation: key '{object_key}' "
                f"outside tenant prefix '{expected_prefix}'."
            )

    def put_bytes(
        self, *, organisation_id: str, object_key: str, data: bytes
    ) -> str:
        self._assert_tenant_key_prefix(organisation_id, object_key)
        self._objects[object_key] = bytes(data)
        return hashlib.sha256(data).hexdigest()

    def get_bytes(self, *, organisation_id: str, object_key: str) -> bytes:
        self._assert_tenant_key_prefix(organisation_id, object_key)
        if object_key not in self._objects:
            raise NexusAPIError(
                status_code=404,
                code="storage_object_not_found",
                message="Requested media object does not exist in private storage.",
            )
        return self._objects[object_key]

    def exists(self, *, organisation_id: str, object_key: str) -> bool:
        self._assert_tenant_key_prefix(organisation_id, object_key)
        return object_key in self._objects


_storage_singleton = PrivateObjectStorageAdapter()


def get_private_storage() -> PrivateObjectStorageAdapter:
    return _storage_singleton


def create_signed_playback_url(
    *,
    organisation_id: str,
    asset_id: str,
    ttl_seconds: Optional[int] = None,
    now: Optional[datetime] = None,
    settings: Optional[Settings] = None,
) -> dict[str, str | int]:
    """
    Creates a short-lived HMAC-SHA256 signed playback URL bound to organisation_id and asset_id.
    Never returns permanent or unrestricted storage URLs.
    """
    cfg = settings or get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else cfg.s3_presigned_url_ttl_seconds
    current_time = now or datetime.now(timezone.utc)
    expires_at = int((current_time + timedelta(seconds=ttl)).timestamp())

    signing_payload = f"{organisation_id}:{asset_id}:{expires_at}"
    signature = hmac.new(
        cfg.supabase_jwt_secret.encode("utf-8"),
        signing_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    query = urlencode(
        {
            "org_id": organisation_id,
            "expires": str(expires_at),
            "signature": signature,
        }
    )
    return {
        "url": f"{cfg.nexus_api_prefix}/media/{asset_id}/stream?{query}",
        "expires_at": expires_at,
        "ttl_seconds": ttl,
    }


def verify_signed_playback_signature(
    *,
    organisation_id: str,
    asset_id: str,
    expires: int,
    signature: str,
    now: Optional[datetime] = None,
    settings: Optional[Settings] = None,
) -> None:
    """
    Verifies a short-lived signed playback URL. Rejects expired, tampered, or cross-tenant URLs.
    """
    cfg = settings or get_settings()
    current_ts = int((now or datetime.now(timezone.utc)).timestamp())
    if expires < current_ts:
        raise NexusAPIError(
            status_code=403,
            code="playback_url_expired",
            message="Signed playback URL has expired.",
        )

    expected_payload = f"{organisation_id}:{asset_id}:{expires}"
    expected_sig = hmac.new(
        cfg.supabase_jwt_secret.encode("utf-8"),
        expected_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        raise NexusAPIError(
            status_code=403,
            code="invalid_playback_signature",
            message="Signed playback URL signature is invalid or cross-tenant.",
        )
