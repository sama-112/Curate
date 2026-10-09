import asyncio
import logging

import httpx

from curate.domain import IncomingMessage, Messenger, Stylist, StylistReply
from curate.inbox import Inbox

logger = logging.getLogger(__name__)


class MessageWorker:
    def __init__(
        self,
        inbox: Inbox,
        stylist: Stylist,
        messenger: Messenger,
        max_attempts: int = 3,
        poll_seconds: float = 0.25,
    ):
        self.inbox = inbox
        self.stylist = stylist
        self.messenger = messenger
        self.max_attempts = max_attempts
        self.poll_seconds = poll_seconds

    async def process_one(self) -> bool:
        row = self.inbox.next_due()
        if row is None:
            return False
        event_id = row["event_id"]
        attempts = row["attempts"] + 1
        try:
            message = IncomingMessage.model_validate_json(row["payload"])
            if row["reply"]:
                reply = StylistReply.model_validate_json(row["reply"])
            else:
                try:
                    reply = await self.stylist.reply(message)
                except Exception:
                    if attempts < self.max_attempts:
                        raise
                    logger.error("generation_failed event_id=%s", event_id)
                    reply = StylistReply(
                        source="error",
                        text=(
                            "I couldn't generate styling advice just now. Please try again shortly."
                        ),
                    )
                self.inbox.save_reply(event_id, reply)
            sent_id = await self.messenger.send_text(
                message.conversation_id, reply.text, f"reply:{event_id}"
            )
            self.inbox.delivered(event_id, sent_id)
            logger.info("reply_delivered event_id=%s source=%s", event_id, reply.source)
        except Exception as error:
            terminal = attempts >= self.max_attempts
            if isinstance(error, httpx.HTTPStatusError):
                terminal = terminal or (
                    400 <= error.response.status_code < 500 and error.response.status_code != 429
                )
            # Exception messages can contain provider response bodies or credentials.
            name = type(error).__name__
            self.inbox.failed_attempt(event_id, attempts, name, terminal=terminal)
            logger.warning(
                "reply_failed event_id=%s error=%s terminal=%s", event_id, name, terminal
            )
        return True

    async def run(self) -> None:
        while True:
            try:
                worked = await self.process_one()
            except Exception as error:
                logger.error("inbox_worker_error error=%s", type(error).__name__)
                worked = False
            if not worked:
                await asyncio.sleep(self.poll_seconds)
