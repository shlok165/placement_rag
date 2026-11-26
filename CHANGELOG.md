# Changelog

## 1.0.0 (2026-11-26)

### Added

- Behaviour events (impressions, opens, saves, apply clicks, "more or fewer like this") and a
  decayed taste vector as one more transparent ranking feature. It is switchable and does nothing
  for a student without events.
- `draft_outreach`: recruiter notes and resume advice built from the profile and the posting, a
  deterministic fabrication check, and an editable, copyable draft box. Nothing is sent.
- Filters read from typed words ("remote ML internship in Pune, above 30k"), confirmed as chips.
- Deadline calendar: an .ics download and a private feed link that can be replaced or turned off.
- Agent trace viewer for coordinators: own turns and turns students chose to share, with tools,
  timings, checks and cache hits. Opening a shared trace is audited.
- Blind retrieval set, bootstrap confidence intervals, paired comparisons, a messy-text slice and
  a cross-encoder experiment (kept off).
- `make bench`: latency, HNSW recall, index size and ingest throughput at 1k, 10k and 50k postings.
- Deployment guide, component tests with a coverage floor, pip-audit, npm audit, Trivy and
  Dependabot.

### Changed

- The agent requires a tool call when the model supports `tool_choice`, asks once for the
  structured form, and otherwise builds the answer by code after the same checks. Live structured
  output rose from 68% to 89%.
- Sign-in uses a progressive delay per account and address pair instead of a per-account lockout.
- Registration no longer says that an account exists, and takes the same time either way.
- `X-Forwarded-For` is believed only from `TRUSTED_PROXIES`.
- Caddy is rebuilt with a patched `golang.org/x/net`.

### Fixed

- Vector search never used its HNSW index, because a second sort key blocked it. p50 latency at
  50,000 postings fell from 191 to 100 ms.

## 0.1.0

First complete version: two portals, hybrid search with explainable ranking, a grounded agent with
eleven tools, budgeted LLM client with mock mode, evals, Docker Compose and CI.
