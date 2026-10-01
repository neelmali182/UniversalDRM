"""FastAPI application entry point for UniversalDRM API (§5.1, §19).

Versioned under /v1. Routes:
  /v1/assets   — upload, protect, lifecycle
  /v1/shares   — share creation and revocation
  /v1/viewer   — OTP verify, session, heartbeat, tile delivery
  /v1/audit    — event queries
  /v1/health   — liveness probe
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from html import escape
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .config import settings
from .middleware.security_headers import SecurityHeadersMiddleware
from .routes import assets, shares, viewer, audit
from .routes.shares import _shares


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    # Future: initialize DB pool, Redis connection, Celery, etc.
    yield
    # Future: close DB pool, flush sinks


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="UniversalDRM API",
        description=(
            "Browser-first content protection and capture-resistant sharing. "
            "Every policy field is tagged enforced / best_effort / traceability. "
            "See §2.2 of the implementation plan for what a browser-only system "
            "cannot guarantee."
        ),
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # CORS — restrict to configured origins in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    # Security headers (HSTS, CSP, etc.) — §15.3
    app.add_middleware(SecurityHeadersMiddleware)

    # Static assets for UniversalDRM viewer
    import os
    import universal_drm
    from fastapi.staticfiles import StaticFiles

    static_path = universal_drm.static_dir()
    if os.path.exists(static_path):
        app.mount("/udrm", StaticFiles(directory=static_path), name="udrm")

    # Routers
    app.include_router(assets.router, prefix="/v1")
    app.include_router(shares.router, prefix="/v1")
    app.include_router(viewer.router, prefix="/v1")
    app.include_router(audit.router, prefix="/v1")

    @app.get("/v/{token}", response_class=HTMLResponse, include_in_schema=False)
    async def share_viewer(token: str):
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        share = next(
            (item for item in _shares.values() if hmac.compare_digest(item["token_hash"], token_hash)),
            None,
        )
        if not share or share["revoked"]:
            raise HTTPException(status_code=404, detail="Share not found or revoked")
        if share["expires_at"] and share["expires_at"] <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Share expired")
        page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UniversalDRM shared document</title>
<link rel="stylesheet" href="/udrm/universal-drm.css">
</head>
<body>
<main id="share-viewer" data-share-token="{escape(token, quote=True)}">
<h1>Shared document</h1>
<p id="share-status" role="status">Verify your email to view this document.</p>
<form id="email-form">
<label>Email address <input name="email" type="email" autocomplete="email" required></label>
<button type="submit">Send verification code</button>
</form>
<form id="otp-form" hidden>
<label>Verification code <input name="otp" inputmode="numeric" autocomplete="one-time-code" required></label>
<button type="submit">Verify and open</button>
</form>
<div id="viewer"></div>
</main>
<script src="/udrm/universal-drm.js"></script>
<script src="/udrm/share-viewer.js"></script>
</body>
</html>"""
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    @app.get("/", tags=["info"])
    async def root():
        return {
            "name": "UniversalDRM API",
            "version": "0.1.0",
            "status": "online",
            "docs": "/docs",
            "health": "/v1/health",
        }

    @app.get("/v1/health", tags=["health"])
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()
