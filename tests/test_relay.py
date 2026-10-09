import asyncio
import json
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from curate.adapters.relay import RelayEnvelope, RelayMessenger, normalize, render_text
from curate.config import Settings
from curate.domain import StylistReply
from curate.main import create_app
from tests.conftest import signed


@pytest.fixture
def app(settings, monkeypatch):
    # Keep HTTP/provider tests deterministic and completely offline.
    calls = {"gpt": [], "relay": []}

    async def reply(self, message):
        calls["gpt"].append(message)
        return StylistReply(text="Try a white oxford with your navy chinos.", source="openai")

    async def send(self, conversation_id, text, key):
        calls["relay"].append((conversation_id, text, key))
        return "reply-message-1"

    monkeypatch.setattr("curate.main.OpenAIStylist.reply", reply)
    monkeypatch.setattr("curate.main.RelayMessenger.send_text", send)
    application = create_app(settings)
    application.state.calls = calls
    return application


def post(client, event, **kwargs):
    body, headers = signed(event, **kwargs)
    return client.post("/webhooks/relay", content=body, headers=headers)


def test_signed_message_gpt_reply_and_duplicate(app, event):
    with TestClient(app) as client:
        assert post(client, event).status_code == 204
        assert post(client, event).status_code == 204
        for _ in range(100):
            if client.get("/readyz").json()["inbox"].get("delivered") == 1:
                break
            time.sleep(0.01)
        assert len(app.state.calls["gpt"]) == 1
        assert app.state.calls["relay"] == [
            ("chat-1", "Try a white oxford with your navy chinos.", "reply:event-1")
        ]
        assert client.get("/readyz").json()["inbox"] == {"delivered": 1}


@pytest.mark.parametrize("signature", [None, "v1,AAAA", "broken", "v1,???", "v2,AAAA"])
def test_reject_invalid_signature(app, event, signature):
    body, headers = signed(event)
    if signature is None:
        headers.pop("webhook-signature")
    else:
        headers["webhook-signature"] = signature
    with TestClient(app) as client:
        assert client.post("/webhooks/relay", content=body, headers=headers).status_code == 401
        assert client.get("/readyz").json()["inbox"] == {}


@pytest.mark.parametrize("offset", [-600, 600])
def test_reject_stale_or_future_timestamp(app, event, offset):
    with TestClient(app) as client:
        timestamp = datetime.now(UTC) + timedelta(seconds=offset)
        assert post(client, event, timestamp=timestamp).status_code == 401
        assert client.get("/readyz").json()["inbox"] == {}


def test_reject_modified_raw_body(app, event):
    body, headers = signed(event)
    with TestClient(app) as client:
        assert (
            client.post("/webhooks/relay", content=body + " ", headers=headers).status_code == 401
        )


def test_reject_header_body_id_mismatch(app, event):
    with TestClient(app) as client:
        assert post(client, event, header_id="different").status_code == 401


def test_reject_malformed_message(app, event):
    event["data"].pop("chat_id")
    with TestClient(app) as client:
        assert post(client, event).status_code == 401
        assert client.get("/readyz").json()["inbox"] == {}


def test_body_size_limit(app):
    with TestClient(app) as client:
        assert client.post("/webhooks/relay", content=b"x" * 262145).status_code == 413


def test_acknowledgement_does_not_wait_for_gpt(app, event, monkeypatch):
    async def slow_reply(self, message):
        await asyncio.sleep(60)

    monkeypatch.setattr("curate.main.OpenAIStylist.reply", slow_reply)
    with TestClient(app) as client:
        started = time.monotonic()
        assert post(client, event).status_code == 204
        assert time.monotonic() - started < 2
        assert client.get("/readyz").json()["inbox"] == {"pending": 1}


def test_missing_credentials_fail_closed(tmp_path):
    settings = Settings(
        _env_file=None,
        openai_api_key="",
        relay_agent_token="",
        relay_webhook_secret="",
        inbox_path=tmp_path / "inbox.db",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/readyz").status_code == 503
        assert client.post("/webhooks/relay", json={}).status_code == 503


@pytest.mark.parametrize("change", ["own", "agent", "outbound", "group", "other_event"])
def test_ignore_non_user_direct_messages(app, event, change):
    if change == "own":
        event["data"]["is_from_me"] = True
    elif change == "agent":
        event["data"]["from_handle"]["kind"] = "agent"
    elif change == "outbound":
        event["data"]["direction"] = "outbound"
    elif change == "group":
        event["data"]["chat"]["is_group"] = True
    else:
        event["event_type"] = "message.sent"
    with TestClient(app) as client:
        assert post(client, event).status_code == 204
        assert client.get("/readyz").json()["inbox"] == {}
        assert app.state.calls == {"gpt": [], "relay": []}


def test_inbox_failure_is_retriable(app, event, monkeypatch):
    import sqlite3

    def unavailable(_):
        raise sqlite3.OperationalError("disk full")

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.inbox, "accept", unavailable)
        assert post(client, event).status_code == 503


def test_media_is_marked_unsupported(event):
    event["data"]["parts"] = [{"type": "media", "url": "https://example.test/private"}]
    message = normalize(RelayEnvelope.model_validate(event))
    assert message.has_unsupported_parts and message.text == ""


def test_relay_rest_wire_format_and_utf16_limit():
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(202, json={"id": "sent-1"})

    async def run():
        async with httpx.AsyncClient(
            base_url="https://api.relayapp.im", transport=httpx.MockTransport(transport)
        ) as client:
            result = await RelayMessenger(client).send_text("chat-1", "Hello", "reply:event-1")
            assert result == "sent-1"

    asyncio.run(run())
    assert requests[0].url.path == "/v1/chats/chat-1/messages"
    assert requests[0].headers["Idempotency-Key"] == "reply:event-1"
    assert json.loads(requests[0].content) == {
        "message": {"parts": [{"type": "text", "value": "Hello"}]}
    }
    text = render_text("🧥" * 10000)["message"]["parts"][0]["value"]
    assert len(text.encode("utf-16-le")) <= 20000
