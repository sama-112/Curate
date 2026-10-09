# Curate milestone plan

## Milestone 1 — implemented locally; live verification pending

- [x] Read the complete product specification; limit implementation to Milestone 1.
- [x] Inspect the folder and Git status: empty project; unrelated dirty parent repository.
- [x] Verify official Relay transport, event schema, signatures, sends, and idempotency.
- [x] Verify OpenAI Responses API and configurable `gpt-6-luna` identifier.
- [x] Create modular Python 3.12 FastAPI app and local virtual environment.
- [x] Implement signed direct text intake and outgoing Relay REST messages.
- [x] Configure official OpenAI SDK, timeout/retries, and one stylist prompt.
- [x] Commit events before acknowledging; process outside the request handler.
- [x] Test deduplication, cached reply recovery, failures, and user routing.
- [x] Add setup commands, dependency lock, environment example, architecture, and tests.
- [ ] Configure OpenAI API key, matching Relay Agent Token/API origin, and local signing secret.
- [ ] Run successful live `check-relay` and `openai-smoke` checks.
- [ ] Observe a real personal Relay message → GPT → reply in the same chat.

The backend and CLI can be installed/run locally. No provider credentials were present
during implementation, so live API success and the end-to-end connection remain unverified.
Local configuration readiness and mock tests are not substitutes for the last three checks.
Complete them using README.md before marking Milestone 1 done.

Validation on October 7, 2026:

- `python -m pytest -q`: **35 passed**, one Starlette HTTPX test-client deprecation warning.
- `ruff check curate tests` and `ruff format --check curate tests`: **passed**.
- `python -m pip check`: **passed**, no broken dependencies.
- Actual Uvicorn startup on loopback, tested on port 18765: **passed**; clean Ctrl-C shutdown.
- Actual HTTP `GET /healthz`: **200**. `GET /readyz` and `POST /webhooks/relay`:
  **503 as expected** with missing credentials; no events accepted.
- Official Relay CLI **0.1.22** version and `listen`/`auth login` help: **verified**.
  Confirmed the CLI's local POST signature and acknowledgement behavior in its installed code.
- `check-relay` and `openai-smoke`: **blocked before network calls** by absent credentials.
- Confirmed `.env`, `.venv`, and `.runtime` are ignored by Git; `.env` has mode 600.

The first test run found a harness thread-access error when tests queried the server's
SQLite connection directly. Tests now inspect the HTTP status endpoint; the application's
single-thread connection constraint remains intact. No code was committed into the
unrelated parent repository. No deployment configuration or future milestone features
were created.

## Remaining milestones — do not start automatically

| Milestone | Scope | Status |
| --- | --- | --- |
| 2 | Reusable Relay buttons, cards/carousels, selections, forms, task activity | Not started |
| 3 | Supabase schema, internal user mapping, scoped persistent wardrobe CRUD | Not started |
| 4 | Reference photo consent, validation, private storage, replace/delete | Not started |
| 5 | Closet video intake, frames, vision, deduplication, confirmed wardrobe review | Not started |
| 6 | Styling consultation and three personalized style pathways | Not started |
| 7 | Personal photo image editing, outfit visualizations, conversational changes | Not started |
| 8 | Specific wardrobe additions with reasons and outfit compatibility | Not started |
| 9 | Unified text/photo/voice garment additions | Not started |
| 10 | Persistent explicit/inferred preferences and outfit feedback | Not started |
| 11 | Full local integration demonstration, isolation and failure recovery | Not started |

Preserve one primary stylist, Relay-independent core services, private media, deterministic
interaction actions, and one milestone at a time. Verify current image/transcription APIs
and configurable model identifiers from official OpenAI docs when their milestones begin.
There is no deployment milestone.
