"""Single-process HTTP resource controls. Distributed quotas belong at the gateway."""

import asyncio
import json
import logging
import time
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from risk_platform.config import Settings

logger = logging.getLogger("risk_platform.security")


class GuardrailMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings
        self.active = 0
        self.window = -1
        self.clients: dict[str, int] = {}

    def admit(self, peer: str) -> bool:
        window = int(time.monotonic() // 60)
        if window != self.window:
            self.clients.clear()
            self.window = window
        if peer not in self.clients and len(self.clients) >= self.settings.rate_limit_max_clients:
            return False
        count = self.clients.get(peer, 0)
        if count >= self.settings.requests_per_minute:
            return False
        self.clients[peer] = count + 1
        return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.monotonic()
        status = 500
        sent = False

        async def secure_send(message: Message) -> None:
            nonlocal status, sent
            if message["type"] == "http.response.start":
                sent = True
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-request-id", request_id.encode()),
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                )
                if scope["path"].startswith(("/v1/", "/health/")):
                    headers.append(
                        (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
                    )
                message = {**message, "headers": headers}
            await send(message)

        async def deny(code: int, detail: str, retry: bool = False):
            response = JSONResponse(
                {"detail": detail},
                status_code=code,
                headers={"Retry-After": "60"} if retry else None,
            )
            await response(scope, receive, secure_send)

        admitted = False
        try:
            raw_headers = scope.get("headers", [])
            if sum(len(k) + len(v) for k, v in raw_headers) > self.settings.max_header_bytes:
                await deny(431, "Request headers too large")
                return
            # Do not trust X-Forwarded-For. The loopback launcher disables proxy headers.
            peer = (scope.get("client") or ("unknown", 0))[0]
            if not self.admit(peer):
                await deny(429, "Request rate limit exceeded", retry=True)
                return
            if self.active >= self.settings.max_concurrent_requests:
                await deny(503, "Request capacity exhausted", retry=True)
                return
            self.active += 1
            admitted = True
            headers = dict(raw_headers)
            lengths = [v for k, v in raw_headers if k == b"content-length"]
            if len(lengths) > 1 or (lengths and b"transfer-encoding" in headers):
                await deny(400, "Ambiguous request framing")
                return
            if lengths:
                if not lengths[0].isdigit():
                    await deny(400, "Invalid content length")
                    return
                if len(lengths[0]) > 20 or int(lengths[0]) > self.settings.max_body_bytes:
                    await deny(413, "Request body too large")
                    return
            if headers.get(b"content-encoding", b"identity").lower() != b"identity":
                await deny(415, "Compressed request bodies are not supported")
                return
            if scope["path"].startswith("/v1/") and scope["method"] in {"POST", "PUT", "PATCH"}:
                content_type = headers.get(b"content-type", b"").split(b";")[0].strip().lower()
                if content_type != b"application/json":
                    await deny(415, "Content-Type must be application/json")
                    return
            body = bytearray()
            try:
                async with asyncio.timeout(self.settings.body_timeout_seconds):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            status = 499
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > self.settings.max_body_bytes:
                            await deny(413, "Request body too large")
                            return
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await deny(408, "Request body deadline exceeded")
                return
            consumed = False

            async def replay() -> Message:
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay, secure_send)
        except Exception:
            # Do not log exception text: it may contain SQL parameters or model inputs.
            if sent:
                raise
            await deny(500, "Internal server error")
        finally:
            if admitted:
                self.active -= 1
            route = scope.get("route")
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "route": getattr(route, "path", "unmatched"),
                        "status": status,
                        "duration_ms": round((time.monotonic() - start) * 1000, 2),
                    }
                )
            )
