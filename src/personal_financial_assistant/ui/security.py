"""Protect the local browser boundary against cross-origin requests."""

import secrets

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HOST = "127.0.0.1:8765"
ORIGIN = f"http://{HOST}"
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
}


class LocalSecurity:
    """Enforce the loopback origin and a per-process request token."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        method = scope["method"]
        api = scope["path"].startswith("/api/")
        unsafe = method not in ("GET", "HEAD", "OPTIONS")
        denied = (
            headers.get("host") != HOST
            or (origin is not None and origin != ORIGIN)
            or (unsafe and origin != ORIGIN)
            or (unsafe and headers.get("sec-fetch-site") in ("cross-site", "same-site"))
            or (
                api
                and not secrets.compare_digest(
                    headers.get("x-pfa-token", "").encode("latin-1"),
                    self.token.encode("ascii"),
                )
            )
            or (
                unsafe
                and headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
            )
        )
        if denied:
            response = JSONResponse(
                {"error": {"code": "forbidden", "message": "Request rejected."}},
                status_code=403,
                headers=SECURITY_HEADERS,
            )
            await response(scope, receive, send)
            return

        async def secured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    response_headers[name] = value
            await send(message)

        await self.app(scope, receive, secured_send)
