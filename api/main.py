"""FastAPI application entry point for the AI Trainer web backend.

Run locally with:
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
        uvicorn api.main:app --reload --port 8000

The Streamlit app (``app.py``) remains the fallback/dev surface; this API is the
new boundary that the Next.js frontend in ``web/`` talks to.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Keep Gemini/gRPC runtime happy (same default as run.sh).
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
load_dotenv()

from api.routers import (  # noqa: E402  (after env setup)
    activities,
    athlete_profile,
    coach,
    dashboard,
    decisions,
    hrv,
    planning,
    session_quality,
    sleep,
    system,
    today,
)

app = FastAPI(
    title="AI Trainer API",
    version="0.1.0",
    description="HTTP boundary over the existing AI Trainer training logic.",
)

# Frontend dev origins. Tighten/override via WEB_ORIGINS for deployment.
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
allow_origins = [
    origin.strip()
    for origin in os.getenv("WEB_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(coach.router)
app.include_router(decisions.router)
app.include_router(hrv.router)
app.include_router(activities.router)
app.include_router(athlete_profile.router)
app.include_router(planning.router)
app.include_router(session_quality.router)
app.include_router(sleep.router)
app.include_router(system.router)
app.include_router(today.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
