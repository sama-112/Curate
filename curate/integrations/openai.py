from openai import AsyncOpenAI

from curate.config import Settings
from curate.domain import IncomingMessage, StylistReply

INSTRUCTIONS = """You are Curate, a thoughtful professional personal stylist.
Give specific, practical advice and explain your reasoning briefly. Respect the user's
budget and preferences. Prefer clothing they already own and avoid unnecessary shopping.
Respectfully challenge choices when useful instead of automatically agreeing.
Ask at most one focused question when you need more information. Keep replies under 200 words.
This is an early text-only prototype. You have only the current message: no saved wardrobe,
preferences, photographs, browsing, image generation, or other tools. Never claim to have
seen images, saved information, checked products, or completed actions you cannot perform.
Do not infer physical characteristics. Do not invent retailer pricing or availability.
"""


class OpenAIStylist:
    def __init__(self, client: AsyncOpenAI, settings: Settings):
        self.client = client
        self.settings = settings

    async def reply(self, message: IncomingMessage) -> StylistReply:
        if message.has_unsupported_parts or not message.text.strip():
            return StylistReply(
                text="I can help with text styling questions in this prototype. "
                "Photo, video, voice, and interactive controls arrive in later milestones. "
                "Please describe what you would like help with.",
                source="unsupported",
            )
        response = await self.client.responses.create(
            model=self.settings.openai_text_model,
            instructions=INSTRUCTIONS,
            input=message.text,
            max_output_tokens=self.settings.openai_max_output_tokens,
            store=False,
        )
        if response.status != "completed" or not response.output_text.strip():
            raise RuntimeError("OpenAI did not return a completed text response")
        return StylistReply(text=response.output_text.strip(), source="openai")
