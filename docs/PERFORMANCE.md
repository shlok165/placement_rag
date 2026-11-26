# Performance

`make bench` seeds 1,000, 10,000 and 50,000 synthetic postings into a scratch database and measures
search, the vector index and ingest. The demo data is not touched and no LLM call is made. Tables
between the markers are written by `evals/bench.py`; the text around them is written by hand.

## Before the fix

The first full run (same machine, same day, same 500 queries) gave these search latencies:

| Postings | p50 | p95 | p99 | personalised p50 | p95 | p99 |
|---|---|---|---|---|---|---|
| 1,000 | 35 | 44 | 51 | 55 | 65 | 72 |
| 10,000 | 80 | 92 | 97 | 100 | 116 | 129 |
| 50,000 | 191 | 219 | 236 | 216 | 251 | 272 |

Latency grew with the corpus, which an index should prevent. The vector query ordered by
`embedding <=> query, id`; the second sort key means Postgres cannot read rows in order from the
HNSW index, so every search scanned and sorted every posting. The same run reported a recall of
1.000 for every HNSW setting, which was the same mistake: its "approximate" query had the same
shape and was exact too. Those recall numbers were wrong and are not shown.

The fix orders by distance alone and breaks ties in Python. The benchmark now forces the index
path for its recall measurements (`enable_sort = off`) and records whether the application's
own query is planned with the index.

## After the fix

<!-- bench:start -->
Run 2026-11-26 on AMD Ryzen 7 7840HS w/ Radeon 780M Graphics, 16 logical CPUs visible to Docker, 7.4 GB RAM in the Docker VM. PostgreSQL 16.16, pgvector 0.8.7. Mock mode, no LLM calls. 500 distinct queries per pass, each embedded once (embedding included in the latency).

### Search latency, POST /api/search in process (ms)

| Postings | p50 | p95 | p99 | personalised p50 | p95 | p99 |
|---|---|---|---|---|---|---|
| 1,000 | 36 | 44 | 51 | 57 | 72 | 87 |
| 10,000 | 49 | 62 | 68 | 72 | 85 | 93 |
| 50,000 | 100 | 132 | 153 | 130 | 167 | 184 |

Embedding one query takes about 5 ms of that. The application's vector query is planned with the HNSW index at 10,000, 50,000 postings; otherwise Postgres scans and sorts.

### Index build and size

| Postings | Table with indexes (MB) | GIN text index (MB) | HNSW m, ef_construction | Build (s) | HNSW size (MB) |
|---|---|---|---|---|---|
| 1,000 | 6 | 1.0 | 16, 64 | 0.2 | 2.0 |
| 1,000 | 6 | 1.0 | 32, 128 | 0.4 | 2.1 |
| 10,000 | 58 | 5.3 | 16, 64 | 2.3 | 19.5 |
| 10,000 | 58 | 5.3 | 32, 128 | 6.7 | 20.2 |
| 50,000 | 276 | 13.7 | 16, 64 | 16.2 | 97.7 |
| 50,000 | 276 | 13.7 | 32, 128 | 48.9 | 101.4 |

### HNSW recall against exact search (200 queries, top 10 and top 50)

Filtered: a location filter that keeps about one posting in nine, with iterative scans on.

| Postings | m, ef_construction | ef_search | recall@10 | recall@50 | filtered @10 | filtered @50 |
|---|---|---|---|---|---|---|
| 1,000 | 16, 64 | 40 | 0.997 | 0.989 | 0.995 | 0.999 |
| 1,000 | 16, 64 | 100 | 1.000 | 1.000 | 1.000 | 1.000 |
| 1,000 | 16, 64 | 200 | 1.000 | 1.000 | 1.000 | 1.000 |
| 1,000 | 32, 128 | 40 | 1.000 | 0.998 | 0.999 | 1.000 |
| 1,000 | 32, 128 | 100 | 1.000 | 1.000 | 1.000 | 1.000 |
| 1,000 | 32, 128 | 200 | 1.000 | 1.000 | 1.000 | 1.000 |
| 10,000 | 16, 64 | 40 | 0.978 | 0.953 | 0.979 | 0.988 |
| 10,000 | 16, 64 | 100 | 0.998 | 0.989 | 0.995 | 0.993 |
| 10,000 | 16, 64 | 200 | 1.000 | 0.998 | 0.998 | 0.996 |
| 10,000 | 32, 128 | 40 | 0.993 | 0.987 | 0.994 | 0.997 |
| 10,000 | 32, 128 | 100 | 1.000 | 0.997 | 0.998 | 0.998 |
| 10,000 | 32, 128 | 200 | 1.000 | 1.000 | 1.000 | 0.999 |
| 50,000 | 16, 64 | 40 | 0.903 | 0.873 | 0.922 | 0.949 |
| 50,000 | 16, 64 | 100 | 0.967 | 0.952 | 0.959 | 0.968 |
| 50,000 | 16, 64 | 200 | 0.989 | 0.983 | 0.983 | 0.982 |
| 50,000 | 32, 128 | 40 | 0.953 | 0.939 | 0.961 | 0.972 |
| 50,000 | 32, 128 | 100 | 0.992 | 0.988 | 0.992 | 0.991 |
| 50,000 | 32, 128 | 200 | 0.996 | 0.995 | 0.997 | 0.994 |

### Ingest throughput (mock parser, local embeddings, one worker)

| Postings | Submit (s) | Worker (s) | Postings per second | Live | Sent to review |
|---|---|---|---|---|---|
| 200 | 0.6 | 9.4 | 20.0 | 191 | 9 |
<!-- bench:end -->

## What the numbers say

- **The fix halved latency at 50,000 postings**: p50 from 191 to 100 ms, p99 from 236 to 153 ms,
  personalised p50 from 216 to 130 ms. At 1,000 postings nothing changed, because the planner still
  prefers a plain scan there, which is right for a table that small.
- **What is left at 50,000 is not broken down yet.** The likeliest next cost is keyword search: for
  every query term it counts how many postings contain it (for the rarity weight), and that count
  reads the whole table. This is a guess from the query shape, not a measurement. The personal
  re-rank adds about 30 ms (personalised against plain p50).
- **HNSW settings.** The application ships pgvector's defaults (`m = 16`, `ef_construction = 64`)
  and searches with `hnsw.ef_search = 200` and strict-order iterative scans. At 50,000 postings that
  keeps 98.9% of the exact top 10. `m = 32, ef_construction = 128` raises it to 99.6% but builds
  three times slower (49 s against 16 s); worth it only well beyond this scale. `ef_search = 40`
  loses a tenth of the exact top 10 at 50,000, which is why the application asks for 200.
- **Filters hold up.** With a location filter that keeps one posting in nine, iterative scans keep
  recall within a point of the unfiltered case.
- **Ingest** handles about 20 pasted postings a second on one worker in mock mode; embedding is most
  of that. 9 of the 200 went to review because the rule parser could not read every field.
- **Scale this is built for**: a few thousand postings a year at one institute. 50,000 is ten years
  of that and still answers in about a tenth of a second on a laptop.

Not measured: concurrent load, the cost of the proxy, and live-mode LLM latency.
