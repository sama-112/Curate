import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from curate.domain import IncomingMessage
from curate.integrations.openai import OpenAIStylist


def message(**changes):
    return IncomingMessage(
        event_id="event-1",
        agent_id="agent-1",
        conversation_id="chat-1",
        message_id="msg-1",
        sender_id="user-1",
        text="Style my navy shirt.",
        **changes,
    )


@pytest.mark.parametrize(
    "status,text",
    [
        ("completed", "Pair it with beige chinos."),
        ("incomplete", "Partial answer"),
        ("completed", ""),
    ],
)
def test_real_sdk_responses_request(settings, status, text):
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 0,
                "status": status,
                "model": settings.openai_text_model,
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": text, "annotations": []}],
                    }
                ],
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
            },
        )

    async def run():
        async with AsyncOpenAI(
            api_key="test",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
        ) as client:
            stylist = OpenAIStylist(client, settings)
            if status == "completed" and text:
                assert (await stylist.reply(message())).text == text
            else:
                with pytest.raises(RuntimeError):
                    await stylist.reply(message())

    asyncio.run(run())
    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/responses"
    assert body["model"] == "gpt-6-luna"
    assert body["input"] == "Style my navy shirt."
    assert body["store"] is False
    assert body["max_output_tokens"] == settings.openai_max_output_tokens
    assert "current message" in body["instructions"]


def test_attachment_does_not_call_openai(settings):
    stylist = OpenAIStylist(None, settings)
    reply = asyncio.run(stylist.reply(message(has_unsupported_parts=True)))
    assert reply.source == "unsupported"


def test_model_is_configurable(settings):
    settings.openai_text_model = "custom-supported-model"
    assert OpenAIStylist(None, settings).settings.openai_text_model == "custom-supported-model"
