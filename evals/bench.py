"""Scale benchmark. `make bench`, or `python -m evals.bench --sizes 1000,10000,50000`.

Everything runs in scratch databases, so the demo data is never touched, and in mock mode, so no
LLM call is made. It measures:

- POST /api/search through the real FastAPI app (in process, no proxy), with and without
  personalisation, over distinct queries, so each query is embedded once per pass;
- HNSW recall against exact search, for two index settings and three `hnsw.ef_search` values,
  with no filter and with a selective location filter;
- index build time and size;
- ingest throughput: pasted postings through the worker (mock parser, local embeddings).

Embeddings of the seeded postings are cached in `evals/.cache/`, so repeat runs skip that step.
"""

import argparse
import math
import os
import random
import statistics
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

BENCH_DB = "placement_bench"
INGEST_DB = "placement_bench_ingest"
BENCH_SEED = 20261127
HNSW_SETTINGS = ((16, 64), (32, 128))
EF_SEARCH = (40, 100, 200)
RECALL_QUERIES = 200
INGEST_POSTINGS = 200
CACHE = Path(__file__).with_name(".cache")
PERFORMANCE_DOC = Path("/srv/docs/PERFORMANCE.md")
PASSWORD = "bench-only-password-1"


def _reset() -> None:
    """Forget cached settings and connections after DATABASE_URL changes."""
    from app.core.config import get_settings
    from app.db.session import get_engine, get_sessionmaker
    from app.llm.client import get_llm

    if get_engine.cache_info().currsize:
        get_engine().dispose()
    for cached in (get_settings, get_engine, get_sessionmaker, get_llm):
        cached.cache_clear()


@contextmanager
def database(name: str) -> Iterator[None]:
    from evals.evaldb import scratch_database

    original = os.environ.get("DATABASE_URL")
    with scratch_database(name) as url:
        os.environ["DATABASE_URL"] = url
        _reset()
        try:
            yield
        finally:
            _reset()
            if original is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original


def session() -> Session:
    from app.db.session import get_sessionmaker

    return get_sessionmaker()()


# ---------------------------------------------------------------- data


def synthetic(count: int, seed: int, today: date) -> list[Any]:
    from evals.dataset import FAMILIES, Variant, generate_jobs

    per = math.ceil(count / len(FAMILIES))
    rows = generate_jobs(today, Variant(seed=seed, per_family=per, prefix=f"bench{seed}:"))
    random.Random(seed).shuffle(rows)
    return rows[:count]


def as_jobs(rows: list[Any]) -> list[Any]:
    from app.db.models import Job, JobStatus
    from app.ingest.duplicates import hash_text

    return [
        Job(
            **row.fields,
            source="seed",
            content_hash=hash_text(f"synthetic posting {row.key}"),
            status=JobStatus.draft,
        )
        for row in rows
    ]


def vectors_for(jobs: list[Any], tag: str) -> tuple[np.ndarray, float | None]:
    """Passage embeddings, from the cache when present. Returns (vectors, passages per second)."""
    from app.core.config import get_settings
    from app.embeddings import embed_passages
    from app.ingest.indexing import job_passage

    CACHE.mkdir(exist_ok=True)
    model = get_settings().embedding_model.replace("/", "_")
    path = CACHE / f"bench-{tag}-{len(jobs)}-{model}.npy"
    if path.exists():
        return np.load(path), None
    started = time.perf_counter()
    vectors = np.asarray(embed_passages([job_passage(j) for j in jobs]), dtype=np.float32)
    rate = len(jobs) / (time.perf_counter() - started)
    np.save(path, vectors)
    return vectors, rate


def queries(count: int) -> list[str]:
    """Distinct, deterministic queries built from the main set's wording (never the blind set)."""
    from evals.cases import CONSTRAINT, PERSONAL, TOPIC
    from evals.dataset import CITIES, FAMILIES

    pool: list[str] = [q for q, *_ in TOPIC + CONSTRAINT] + [q for q, *_ in PERSONAL]
    for family in FAMILIES:
        pool += [" ".join(family.core).lower(), *(w.rstrip(".").lower() for w in family.work)]
        for title in family.titles:
            base = title.replace(" Intern", "").lower()
            pool += [base, f"{base} internship", f"remote {base}"]
            pool += [f"{base} in {city}" for city in CITIES[:3]]
    unique = list(dict.fromkeys(pool))
    random.Random(BENCH_SEED).shuffle(unique)
    if len(unique) < count:
        raise ValueError(f"Only {len(unique)} distinct queries are available.")
    return unique[:count]


# ---------------------------------------------------------------- index


def build_hnsw(db: Session, m: int, ef_construction: int) -> tuple[float, int]:
    db.execute(text("DROP INDEX IF EXISTS ix_jobs_embedding"))
    # Serial build: parallel builds need more shared memory than Docker gives by default.
    db.execute(text("SET max_parallel_maintenance_workers = 0"))
    db.execute(text("SET maintenance_work_mem = '512MB'"))
    started = time.perf_counter()
    db.execute(
        text(
            "CREATE INDEX ix_jobs_embedding ON jobs USING hnsw (embedding vector_cosine_ops) "
            f"WITH (m = {int(m)}, ef_construction = {int(ef_construction)})"
        )
    )
    db.commit()
    seconds = time.perf_counter() - started
    size = db.scalar(text("SELECT pg_relation_size('ix_jobs_embedding')")) or 0
    return seconds, int(size)


def nearest(
    db: Session, vector: list[float], location: str | None, exact: bool, ef: int
) -> list[int]:
    """The application's vector query, forced through HNSW (approximate) or a full sort (exact).

    With sorting turned off the only way to return rows in distance order is the HNSW index, so
    the approximate pass really measures the index, even on small tables.
    """
    if exact:
        db.execute(text("SET LOCAL enable_indexscan = off"))
    else:
        db.execute(text("SET LOCAL enable_sort = off"))
        db.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef)}"))
        db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    sql, params = _vector_sql(vector, location)
    rows = db.execute(text(sql), params).all()
    db.rollback()
    return [r.id for r in rows]


def _vector_sql(vector: list[float], location: str | None) -> tuple[str, dict[str, Any]]:
    where = "status = 'indexed' AND embedding IS NOT NULL"
    params: dict[str, Any] = {"v": str(vector)}
    if location:
        where += " AND lower(location) = :loc"
        params["loc"] = location.lower()
    sql = f"SELECT id FROM jobs WHERE {where} ORDER BY embedding <=> CAST(:v AS vector) LIMIT 50"
    return sql, params


def app_plan_uses_hnsw(db: Session, vector: list[float]) -> bool:
    """Whether the planner picks the index for the application's query, with nothing forced."""
    db.execute(text("SET LOCAL hnsw.ef_search = 200"))
    db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    sql, params = _vector_sql(vector, None)
    plan = "\n".join(r[0] for r in db.execute(text(f"EXPLAIN {sql}"), params).all())
    db.rollback()
    return "ix_jobs_embedding" in plan


def recall(
    db: Session, vectors: list[list[float]], exact: dict[str, list[list[int]]], ef: int
) -> dict[str, float]:
    out: dict[str, float] = {}
    for label, location in (("all", None), ("filtered", "Chandigarh")):
        found10 = found50 = 0
        for vector, truth in zip(vectors, exact[label], strict=True):
            approx = nearest(db, vector, location, False, ef)
            found10 += len(set(approx[:10]) & set(truth[:10])) / max(1, min(10, len(truth)))
            found50 += len(set(approx) & set(truth)) / max(1, len(truth))
        out[f"{label}@10"] = found10 / len(vectors)
        out[f"{label}@50"] = found50 / len(vectors)
    return out


# ---------------------------------------------------------------- search latency


def percentiles(samples: list[float]) -> dict[str, float]:
    cuts = statistics.quantiles(samples, n=100, method="inclusive")
    return {"p50": cuts[49], "p95": cuts[94], "p99": cuts[98], "mean": statistics.fmean(samples)}


def client_for_student() -> Any:
    from fastapi.testclient import TestClient

    from app.core.security import CSRF_COOKIE, hash_password
    from app.db.models import Role, StudentProfile, User
    from app.main import app
    from app.search.profiles import refresh_embedding
    from evals.cases import PROFILES

    with session() as db:
        user = User(
            email="bench@iitrpr.ac.in",
            password_hash=hash_password(PASSWORD),
            full_name="Bench Student",
            role=Role.student,
        )
        spec = PROFILES["software"]
        user.profile = StudentProfile(skills=spec["skills"], preferences=spec["preferences"])
        refresh_embedding(user.profile)
        db.add(user)
        db.commit()
    client = TestClient(app)
    reply = client.post(
        "/api/auth/login", json={"email": "bench@iitrpr.ac.in", "password": PASSWORD}
    )
    reply.raise_for_status()
    client.headers["X-CSRF-Token"] = client.cookies[CSRF_COOKIE]
    return client


def latency(client: Any, texts: list[str], personalize: bool) -> dict[str, float]:
    from app.embeddings import _embed_query_cached

    _embed_query_cached.cache_clear()
    for warm in ("warm up one", "warm up two", "warm up three"):
        client.post("/api/search", json={"query": warm, "personalize": personalize})
    samples = []
    for query in texts:
        started = time.perf_counter()
        reply = client.post("/api/search", json={"query": query, "personalize": personalize})
        samples.append((time.perf_counter() - started) * 1000)
        reply.raise_for_status()
    return percentiles(samples)


def embedding_ms(texts: list[str]) -> float:
    from app.embeddings import _embed_query_cached, embed_query

    _embed_query_cached.cache_clear()
    started = time.perf_counter()
    for query in texts:
        embed_query(query)
    _embed_query_cached.cache_clear()
    return (time.perf_counter() - started) * 1000 / len(texts)


# ---------------------------------------------------------------- runs


def insert(db: Session, jobs: list[Any], vectors: np.ndarray) -> float:
    from app.ingest.indexing import index_job

    started = time.perf_counter()
    for start in range(0, len(jobs), 2000):
        batch = jobs[start : start + 2000]
        for job, vector in zip(batch, vectors[start : start + 2000], strict=True):
            index_job(job, vector=vector.tolist())
        db.add_all(batch)
        db.commit()
    return time.perf_counter() - started


def run_search_bench(
    sizes: list[int], query_count: int, log: Callable[[str], None]
) -> list[dict[str, Any]]:
    from app.embeddings import embed_query

    today = datetime.now(UTC).date()
    rows = synthetic(max(sizes), BENCH_SEED, today)
    jobs = as_jobs(rows)
    vectors, embed_rate = vectors_for(jobs, "search")
    if embed_rate:
        log(f"embedded {len(jobs)} postings at {embed_rate:.0f} per second")
    texts = queries(query_count)
    probe = [embed_query(q) for q in texts[:RECALL_QUERIES]]
    query_ms = embedding_ms(texts[:100])
    results = []
    with database(BENCH_DB):
        client = client_for_student()
        done = 0
        with session() as db:
            db.execute(text("DROP INDEX IF EXISTS ix_jobs_embedding"))
            db.commit()
        for size in sizes:
            with session() as db:
                insert_s = insert(db, jobs[done:size], vectors[done:size])
                done = size
                db.execute(text("ANALYZE jobs"))
                db.commit()
                exact = {
                    "all": [nearest(db, v, None, True, 0) for v in probe],
                    "filtered": [nearest(db, v, "Chandigarh", True, 0) for v in probe],
                }
                settings = []
                for m, efc in HNSW_SETTINGS:
                    build_s, index_bytes = build_hnsw(db, m, efc)
                    by_ef = {ef: recall(db, probe, exact, ef) for ef in EF_SEARCH}
                    settings.append(
                        {
                            "m": m,
                            "ef_construction": efc,
                            "build_s": build_s,
                            "index_mb": index_bytes / 2**20,
                            "recall": by_ef,
                        }
                    )
                    log(f"{size}: m={m} efc={efc} built in {build_s:.1f}s")
                # Latency is measured with the index the application ships: pgvector's defaults.
                build_hnsw(db, *HNSW_SETTINGS[0])
                db.execute(text("ANALYZE jobs"))
                db.commit()
                sizes_mb = {
                    "table_mb": (db.scalar(text("SELECT pg_total_relation_size('jobs')")) or 0)
                    / 2**20,
                    "gin_mb": (db.scalar(text("SELECT pg_relation_size('ix_jobs_tsv')")) or 0)
                    / 2**20,
                }
                uses_index = app_plan_uses_hnsw(db, probe[0])
            plain = latency(client, texts, personalize=False)
            personal = latency(client, texts, personalize=True)
            log(f"{size}: p50 {plain['p50']:.0f} ms, personal p50 {personal['p50']:.0f} ms")
            results.append(
                {
                    "size": size,
                    "insert_s": insert_s,
                    "plain": plain,
                    "personal": personal,
                    "hnsw": settings,
                    "query_embedding_ms": query_ms,
                    "app_uses_hnsw": uses_index,
                    **sizes_mb,
                }
            )
    return results


def posting_text(row: Any) -> str:
    f = row.fields
    place = f["location"] or "Remote"
    pay = (
        f"Stipend: Rs {f['stipend_min']} to {f['stipend_max']} per month"
        if f["job_type"] == "internship"
        else f"CTC: Rs {f['stipend_min']} to {f['stipend_max']} per year"
    )
    return "\n".join(
        [
            f"{f['title']} at {f['company']}",
            f"Location: {place}",
            f"Type: {f['job_type']}",
            pay,
            f"Skills: {', '.join(f['skills'])}",
            f"Apply by: {f['deadline']:%d %B %Y}",
            f"Apply at: {f['apply_url']}",
            "",
            f["description"],
            f["requirements"],
        ]
    )


def run_ingest_bench(log: Callable[[str], None]) -> dict[str, Any]:
    from sqlalchemy import func, select

    from app.core.security import hash_password
    from app.db.models import Job, JobStatus, Role, User
    from app.ingest import tasks
    from app.ingest.service import create_from_text
    from app.schemas.jobs import PasteIn

    rows = synthetic(INGEST_POSTINGS, BENCH_SEED + 1, datetime.now(UTC).date())
    with database(INGEST_DB), session() as db:
        actor = User(
            email="bench-coordinator@iitrpr.ac.in",
            password_hash=hash_password(PASSWORD),
            full_name="Bench Coordinator",
            role=Role.coordinator,
        )
        db.add(actor)
        db.commit()
        from app.embeddings import warm_up

        warm_up()
        started = time.perf_counter()
        for row in rows:
            create_from_text(db, actor, PasteIn(text=posting_text(row), auto_publish=True))
        submitted = time.perf_counter() - started
        processed = 0
        started = time.perf_counter()
        while tasks.process_one(db):
            processed += 1
        worked = time.perf_counter() - started
        live = db.scalar(select(func.count()).where(Job.status == JobStatus.indexed)) or 0
        review = db.scalar(select(func.count()).where(Job.status == JobStatus.draft)) or 0
    result = {
        "postings": len(rows),
        "submit_s": submitted,
        "worker_s": worked,
        "tasks": processed,
        "indexed": live,
        "review": review,
        "per_second": len(rows) / (submitted + worked),
    }
    log(f"ingest: {result['per_second']:.1f} postings per second")
    return result


# ---------------------------------------------------------------- report


def machine() -> dict[str, str]:
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
        memory = next(
            line.split()[1]
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemTotal")
        )
        ram = f"{int(memory) / 2**20:.1f} GB"
    except (OSError, StopIteration):
        ram = "unknown"
    with session() as db:
        postgres = (db.scalar(text("SHOW server_version")) or "").split()[0]
        vector = db.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
    return {
        "cpu": cpu,
        "cpus": str(os.cpu_count()),
        "ram": ram,
        "postgres": postgres,
        "pgvector": str(vector),
    }


def to_markdown(
    results: list[dict[str, Any]], ingest: dict[str, Any], info: dict[str, str], query_count: int
) -> str:
    lines = [
        f"Run {datetime.now(UTC).date().isoformat()} on {info['cpu']}, {info['cpus']} logical CPUs "
        f"visible to Docker, {info['ram']} RAM in the Docker VM. PostgreSQL {info['postgres']}, "
        f"pgvector {info['pgvector']}. Mock mode, no LLM calls. {query_count} distinct queries per "
        "pass, each embedded once (embedding included in the latency).",
        "",
        "### Search latency, POST /api/search in process (ms)",
        "",
        "| Postings | p50 | p95 | p99 | personalised p50 | p95 | p99 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        a, b = r["plain"], r["personal"]
        lines.append(
            f"| {r['size']:,} | {a['p50']:.0f} | {a['p95']:.0f} | {a['p99']:.0f} | "
            f"{b['p50']:.0f} | {b['p95']:.0f} | {b['p99']:.0f} |"
        )
    lines += [
        "",
        f"Embedding one query takes about {results[0]['query_embedding_ms']:.0f} ms of that. "
        "The application's vector query is planned with the HNSW index at "
        + (", ".join(f"{r['size']:,}" for r in results if r["app_uses_hnsw"]) or "no size")
        + " postings; otherwise Postgres scans and sorts.",
        "",
        "### Index build and size",
        "",
        "| Postings | Table with indexes (MB) | GIN text index (MB) | HNSW m, ef_construction "
        "| Build (s) | HNSW size (MB) |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        for s in r["hnsw"]:
            lines.append(
                f"| {r['size']:,} | {r['table_mb']:.0f} | {r['gin_mb']:.1f} | {s['m']}, "
                f"{s['ef_construction']} | {s['build_s']:.1f} | {s['index_mb']:.1f} |"
            )
    lines += [
        "",
        f"### HNSW recall against exact search ({RECALL_QUERIES} queries, top 10 and top 50)",
        "",
        "Filtered: a location filter that keeps about one posting in nine, with iterative "
        "scans on.",
        "",
        "| Postings | m, ef_construction | ef_search | recall@10 | recall@50 | filtered @10 "
        "| filtered @50 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        for s in r["hnsw"]:
            for ef, rec in s["recall"].items():
                lines.append(
                    f"| {r['size']:,} | {s['m']}, {s['ef_construction']} | {ef} | "
                    f"{rec['all@10']:.3f} | {rec['all@50']:.3f} | {rec['filtered@10']:.3f} | "
                    f"{rec['filtered@50']:.3f} |"
                )
    lines += [
        "",
        "### Ingest throughput (mock parser, local embeddings, one worker)",
        "",
        "| Postings | Submit (s) | Worker (s) | Postings per second | Live | Sent to review |",
        "|---|---|---|---|---|---|",
        f"| {ingest['postings']} | {ingest['submit_s']:.1f} | {ingest['worker_s']:.1f} | "
        f"{ingest['per_second']:.1f} | {ingest['indexed']} | {ingest['review']} |",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(prog="evals.bench")
    parser.add_argument("--sizes", default="1000,10000,50000")
    parser.add_argument("--queries", type=int, default=500)
    parser.add_argument("--no-doc", action="store_true", help="print only")
    args = parser.parse_args()
    os.environ["LLM_MODE"] = "mock"
    _reset()
    sizes = sorted(int(s) for s in args.sizes.split(","))

    def log(message: str) -> None:
        print(f"[{datetime.now(UTC):%H:%M:%S}] {message}", flush=True)

    results = run_search_bench(sizes, args.queries, log)
    ingest = run_ingest_bench(log)
    info = machine()
    body = to_markdown(results, ingest, info, args.queries)
    print("\n" + body)
    if not args.no_doc:
        from evals.report import update_section

        update_section("bench", body, PERFORMANCE_DOC)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
