# Build plan

placement_rag is built in nine milestones. Each one ends with tests, a clean
`docker compose up --build`, an entry in [PROGRESS.md](PROGRESS.md) and a commit.

| Milestone | Outcome | Accepted when |
|---|---|---|
| M0 Foundations | Compose stack, migrations, health endpoints, CI, design system | Login page loads and `/readyz` is healthy |
| M1 Auth and roles | Sessions, CSRF, role guards, seed users | Students get 403 on admin routes, with tests |
| M2 Ingest and admin portal | Form, paste, upload and CSV intake, worker queue, review, dedupe, expiry | A posting reaches `indexed`; failures are visible and retryable |
| M3 Retrieval and evals | Hybrid search, personalised re-rank, synthetic dataset, harness | `make eval` prints a real comparison table |
| M4 Student portal | Onboarding, resume parsing with redaction, search, tracker, alerts | Full student journey passes end to end in mock mode |
| M5 Copilot | LLM client with guardrails, agent loop, tools, memory, chat UI | Agent and grounding tests pass in mock mode |
| M6 Agent evals | Offline suite, judge, capped live run | `docs/EVALS.md` labels live and mock numbers |
| M7 HCI polish | Accessibility, responsive pass, tour, palette, SUS | axe passes; keyboard walkthrough works |
| M8 Production and docs | Prod compose, backups, README, push | Fresh clone works in three commands |

## Assumptions

- One institute, one database, one deployment. Horizontal scale is out of scope.
- The corpus is hundreds to a few thousand postings, so HNSW in Postgres is enough and a separate
  vector store would only add moving parts.
- Coordinators are trusted staff; student resumes are the sensitive data in the system.
- Mock mode must be a complete product, because it is what CI, tests and a fresh clone run.

## Order of work inside a milestone

1. Schema and domain logic, with tests.
2. API routes, with role and ownership tests.
3. UI on top of the design system.
4. Clean-state compose run, docs, commit.
