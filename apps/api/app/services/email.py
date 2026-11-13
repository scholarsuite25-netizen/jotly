from dataclasses import dataclass, field
from typing import Callable, Optional
import uuid

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import NexusAPIError

SUPPORTED_EMAIL_PROVIDERS: tuple[str, ...] = ("resend", "emailbump", "unipost")

FORBIDDEN_EMAIL_CONTENT_MARKERS: tuple[str, ...] = (
    "transcript_segment:",
    "voice_sample_bytes:",
    "BEGIN PRIVATE KEY",
)


@dataclass(frozen=True)
class EmailMessage:
    to_email: str
    subject: str
    text_body: str
    category: str = "transactional"
    organisation_id: Optional[str] = None


@dataclass(frozen=True)
class EmailDeliveryResult:
    provider: str
    message_id: str
    status: str
    attempted_providers: list[str] = field(default_factory=list)


def validate_email_privacy(message: EmailMessage) -> None:
    """
    Ensures email subjects and bodies never expose raw meeting transcripts,
    voice samples, or secret key material.
    """
    combined = f"{message.subject}\n{message.text_body}"
    for marker in FORBIDDEN_EMAIL_CONTENT_MARKERS:
        if marker.lower() in combined.lower():
            raise ValueError(
                f"Email privacy policy violation: forbidden marker '{marker}' detected."
            )


class MultiProviderEmailService:
    """
    Transactional email delivery adapter supporting Resend, Emailbump, and Unipost
    with configurable primary provider and automatic failover chain.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        transport_override: Optional[Callable[[str, EmailMessage], str]] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport_override = transport_override
        self.outbox: list[tuple[str, EmailMessage, EmailDeliveryResult]] = []

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        validate_email_privacy(message)
        providers = [
            p
            for p in self.settings.ordered_email_providers
            if p in SUPPORTED_EMAIL_PROVIDERS
        ]
        if not providers:
            raise NexusAPIError(
                status_code=500,
                code="email_provider_not_configured",
                message="No supported email provider (resend, emailbump, unipost) is configured.",
            )

        attempted: list[str] = []
        last_error: Optional[Exception] = None

        for provider in providers:
            attempted.append(provider)
            try:
                message_id = self._dispatch_via_provider(provider, message)
                result = EmailDeliveryResult(
                    provider=provider,
                    message_id=message_id,
                    status="sent",
                    attempted_providers=list(attempted),
                )
                self.outbox.append((provider, message, result))
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        raise NexusAPIError(
            status_code=502,
            code="email_delivery_failed",
            message=(
                f"All configured email providers failed ({', '.join(attempted)})."
            ),
        ) from last_error

    def _dispatch_via_provider(self, provider: str, message: EmailMessage) -> str:
        if self.transport_override is not None:
            return self.transport_override(provider, message)

        if self.settings.email_dry_run:
            return f"{provider}-dryrun-{uuid.uuid4().hex[:12]}"

        if provider == "resend":
            return self._send_resend(message)
        if provider == "emailbump":
            return self._send_emailbump(message)
        if provider == "unipost":
            return self._send_unipost(message)

        raise ValueError(f"Unsupported email provider '{provider}'.")

    def _send_resend(self, message: EmailMessage) -> str:
        if not self.settings.resend_api_key:
            raise RuntimeError("RESEND_API_KEY is not configured.")
        response = httpx.post(
            f"{self.settings.resend_api_base_url.rstrip('/')}/emails",
            headers={"Authorization": f"Bearer {self.settings.resend_api_key}"},
            json={
                "from": f"{self.settings.email_from_name} <{self.settings.email_from_address}>",
                "to": [message.to_email],
                "subject": message.subject,
                "text": message.text_body,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        return str(data.get("id") or f"resend-{uuid.uuid4().hex[:10]}")

    def _send_emailbump(self, message: EmailMessage) -> str:
        if not self.settings.emailbump_api_key:
            raise RuntimeError("EMAILBUMP_API_KEY is not configured.")
        response = httpx.post(
            f"{self.settings.emailbump_api_base_url.rstrip('/')}/messages/send",
            headers={"X-API-Key": self.settings.emailbump_api_key},
            json={
                "from_email": self.settings.email_from_address,
                "from_name": self.settings.email_from_name,
                "to": [message.to_email],
                "subject": message.subject,
                "text": message.text_body,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        return str(data.get("message_id") or f"emailbump-{uuid.uuid4().hex[:10]}")

    def _send_unipost(self, message: EmailMessage) -> str:
        if not self.settings.unipost_api_key:
            raise RuntimeError("UNIPOST_API_KEY is not configured.")
        response = httpx.post(
            f"{self.settings.unipost_api_base_url.rstrip('/')}/mail/send",
            headers={"Authorization": f"Bearer {self.settings.unipost_api_key}"},
            json={
                "sender": {
                    "email": self.settings.email_from_address,
                    "name": self.settings.email_from_name,
                },
                "recipients": [{"email": message.to_email}],
                "subject": message.subject,
                "content": {"type": "text/plain", "value": message.text_body},
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        return str(data.get("id") or f"unipost-{uuid.uuid4().hex[:10]}")
