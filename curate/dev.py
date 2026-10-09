"""Local setup checks; never print API keys or pass tokens as CLI arguments."""

import argparse
import asyncio
import os
import subprocess
import sys

import httpx
from openai import AsyncOpenAI

from curate.config import Settings
from curate.domain import IncomingMessage
from curate.integrations.openai import OpenAIStylist

RELAY_CLI = "relaymessenger@0.1.22"


def require(settings: Settings, *names: str) -> None:
    missing = [name for name in names if not getattr(settings, name.lower()).get_secret_value()]
    if missing:
        raise SystemExit("Set these values in .env: " + ", ".join(missing))


async def check_relay(settings: Settings) -> None:
    require(settings, "RELAY_AGENT_TOKEN")
    async with httpx.AsyncClient(timeout=settings.relay_timeout_seconds) as client:
        response = await client.get(
            f"{settings.relay_api_url}/v1/chats",
            params={"limit": 1},
            headers={"Authorization": f"Bearer {settings.relay_agent_token.get_secret_value()}"},
        )
        response.raise_for_status()
        if response.status_code != 200 or not isinstance(response.json().get("chats"), list):
            raise RuntimeError("Unexpected Relay authentication response")
    print("Relay authentication: PASS (read only; no message sent)")


async def openai_smoke(settings: Settings) -> None:
    require(settings, "OPENAI_API_KEY")
    async with AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    ) as client:
        reply = await OpenAIStylist(client, settings).reply(
            IncomingMessage(
                event_id="local-smoke",
                agent_id="local",
                conversation_id="local",
                message_id="local",
                sender_id="local",
                text="Suggest one outfit using a navy shirt, beige chinos, and white sneakers.",
            )
        )
        print(f"OpenAI Responses API: PASS (model={settings.openai_text_model})")
        print(reply.text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check-relay", "openai-smoke", "relay-login", "relay"])
    args = parser.parse_args()
    settings = Settings()
    try:
        if args.command == "check-relay":
            asyncio.run(check_relay(settings))
        elif args.command == "openai-smoke":
            asyncio.run(openai_smoke(settings))
        else:
            require(settings, "RELAY_AGENT_TOKEN")
            env = os.environ.copy()
            env["RELAY_AGENT_TOKEN"] = settings.relay_agent_token.get_secret_value()
            env["RELAY_API_URL"] = settings.relay_api_url
            # Keep this unrelated provider's key out of the Relay CLI environment.
            env.pop("OPENAI_API_KEY", None)
            command = ["npx", "--yes", RELAY_CLI, "--agent", "no", "--profile", "curate"]
            if args.command == "relay-login":
                # Relay requires the named profile to exist even when a token is in env.
                result = subprocess.run(
                    [*command, "auth", "login", "--with-token"],
                    input=settings.relay_agent_token.get_secret_value() + "\n",
                    text=True,
                    env=env,
                    check=False,
                )
            else:
                result = subprocess.run(
                    [*command, "listen", "--forward-to", "http://127.0.0.1:8000/webhooks/relay"],
                    env=env,
                    check=False,
                )
            raise SystemExit(result.returncode)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        status = getattr(error, "status_code", None)
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
        print(
            f"Check failed: {type(error).__name__} (HTTP status: {status}). "
            "Check credentials, API origin, network, billing, and model access.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
