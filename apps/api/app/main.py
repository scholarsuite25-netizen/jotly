from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.errors import register_exception_handlers
from app.routers import (
    audit,
    documents,
    exports_evaluation,
    health,
    identity,
    jobs,
    media,
    meetings,
    organisations,
    speech,
    intelligence,
    collaboration,
    transcripts,
    transcriptions,
    voice_governance,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.nexus_app_name,
        version="0.1.0",
        docs_url=f"{settings.nexus_api_prefix}/docs",
        openapi_url=f"{settings.nexus_api_prefix}/openapi.json",
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Correlation-ID",
            "X-Organisation-ID",
            "Idempotency-Key",
        ],
    )

    register_exception_handlers(app)

    prefix = settings.nexus_api_prefix
    app.include_router(health.router, prefix=prefix)
    app.include_router(identity.router, prefix=prefix)
    app.include_router(organisations.router, prefix=prefix)
    app.include_router(meetings.router, prefix=prefix)
    app.include_router(media.router, prefix=prefix)
    app.include_router(transcriptions.router, prefix=prefix)
    app.include_router(transcripts.router, prefix=prefix)
    app.include_router(exports_evaluation.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(documents.transcript_ingest_router, prefix=prefix)
    app.include_router(speech.router, prefix=prefix)
    app.include_router(speech.audio_router, prefix=prefix)
    app.include_router(voice_governance.router, prefix=prefix)
    app.include_router(intelligence.router, prefix=prefix)
    app.include_router(collaboration.router, prefix=prefix)
    app.include_router(audit.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)

    return app


app = create_app()
