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
