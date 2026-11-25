# Progress

## M0 Foundations

Compose stack (`db`, `backend`, `frontend`), initial migration with every table, health and metrics
endpoints, JSON logs, design tokens and base components, login page, CI skeleton. Verified from a
clean state: all services healthy and the login page is served.

## M1 Auth and roles

Email and password accounts (argon2), server-side sessions, CSRF tokens, login rate limiting,
institute email check, coordinator invites, route guards on both sides. One test walks every admin
route as a student (403) and as a visitor (401); another checks that every other route needs a
session.

## M2 Ingest and coordinator portal

Four ways in (form, paste, PDF or DOCX upload, CSV), a Postgres-backed queue with a worker
container, rules-based parsing in mock mode, review screen with low-confidence flags, exact and
fuzzy duplicate checks, nightly expiry, alerts, change history, undo. The LLM client (cache, budget
caps, retries, logging) is the only module that talks to the provider. Verified: a posting reaches
`indexed` with embedding and `tsv` set, failures show their reason and can be retried.

## M3 Retrieval and evals

Hybrid search (pgvector plus rarity-weighted full-text search, RRF), explainable personal re-rank,
156 synthetic postings, 77 labelled cases in three slices, weight sweeps on a development half.
`make eval` prints the tables and writes `docs/EVALS.md`. Hybrid beats both single methods on
nDCG@10 and recall@50 but not on hit@1; the reasons are written down there.

## M4 Student portal

Onboarding with progress and skips, resume reading with identifier removal and an exact view of what
is kept, search with filters, chips, saved and recent searches, explainable match, saves and tracking
with undo, board and list views, notifications, consent, data export and account deletion. Playwright
flows cover the coordinator and student journeys in mock mode.

## M5 Copilot

Hand-written agent loop over eleven validated tools, grounding and prediction checks before any text
is shown, streamed answers with a stop control, confirm cards for every change, long-term memory with
consent per fact, deterministic session summaries, daily quotas. The LLM client enforces caching,
caps, retries and logging. Agent, grounding and isolation tests pass in mock mode and the usage page
shows zero live calls.
