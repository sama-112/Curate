from typing import Any, Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from curate.domain import IncomingMessage


class RelayEnvelope(BaseModel):
    api_version: Literal["v1"]
    webhook_version: Literal["2026-08-30"]
    event_type: str
    event_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1)
    data: dict[str, Any]


class RelayHandle(BaseModel):
    id: str = Field(min_length=1)
    kind: Literal["user", "agent"]
    is_me: bool


class RelayChat(BaseModel):
    id: str = Field(min_length=1)
    is_group: bool


class RelayPart(BaseModel):
    type: str
    value: str | None = None


class RelayMessage(BaseModel):
    id: str = Field(min_length=1)
    chat_id: str = Field(min_length=1)
    chat: RelayChat
    direction: Literal["inbound", "outbound"]
    is_from_me: bool
    from_handle: RelayHandle
    parts: list[RelayPart] = Field(max_length=100)


def normalize(envelope: RelayEnvelope) -> IncomingMessage | None:
    if envelope.event_type != "message.received":
        return None
    message = RelayMessage.model_validate(envelope.data)
    # This milestone supports direct messages from people. Prevent self/agent reply loops.
    if (
        message.is_from_me
        or message.from_handle.is_me
        or message.direction != "inbound"
        or message.from_handle.kind != "user"
        or message.chat.is_group
    ):
        return None
    if message.chat_id != message.chat.id:
        raise ValueError("Conflicting Relay chat IDs")
    return IncomingMessage(
        event_id=envelope.event_id,
        agent_id=envelope.agent_id,
        conversation_id=message.chat_id,
        message_id=message.id,
        sender_id=message.from_handle.id,
        text="\n".join(part.value or "" for part in message.parts if part.type == "text"),
        has_unsupported_parts=any(part.type != "text" for part in message.parts),
    )


def render_text(text: str) -> dict[str, Any]:
    # Relay's limit is 10,000 UTF-16 code units, including two per astral character.
    encoded = text.encode("utf-16-le")
    if len(encoded) > 20000:
        text = encoded[:19900].decode("utf-16-le", errors="ignore") + "…"
    return {"message": {"parts": [{"type": "text", "value": text}]}}


class RelayMessenger:
    """Use documented REST directly; no Git-sourced Python SDK dependency is needed."""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def send_text(self, conversation_id: str, text: str, key: str) -> str:
        response = await self.client.post(
            f"/v1/chats/{quote(conversation_id, safe='')}/messages",
            json=render_text(text),
            headers={"Idempotency-Key": key},
        )
        response.raise_for_status()
        return str(response.json()["id"])
