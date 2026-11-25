# Architecture

```mermaid
flowchart LR
  subgraph Browser
    S[Student portal]
    C[Coordinator portal]
  end
  S & C -->|HTTPS| P[Caddy: static files, TLS, /api proxy]
  P --> A[FastAPI backend]
  A --> D[(PostgreSQL 16 + pgvector)]
  W[Worker] --> D
  A & W --> F[(Raw files volume)]
  A & W --> E[Local embeddings, ONNX]
  A & W --> L[LLMClient: cache, caps, retries, mock]
  L -. live mode only .-> X[Pollinations API]
```

One codebase, one database, four containers (`db`, `backend`, `worker`, `frontend`).

## Ingest

```mermaid
sequenceDiagram
  participant Co as Coordinator
  participant API as Backend
  participant DB as Postgres
  participant W as Worker
  Co->>API: form, pasted text, PDF or DOCX, CSV
  API->>API: hash, reject exact duplicates
  API->>DB: job (pending) + task, one transaction
  W->>DB: claim task (FOR UPDATE SKIP LOCKED)
  W->>W: extract text, parse to a strict schema, normalise
  alt review needed
    W->>DB: draft, with per-field confidence and likely duplicates
    Co->>API: edit and publish
  end
  W->>DB: embedding + tsv + status indexed, one transaction
  W->>DB: alerts for matching students
```

- Edits to a live posting re-embed and rewrite `tsv` in the same transaction as the row.
- Failed input is reported once with a plain reason. Unexpected errors are retried with backoff.
- A task whose worker died is claimed again after ten minutes.
- Archiving or expiring changes `status`, and search filters on it, so the posting is gone at once.

## Search (`app/search`)

1. Filters: live, deadline not passed, plus type, place, remote, pay, closing window.
2. Candidates: 50 nearest by cosine distance and 50 by full-text score. Each keyword is weighted by
   how rare it is, because Postgres ranking has no inverse document frequency.
3. Fusion: reciprocal rank fusion (or a weighted sum, by configuration).
4. Personal re-rank: search match, skill overlap, preference match, profile similarity, and a small
   urgency nudge. The full breakdown is returned and shown to the student.

All weights are in `app/search/weights.toml`. The module does not depend on the agent or the API.

## Agent (`app/agent`)

A short loop over the chat completions API: system prompt, memory, summary and recent messages, then
tool calls until `final_answer`. At most five steps and a token limit per turn.

Before an answer is shown, code checks that every posting id came from a tool result in that turn
and that nothing predicts selection. One repair attempt is allowed; after that the answer is built
from the tool results alone. Only then is it streamed.

Tools take the student from the session. Their schemas reject unknown arguments, so a model cannot
pass a user id. Write tools only create a pending action, which the student confirms.

## LLM client (`app/llm`)

Everything goes through `LLMClient`: mock mode by default, response cache by content hash, an atomic
"count then reserve" against daily, total and per-eval caps, at most two retries on network errors,
429 and 5xx, prompt size limits, and a log row per call. Over budget it answers from the cache or the
rule-based fallback and says so.

## Data

Vectors, text search and rows live in one Postgres database, so removing a posting or an account is
one transaction. Uploaded files sit behind a small storage interface with generated names.
