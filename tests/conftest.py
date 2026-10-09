import base64
import json
from datetime import UTC, datetime

import pytest
from standardwebhooks import Webhook

from curate.config import Settings

SECRET = "whsec_" + base64.b64encode(b"curate-test-key-do-not-use-live-12").decode()


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        openai_api_key="test-openai",
        relay_agent_token="test-relay",
        relay_webhook_secret=SECRET,
        inbox_path=tmp_path / "inbox.sqlite3",
        worker_poll_seconds=0.01,
    )


@pytest.fixture
def event():
    # Minimal subset of the official message.received fixture; unknown fields are accepted.
    return {
        "api_version": "v1",
        "webhook_version": "2026-08-30",
        "event_type": "message.received",
        "event_id": "event-1",
        "agent_id": "agent-1",
        "created_at": "2026-10-07T00:00:00Z",
        "trace_id": "test-trace",
        "data": {
            "id": "message-1",
            "chat_id": "chat-1",
            "chat": {"id": "chat-1", "is_group": False},
            "direction": "inbound",
            "is_from_me": False,
            "from_handle": {"id": "user-1", "kind": "user", "is_me": False},
            "parts": [{"type": "text", "value": "How can I style navy chinos?"}],
        },
    }


def signed(event, *, timestamp=None, header_id=None):
    body = json.dumps(event, ensure_ascii=False)
    timestamp = timestamp or datetime.now(UTC)
    event_id = header_id or event["event_id"]
    headers = {
        "content-type": "application/json",
        "webhook-id": event_id,
        "webhook-timestamp": str(int(timestamp.timestamp())),
        "webhook-signature": Webhook(SECRET).sign(event_id, timestamp, body),
    }
    return body, headers
