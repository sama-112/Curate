from typing import Literal, Protocol

from pydantic import BaseModel, Field


class IncomingMessage(BaseModel):
    """Transport-independent input. Identity is supplied by the verified adapter."""

    event_id: str
    agent_id: str
    conversation_id: str
    message_id: str
    sender_id: str
    text: str = Field(max_length=10000)
    has_unsupported_parts: bool = False


class StylistReply(BaseModel):
    text: str = Field(min_length=1)
    source: Literal["openai", "unsupported", "error"]


class Stylist(Protocol):
    async def reply(self, message: IncomingMessage) -> StylistReply: ...


class Messenger(Protocol):
    async def send_text(self, conversation_id: str, text: str, key: str) -> str: ...
