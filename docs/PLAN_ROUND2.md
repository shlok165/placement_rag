# Plan, round 2

Goal: make the project measurably better without breaking what works. Each item is one commit with
its tests and docs. Everything runs in mock mode except one capped live agent run at the end.

## Order

1. **Structured answers (1.1).** Require a tool call (`tool_choice`) when the model list says the
   model supports it, ask once for the structured form when a reply is plain text, and wrap
   anything left by code after the same checks. Every answer records how it was produced.
2. **Retrieval evaluation (1.2).** A blind set from a separate generator seed, never used for
   tuning; bootstrap 95% intervals; a messy-text slice; a cross-encoder experiment kept only if it
   helps.
3. **Scale (1.5).** `make bench` at 1k, 10k and 50k postings in a scratch database: search
   latency, HNSW recall against exact search for two settings, index size and build time, ingest
   throughput. Results in `docs/PERFORMANCE.md`.
4. **Behaviour signals (1.3).** Events table and endpoint, a decayed taste vector, one more
   re-rank feature with its own weight, a leave-one-out simulation, and an exact cold-start test.
5. **Outreach drafts (1.4).** `draft_outreach` tool, a deterministic fabrication check, a copyable
   and editable draft in the chat, a template mock path and eight eval cases.
6. **Tier 2.** Security follow-ups, frontend tests with a coverage threshold, supply-chain checks,
   then filter chips, calendar export and the trace viewer, then the deployment guide and release.
7. **Docs pass**, then **the live run**, then tier 3 if time allows, then the final checks.

## Rules kept from round 1

Mock mode is the committed default and the only mode in tests and CI. Numbers in the docs come from
scripts in the repo. A change that does not help is reported and reverted.
