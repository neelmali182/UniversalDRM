"""Security headers middleware for UniversalDRM API (§15.3).

Applied on every response:
- Strict-Transport-Security (HSTS)
- Content-Security-Policy (strict; no inline scripts)
- X-Content-Type-Options: nosniff
- Referrer-Policy: no-referrer
- Permissions-Policy
- X-Frame-Options: DENY (legacy; CSP frame-ancestors is primary)
- Cross-Origin-Opener-Policy / Cross-Origin-Resource-Policy

Cache-Control: no-store is set per-route on protected tile responses
(not globally here) to avoid caching viewer API responses by default.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every HTTP response (§15.3)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), "
            "usb=(), screen-wake-lock=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' blob: data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        return response
