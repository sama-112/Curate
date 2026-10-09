# Curate — local Milestone 1

Curate is an AI personal stylist inside Relay. This milestone implements a direct text
message → OpenAI Responses API → Relay reply, with a local FastAPI server. There is no
deployment. Native controls, Supabase, photos, video, voice, and try-on are later milestones.

**Verification status:** offline tests pass. A live GPT call and a real Relay round trip
have not been verified: no OpenAI key or Relay Agent Token is configured in this project.
`/readyz` reports local configuration and worker health; it does not verify provider access.

## Setup

Use Python 3.12+ and Node.js 22.22.3+ (Node runs Relay's development CLI only).
The existing `.venv` was created with Python 3.12.14 from the Codex bundled runtime.

```bash
cd /Users/daudkhan/Desktop/Curate
source .venv/bin/activate
python -m pip install -r requirements.lock
cp -n .env.example .env
chmod 600 .env
```

For a fresh checkout, create the environment before those commands:

```bash
python3.12 -m venv .venv
```

On this computer, if `python3.12` is unavailable, the verified interpreter is:

```bash
/Users/daudkhan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m venv .venv
```

Edit `.env` locally:

- `OPENAI_API_KEY`: an API key from [OpenAI's API dashboard](https://platform.openai.com/api-keys),
  with billing and access to the configured model. ChatGPT/Codex sign-in is separate.
- `OPENAI_TEXT_MODEL`: defaults to `gpt-6-luna`, verified in the
  [official model reference](https://developers.openai.com/api/docs/models/gpt-6-luna)
  on October 7, 2026. Change it to another supported Responses model if needed.
- `RELAY_AGENT_TOKEN`: the token for the Curate agent you intend to message.
- `RELAY_API_URL`: the issuing API origin, default `https://api.relayapp.im`, without `/v1`.
- `RELAY_WEBHOOK_SECRET`: obtain this in the local forwarding step below.

Keep `.env` out of Git and never paste keys into chat. Environment variables override `.env`.
Supabase credentials are not needed in Milestone 1.

## Get a Relay Agent Token

Reuse an existing Curate agent if you have one. Its token must match its API environment.
For a new agent, follow [Relay's agent creation guide](https://docs.relayapp.im/agents/create-agent):

```bash
npx --yes relaymessenger@0.1.22 agents create
```

Complete browser sign-in and the prompted agent details. Keep the returned handle, profile,
and share link. Do not create another agent after an uncertain timeout; inspect Relay Console.
To load the saved token without showing it on screen, substitute the returned profile:

```bash
export RELAY_AGENT_TOKEN="$(npx --yes relaymessenger@0.1.22 auth token --profile YOUR_PROFILE)"
```

This environment variable is enough for that terminal. To populate `.env`, transfer the
saved credential locally without printing it. Relay Console's **Rotate token** also shows
a new token once, but invalidates existing tokens; use that only intentionally.

## Start the local Relay connection

In terminal A, activate `.venv` and run:

```bash
cd /Users/daudkhan/Desktop/Curate
source .venv/bin/activate
python -m curate.dev check-relay
python -m curate.dev openai-smoke
python -m curate.dev relay-login
python -m curate.dev relay
```

`check-relay` makes the documented read-only `GET /v1/chats?limit=1`. An empty chat list
is a successful authentication check. `openai-smoke` makes one billable GPT request and
prints the actual answer; it does not send a Relay message.

`relay-login` imports the existing token into the dedicated `curate` CLI profile through
stdin and saves it privately in Relay's local configuration. It creates no new agent.
This step is required once, even when the token comes from `.env`; Relay requires an
existing named profile. Re-run it when intentionally changing the token or API origin.

The `relay` helper loads `.env` and invokes this documented command with the Agent Token
in its environment, never in command arguments:

```bash
npx --yes relaymessenger@0.1.22 --agent no --profile curate listen --forward-to http://127.0.0.1:8000/webhooks/relay
```

Copy the printed **Local signing secret** to `RELAY_WEBHOOK_SECRET` in `.env`. Leave terminal
A running. Treat that secret as private. The listener may exit if an event arrives before
the backend is ready; restart `python -m curate.dev relay` after starting the server.

Relay's [local forwarding integration](https://docs.relayapp.im/integrations/your-own-backend)
uses an outbound connection and signed local POSTs. No public callback, ngrok, or saved public
webhook subscription is required. Run only one consumer for this agent: another runtime or
listener can take its events. Existing subscriptions are left unchanged.

In terminal B:

```bash
cd /Users/daudkhan/Desktop/Curate
source .venv/bin/activate
python -m uvicorn curate.main:app --host 127.0.0.1 --port 8000
```

Use one worker. Restart the server after changing `.env`; changes are not loaded live.
No `--reload` is used so queued processing is not interrupted by file edits.

## Manually verify through Relay

1. Check the local endpoints:

   ```bash
   curl -i http://127.0.0.1:8000/healthz
   curl -i http://127.0.0.1:8000/readyz
   ```

   Expect `200`, `configured: true`, and `worker_running: true`. Missing configuration
   returns `503` and names the missing variables without revealing their values.
2. Open your agent's share link/handle in the Relay app. Use a direct chat from your personal
   account. Send: “I own a navy shirt, beige chinos, and white sneakers. Suggest one outfit
   and explain why it works.”
3. Confirm terminal A logs the forwarded `message.received`. Terminal B should log
   `event_accepted`, then `reply_delivered ... source=openai` for the same event ID.
4. Confirm the generated advice appears in that same Relay chat. This is the required live
   proof; authentication checks, a `204`, or an offline mock test alone do not establish it.
5. Send a second text question. Each message is independent in Milestone 1; repeat relevant
   context. Conversation memory and persistent preferences are not implemented yet.

If generation exhausts retries, Curate sends an honest error message and logs
`source=error`; that is not a successful GPT verification. Attachments receive a text-only
explanation. Group chats, messages from other agents, own messages, and unrelated events
are ignored. Native interactions are reserved for Milestone 2.

Stop with **Ctrl-C in both terminals**, then `deactivate`. Pending accepted events remain
in `.runtime/inbox.sqlite3` and resume when the backend restarts. Keep that journal to
preserve deduplication. It contains private message text and replies; do not share or commit it.
Permanently failed sends remain `failed` and appear in `/readyz` counts. Resolve the logged
provider/configuration issue and send a new message; there is no automatic replay of failed rows.

## Tests

```bash
python -m pytest -q
python -m ruff check curate tests
python -m ruff format --check curate tests
```

The tests use signed fixtures, mock HTTP transports, and temporary SQLite files. They make
no provider calls. They cover signature/timestamp/body validation, fast acknowledgement,
duplicate events, restart recovery, exact Responses/Relay request shapes, user routing,
attachment fallback, and error/retry behavior. The installed Starlette version emits one
test-client deprecation warning for HTTPX; it does not fail the tests.

## Files and scope

- `curate/main.py`: FastAPI endpoints and application lifecycle.
- `curate/adapters/relay.py`: Relay schemas, normalization, text rendering, REST sends.
- `curate/integrations/openai.py`: one stylist using the official asynchronous OpenAI SDK.
- `curate/domain.py`: interface-independent validated messages and replies.
- `curate/inbox.py`, `curate/worker.py`: durable local transport journal and background worker.
- `curate/config.py`, `curate/dev.py`: environment settings and setup/verification commands.
- `tests/`: focused offline unit and integration coverage.
- `.env.example`, `.gitignore`, `pyproject.toml`, `requirements.lock`: setup and pinned dependencies.
- `PLAN.md`, `ARCHITECTURE.md`: milestone status and boundaries.

The starting folder was empty. Git currently resolves to `~/Desktop`, whose remote is an
unrelated repository. No parent changes were modified or committed. Before publishing code,
give Curate its own Git repository/remote and review only Curate files.

Official integration references: [message.received](https://docs.relayapp.im/events/message-received),
[signature verification](https://docs.relayapp.im/webhooks/verify-signatures),
[durable acknowledgement](https://docs.relayapp.im/webhooks),
[idempotency](https://docs.relayapp.im/live/idempotency),
[message sends](https://docs.relayapp.im/messages/send),
[local CLI forwarding](https://docs.relayapp.im/cli/reference/listen),
[OpenAI Python SDK](https://developers.openai.com/api/reference/python).
