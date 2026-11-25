# Decisions

Short records of choices made while building.

## Provider check (done before coding)

Checked against the live OpenAPI document (`/openapi.json`, version 0.3.0) and `GET /v1/models`.

- Base URL, `POST /v1/chat/completions`, `Authorization: Bearer` and the model list match the spec.
- `GET /v1/models` needs no key. Entries have an `id` and `aliases`; either is a valid model name, so
  the startup check accepts both.
- `402` means the balance or the key's budget is used up. It is treated as a budget error and is
  never retried. `429` carries a JSON error and may carry `Retry-After`, which is honoured.
- Identical requests may be answered from a provider-side shared cache. This is one more reason
  resume text is redacted before any call.

## Configuration

- **Environment aliases.** `LLM_API_KEY`, `LLM_MODEL` and `LLM_BASE_URL` also accept
  `POLLINATIONS_API_KEY`, `POLLINATIONS_MODEL` and `POLLINATIONS_BASE_URL`. A base URL with or
  without a trailing `/v1` works.
- **Mock is the default everywhere.** Live mode needs both `LLM_MODE=live` and a key.
- **Model names are never hardcoded.** The live client checks the configured name against the model
  list once per process and fails with a clear message if it is missing.

## Backend

- **Synchronous SQLAlchemy.** Routes run in the FastAPI thread pool. It keeps the code simple, and
  Postgres is the bottleneck at this scale, not the event loop.
- **Server-side sessions, not JWT.** Opaque token in an HTTP-only cookie, hash stored in
  `user_sessions`, plus a per-session CSRF token. Logout and deactivation take effect at once.
- **Extra tables.** Needed beyond the initial model: `user_sessions`, `login_attempts`, `invites`,
  `saved_searches`, `search_events`, `job_views`, `resume_files`, `pending_actions`,
  `message_feedback`, `app_feedback`, `sus_responses`, `announcements`, `scheduled_runs`.
- **Extra job columns.** `duration_months` (preferences mention duration), `raw_text`,
  `parse_meta` (confidence and errors), `duplicate_of_id`, `auto_publish`, `published_at`.
- **Content hash** covers what was submitted (normalised text, or the fields for a form). The unique
  constraint blocks exact resubmission; near-duplicates are found by fuzzy match and flagged.
- **`tsv` is written by the application**, in the same transaction as the row, because
  `array_to_string` is not immutable and cannot be used in a generated column.

## Search

- **Keyword queries are OR-ed.** `websearch_to_tsquery` requires every term, which returns nothing
  for natural questions. Any term may match.
- **Search analytics are anonymous.** `search_events` stores the query and result counts with no
  user id. Recent searches live only in the browser.
- **Rarity-weighted keywords.** Full-text terms are scored one by one and weighted by how few
  postings contain them, in place of a hand-kept list of words to ignore.

## Frontend

- **Filters live in the address bar,** so a search can be bookmarked, shared and reloaded.
- **Scroll containers are focusable regions,** so they can be scrolled with the keyboard.
- **Dragging is pointer only.** Every card carries a stage list, which is the accessible way to move
  it, so drag-and-drop stays an extra.
- **`lucide-react`, `sonner` and `cmdk`** are used as in shadcn/ui. Components follow shadcn/ui
  patterns over Radix and are grouped into a few files.

## Agent

- **The answer is a tool call.** The model finishes a turn by calling `final_answer`, so the
  structured output is validated by Pydantic exactly like any other tool.
- **Verify, then stream.** Progress events stream while tools run. Answer text is released to the
  browser only after the grounding check passes, so an invented job is never shown and then
  retracted. The cost is a slower first word.
- **Session summaries are deterministic.** Older turns are condensed without an LLM call, which
  saves budget and keeps tests stable.
- **Memory proposals are pending actions.** A remembered fact uses the same confirm card as saving
  a job, so there is one consent pattern to learn.
- **Over budget means mock, with a notice.** When a cap is hit the agent falls back to the
  rule-based assistant, which is still grounded in real postings, and the UI says so.
- **No forced tool choice.** Providers differ in support for it, so the loop accepts a plain-text
  reply, runs the same checks and records that it was not structured.

## Evals

- **One live run only.** Later changes were not measured live, to respect the call budget.
- **Isolated corpus.** CLI evals run in a separate database built from the synthetic dataset with a
  fixed reference date, so numbers are reproducible and never mix with demo data.
