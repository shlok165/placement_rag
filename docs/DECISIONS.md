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
- **Forced tool choice where the model supports it.** The model list carries
  `supported_parameters`; the client reads it with the model check, once per process, and sends
  `tool_choice: "required"` (or the named `final_answer` function for a repair) only when
  `tool_choice` is listed. Otherwise it sends `auto`. Round 1 never forced it, and 12 of 37 live
  turns came back as plain text.
- **One repair for plain text, then code.** A grounded plain-text reply gets one request to resend
  it through `final_answer`. If it is still plain text, code wraps it after the same grounding and
  prediction checks. Broken JSON is never shown as prose. Each stored answer records
  `answer_kind`: `structured`, `repaired` or `fallback`. Repair calls are logged in `llm_calls`
  with the purpose `agent_repair`.
- **The cache key includes a forced tool choice** but not the default, so earlier cached answers
  still match.

## Behaviour signals

- **Events carry no text.** `interaction_events` holds a user, a posting, a kind and a time. They
  are deleted with the account and listed in the data export.
- **The server records what it can see.** Saves and opens are written where they happen, so a save
  confirmed in the copilot counts like one on a card. The browser reports only impressions and
  apply clicks. "More like this" and "Fewer like this" have their own endpoint, which can also
  clear them.
- **Undoing a save removes its event,** so the taste vector follows what the student keeps.
- **Taste weight 0.10 was set before measuring.** It equals the profile weight. The offline
  simulation reports a sensitivity table but the weight was not chosen from it.
- **No events means no feature.** Without a positive event there is no taste vector and no taste
  component, so the score is computed by exactly the same code path as before. A test checks this.

## Outreach drafts

- **The model writes the draft; code checks it.** `draft_outreach` returns the facts a draft may
  use. The draft comes back in `final_answer.draft` and must pass a deterministic check: every
  skill, organisation, project name and number has to come from the profile or the posting, and a
  first-person claim of a skill has to be in the profile. Aspirations ("keen to learn") are not
  claims.
- **Never an unchecked draft.** A failed draft gets one repair request. If it fails again, the
  student sees a template draft built only from the facts. A draft written into the answer text
  instead of the draft field is checked the same way.
- **Pattern matching, not another model call.** The check costs nothing, is the same every time
  and can be tested with planted fabrications. It can miss an invented claim phrased without a
  name, a number or a known skill ("I am a great leader").
- **Nothing is sent.** The draft is shown in an editable box with a copy button.

## Evals

- **One live run only.** Later changes were not measured live, to respect the call budget.
- **Isolated corpus.** CLI evals run in a separate database built from the synthetic dataset with a
  fixed reference date, so numbers are reproducible and never mix with demo data.
- **The blind set has its own corpus.** Its 104 postings are evaluated in a fresh database, not
  mixed into the main 156, so its numbers do not depend on the main set at all. It reuses the
  student profiles, because those describe students rather than postings.
- **Once per release is enforced by a log.** `evals/blind/runs.jsonl` is committed; the script
  refuses a second run for a release unless `--force` is given, and any forced run stays visible
  in the log.
- **Paired bootstrap for differences.** Configurations are compared case by case. Two separate
  intervals overlap far more often than the paired difference crosses zero.
- **Cross-encoder kept as an off switch.** It lost on the development half, so it is off. The
  switch stays so the blind run can record it and so the result can be reproduced.
