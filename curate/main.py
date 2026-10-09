import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI
from pydantic import ValidationError
from standardwebhooks import Webhook

from curate.adapters.relay import RelayEnvelope, RelayMessenger, normalize
from curate.config import Settings
from curate.inbox import Inbox
from curate.integrations.openai import OpenAIStylist
from curate.worker import MessageWorker

logger = logging.getLogger(__name__)
MAX_WEBHOOK_BYTES = 256 * 1024


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=settings.log_level.upper())
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        inbox = Inbox(settings.inbox_path)
        app.state.inbox = inbox
        app.state.worker_task = None
        missing = settings.missing_credentials()
        if missing:
            logger.warning("credentials_missing names=%s", ",".join(missing))
            try:
                yield
            finally:
                inbox.close()
            return

        # Invalid secrets fail at startup, before accepting any events.
        app.state.verifier = Webhook(settings.relay_webhook_secret.get_secret_value())
        async with (
            AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=settings.openai_timeout_seconds,
                max_retries=settings.openai_max_retries,
            ) as openai,
            httpx.AsyncClient(
                base_url=settings.relay_api_url,
                headers={
                    "Authorization": f"Bearer {settings.relay_agent_token.get_secret_value()}"
                },
                timeout=settings.relay_timeout_seconds,
            ) as relay,
        ):
            worker = MessageWorker(
                inbox,
                OpenAIStylist(openai, settings),
                RelayMessenger(relay),
                settings.worker_max_attempts,
                settings.worker_poll_seconds,
            )
            task = asyncio.create_task(worker.run(), name="curate-message-worker")
            app.state.worker_task = task
            try:
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                inbox.close()

    app = FastAPI(title="Curate", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def ready(request: Request):
        missing = settings.missing_credentials()
        task = request.app.state.worker_task
        detail = {
            "configured": not missing,
            "missing": missing,
            "worker_running": bool(task and not task.done()),
            "inbox": request.app.state.inbox.counts(),
        }
        if missing or not detail["worker_running"]:
            return JSONResponse(detail, status_code=503)
        return detail

    @app.post("/webhooks/relay", status_code=204)
    async def receive(request: Request) -> Response:
        if settings.missing_credentials():
            raise HTTPException(503, "Configure local credentials before receiving messages")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_WEBHOOK_BYTES:
                raise HTTPException(413, "Webhook too large")
        try:
            # Standard Webhooks verifies HMAC and ±5-minute timestamp before JSON parsing.
            payload = request.app.state.verifier.verify(bytes(body), dict(request.headers))
            envelope = RelayEnvelope.model_validate(payload)
            if envelope.event_id != request.headers.get("webhook-id"):
                raise ValueError("Header/body event ID mismatch")
            message = normalize(envelope)
        except (ValueError, ValidationError):
            raise HTTPException(401, "Webhook rejected") from None
        except Exception:
            # Includes the verifier's malformed-signature errors; never log signed bodies.
            raise HTTPException(401, "Webhook rejected") from None
        if message:
            try:
                inserted = request.app.state.inbox.accept(message)
            except sqlite3.Error:
                raise HTTPException(503, "Inbox unavailable") from None
            logger.info("event_accepted event_id=%s new=%s", envelope.event_id, inserted)
        return Response(status_code=204)

    return app


app = create_app()
