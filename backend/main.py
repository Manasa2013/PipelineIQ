"""
PipelineIQ - Lead Qualification & Outreach Agent

FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.approval import router as approval_router
from backend.api.audit_logs import router as audit_logs_router
from backend.api.leads import router as leads_router
from backend.config import get_settings
from backend.database.session import async_session_factory, init_db
from backend.graph import PipelineState, pipeline_graph
from uuid import uuid4

# Import ORM models so they register on Base.metadata before table creation
import backend.models.sqlalchemy_models  # noqa: F401
from backend.models.sqlalchemy_models import Lead

settings = get_settings()

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(settings.APP_NAME)


# ── Lifecycle ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler: setup on start, cleanup on shutdown."""
    logger.info(f"{settings.APP_NAME} v{settings.APP_VERSION} starting...")
    await init_db()
    logger.info("Database tables initialised.")
    yield
    logger.info(f"{settings.APP_NAME} shutting down.")


# ── App instance ───────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered Lead Qualification & Outreach Agent",
    lifespan=lifespan,
)


# ── CORS ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Register routers ────────────────────────────────────────────────────

app.include_router(approval_router)
app.include_router(audit_logs_router)
app.include_router(leads_router)


# ── Run Pipeline endpoint ──────────────────────────────────────────────


@app.post("/pipeline/run", tags=["Pipeline"])
async def run_pipeline(payload: dict):
    """
    Execute the full lead qualification pipeline for a given lead.

    Accepts lead data as JSON, runs it through the LangGraph, and
    returns the final state (including logs, score, classification, etc.).

    For "hot" leads the graph will pause at the human-approval interrupt.
    The thread_id is persisted on the Lead record so the approval endpoints
    can resume the graph with the human's decision.
    """
    lead_data = payload.get("lead", payload)

    initial_state: PipelineState = {
        "lead": lead_data,
        "enrichment": None,
        "score": None,
        "classification": None,
        "draft_email": None,
        "approval_status": None,
        "logs": [],
    }

    # Generate a stable thread ID for this pipeline run.
    # This is stored on the Lead so approval endpoints can resume the graph.
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await pipeline_graph.ainvoke(initial_state, config=config)

        # Persist the thread_id on the Lead record so approval endpoints
        # can resume this graph thread when the human makes a decision.
        lead_id = lead_data.get("id") if isinstance(lead_data, dict) else None
        if lead_id:
            async with async_session_factory() as session:
                try:
                    db_lead = await session.get(Lead, lead_id)
                    if db_lead is not None:
                        db_lead.pipeline_thread_id = thread_id
                        await session.commit()
                        logger.info(
                            "Persisted pipeline thread_id %s for lead %s",
                            thread_id,
                            lead_id,
                        )
                except Exception as db_exc:
                    await session.rollback()
                    logger.warning(
                        "Could not persist thread_id for lead %s: %s",
                        lead_id,
                        db_exc,
                    )

        # Remove None entries for a cleaner response
        clean = {k: v for k, v in result.items() if v is not None}
        clean["thread_id"] = thread_id
        logger.info("Pipeline result keys: %s", list(result.keys()))
        try:
            encoded = jsonable_encoder(clean)
            return JSONResponse(content=encoded)
        except Exception as enc_exc:
            logger.error("JSONResponse encoding failed: %s", enc_exc)
            # Fallback: return string-safe version
            safe = {k: str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v
                    for k, v in clean.items()}
            return JSONResponse(content=safe)

    except Exception as exc:
        logger.error("Pipeline execution failed: %s", exc)
        return JSONResponse(
            content={
                "error": f"Pipeline execution failed: {str(exc)}",
                "lead": payload,
                "logs": [{"event_type": "pipeline_error", "message": str(exc)}],
            },
            status_code=500,
        )


# ── Health endpoint ────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """Return the current health status of the application."""
    return JSONResponse(
        content={
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


# ── Entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )