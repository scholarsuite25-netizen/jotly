from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantAccessContext, require_permission
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.meetings_media import MediaAsset
from app.services.audit import record_audit_event
from app.services.storage_media import (
    create_signed_playback_url,
    get_private_storage,
    verify_signed_playback_signature,
)

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{asset_id}/playback-url")
def get_media_playback_url(
    asset_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Authorises playback for a permitted tenant user and returns a short-lived
    signed playback URL. Logs a `media.playback.authorise` audit event.
    """
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        asset = db.scalars(
            select(MediaAsset).where(MediaAsset.id == asset_id)
        ).first()
        if asset is None:
            raise NexusAPIError(
                status_code=404,
                code="media_asset_not_found",
                message="Media asset not found in the active organisation.",
            )

        signed = create_signed_playback_url(
            organisation_id=ctx.organisation.id,
            asset_id=asset.id,
        )
        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="media.playback.authorise",
            resource_type="media_asset",
            resource_id=asset.id,
            result="succeeded",
            metadata={"expires_at": signed["expires_at"]},
        )
        db.commit()

        return {
            "asset_id": asset.id,
            "organisation_id": ctx.organisation.id,
            "playback_url": signed["url"],
            "expires_at": signed["expires_at"],
            "ttl_seconds": signed["ttl_seconds"],
        }


@router.get("/{asset_id}/stream")
def stream_signed_media(
    asset_id: str,
    org_id: str = Query(...),
    expires: int = Query(...),
    signature: str = Query(...),
    db: Session = Depends(get_db),
) -> Response:
    """
    Streams media bytes only if the short-lived HMAC signature and expiration timestamp are valid
    for `(org_id, asset_id, expires)`. Rejects expired or tampered links with 403 Forbidden.
    """
    verify_signed_playback_signature(
        organisation_id=org_id,
        asset_id=asset_id,
        expires=expires,
        signature=signature,
    )

    storage = get_private_storage()
    with tenant_db_context(db, organisation_id=org_id):
        asset = db.scalars(
            select(MediaAsset).where(MediaAsset.id == asset_id)
        ).first()
        if asset is None:
            raise NexusAPIError(
                status_code=404,
                code="media_asset_not_found",
                message="Media asset not found.",
            )
        raw_bytes = storage.get_bytes(
            organisation_id=org_id, object_key=asset.object_key
        )
        return Response(
            content=raw_bytes,
            media_type=asset.mime_type,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
