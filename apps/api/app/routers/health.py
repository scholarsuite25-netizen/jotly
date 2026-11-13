from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.nexus_app_name,
        "environment": settings.nexus_env,
        "voice_cloning_enabled": settings.voice_cloning_enabled,
        "email_providers": settings.ordered_email_providers,
        "topology": {
            "frontend": "vercel",
            "edge_gateway": "cloudflare",
            "compute_host": "hostinger-self-hosted",
            "auth": "supabase-auth",
        },
    }


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    settings = get_settings()
    return {
        "status": "ready",
        "database": "connected",
        "voice_cloning_enabled": settings.voice_cloning_enabled,
    }
