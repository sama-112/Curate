import asyncio

import httpx
import pytest

from curate.adapters.relay import RelayEnvelope, normalize
from curate.domain import StylistReply
from curate.inbox import Inbox
from curate.worker import MessageWorker


class FakeStylist:
    calls = 0

    async def reply(self, message):
        self.calls += 1
        return StylistReply(text=f"Advice for {message.sender_id}", source="openai")


class FakeMessenger:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    async def send_text(self, conversation_id, text, key):
        self.calls.append((conversation_id, text, key))
        if self.error:
            raise self.error
        return "sent-1"


def test_restart_reuses_cached_reply_and_idempotency_key(settings, event):
    inbox = Inbox(settings.inbox_path)
    message = normalize(RelayEnvelope.model_validate(event))
    assert inbox.accept(message)
    assert not inbox.accept(message)
    # Even a different event ID for the same inbound message cannot duplicate work.
    assert not inbox.accept(message.model_copy(update={"event_id": "event-2"}))
    stylist = FakeStylist()
    messenger = FakeMessenger(httpx.ReadTimeout("uncertain send"))
    asyncio.run(MessageWorker(inbox, stylist, messenger).process_one())
    assert stylist.calls == 1
    inbox.close()

    inbox = Inbox(settings.inbox_path)
    with inbox.db:
        inbox.db.execute("UPDATE inbox SET next_attempt=0")
    messenger.error = None
    asyncio.run(MessageWorker(inbox, stylist, messenger).process_one())
    assert stylist.calls == 1
    assert messenger.calls[0] == messenger.calls[1]
    assert inbox.counts() == {"delivered": 1}
    inbox.close()


def test_generation_failure_sends_honest_error(settings, event, caplog):
    class FailingStylist:
        async def reply(self, message):
            raise RuntimeError("private-provider-error-with-secret")

    inbox = Inbox(settings.inbox_path)
    inbox.accept(normalize(RelayEnvelope.model_validate(event)))
    messenger = FakeMessenger()
    asyncio.run(MessageWorker(inbox, FailingStylist(), messenger, max_attempts=1).process_one())
    assert "couldn't generate" in messenger.calls[0][1]
    assert "private-provider" not in caplog.text
    assert inbox.counts() == {"delivered": 1}
    assert '"source":"error"' in inbox.db.execute("SELECT reply FROM inbox").fetchone()[0]
    inbox.close()


@pytest.mark.parametrize("status,terminal", [(401, True), (429, False), (503, False)])
def test_relay_retry_policy(settings, event, status, terminal):
    request = httpx.Request("POST", "https://api.relayapp.im/v1/chats/chat-1/messages")
    error = httpx.HTTPStatusError(
        "failure", request=request, response=httpx.Response(status, request=request)
    )
    inbox = Inbox(settings.inbox_path)
    inbox.accept(normalize(RelayEnvelope.model_validate(event)))
    asyncio.run(MessageWorker(inbox, FakeStylist(), FakeMessenger(error)).process_one())
    assert inbox.counts() == {"failed" if terminal else "pending": 1}
    inbox.close()


def test_users_stay_in_their_own_conversations(settings, event):
    inbox = Inbox(settings.inbox_path)
    first = normalize(RelayEnvelope.model_validate(event))
    second = first.model_copy(
        update={
            "event_id": "event-2",
            "message_id": "msg-2",
            "sender_id": "user-2",
            "conversation_id": "chat-2",
        }
    )
    inbox.accept(first)
    inbox.accept(second)
    messenger = FakeMessenger()
    worker = MessageWorker(inbox, FakeStylist(), messenger)
    asyncio.run(worker.process_one())
    asyncio.run(worker.process_one())
    assert messenger.calls == [
        ("chat-1", "Advice for user-1", "reply:event-1"),
        ("chat-2", "Advice for user-2", "reply:event-2"),
    ]
    inbox.close()
