"""Agent tools. The student always comes from the signed-in session, never from arguments."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import schemas as s
from app.db.models import Application, Job, JobStatus, SavedJob, StudentProfile
from app.search.config import get_search_config
from app.search.engine import search
from app.search.profiles import load_ranking_profile
from app.search.ranking import Profile, score_job
from app.search.retrieval import Filters

VISIBLE = (JobStatus.indexed, JobStatus.expired)


class ToolError(Exception):
    """Shown to the model so that it can correct itself or tell the student."""


@dataclass
class ToolContext:
    db: Session
    user_id: int
    today: date = field(default_factory=lambda: datetime.now(UTC).date())
    # Postings returned by tools in this turn. Answers may only cite these.
    seen: dict[int, s.Citation] = field(default_factory=dict)
    # Write actions waiting for the student's confirmation.
    proposals: list[dict[str, Any]] = field(default_factory=list)
    trace: list[s.ToolTrace] = field(default_factory=list)
    # Raw tool output, kept for evals.
    outputs: list[str] = field(default_factory=list)
    _profile: Profile | None = None

    @property
    def profile(self) -> Profile:
        if self._profile is None:
            self._profile = load_ranking_profile(self.db, self.user_id)
        return self._profile

    def remember(self, job: Job) -> None:
        self.seen[job.id] = s.Citation(job_id=job.id, title=job.title, company=job.company)

    def propose(self, kind: str, label: str, payload: dict[str, Any]) -> None:
        proposal = {"kind": kind, "label": label, "payload": payload}
        if proposal not in self.proposals:
            self.proposals.append(proposal)


def _pay(job: Job) -> str | None:
    low, high = job.stipend_min, job.stipend_max
    if low is None and high is None:
        return None
    unit = "month" if job.job_type == "internship" else "year"
    if low is not None and high is not None and low != high:
        return f"₹{low:,} to ₹{high:,} a {unit}"
    return f"₹{(high if high is not None else low):,} a {unit}"


def _compact(ctx: ToolContext, job: Job) -> dict[str, Any]:
    """Only what the model needs, to keep prompts small."""
    ctx.remember(job)
    data: dict[str, Any] = {
        "job_id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location or ("Remote" if job.remote else None),
        "remote": job.remote,
        "type": job.job_type,
        "pay": _pay(job),
        "deadline": job.deadline.isoformat() if job.deadline else None,
        "days_left": (job.deadline - ctx.today).days if job.deadline else None,
        "skills": job.skills[:8],
    }
    if not ctx.profile.is_empty:
        breakdown = score_job(job, ctx.profile, get_search_config().rerank, ctx.today)
        data["match_percent"] = breakdown["match_percent"]
    return {k: v for k, v in data.items() if v is not None}


def _visible(ctx: ToolContext, job_id: int) -> Job:
    job = ctx.db.get(Job, job_id)
    if job is None or job.status not in VISIBLE:
        raise ToolError(f"There is no posting with job_id {job_id}.")
    ctx.remember(job)
    return job


# ---------------------------------------------------------------- read tools


def search_jobs(ctx: ToolContext, args: s.SearchJobsArgs) -> dict[str, Any]:
    results = search(
        ctx.db,
        args.query,
        Filters(**args.filters.model_dump()),
        profile=ctx.profile,
        limit=args.k,
        today=ctx.today,
    )
    weak = (results.top_similarity or 1.0) < get_search_config().weak_similarity
    return {
        "total": results.total,
        "no_close_match": bool(args.query.strip()) and weak,
        "results": [_compact(ctx, hit.job) for hit in results.hits],
    }


def get_job(ctx: ToolContext, args: s.GetJobArgs) -> dict[str, Any]:
    job = _visible(ctx, args.job_id)
    return {
        **_compact(ctx, job),
        "description": job.description[:1200],
        "requirements": job.requirements[:400],
        "open": job.status == JobStatus.indexed
        and (job.deadline is None or job.deadline >= ctx.today),
        "apply_url": job.apply_url or None,
    }


def get_profile(ctx: ToolContext, _: s.GetProfileArgs) -> dict[str, Any]:
    profile = ctx.db.get(StudentProfile, ctx.user_id)
    if profile is None:
        return {"empty": True}
    parsed = profile.parsed_profile or {}
    return {
        "skills": profile.skills,
        "preferences": {
            k: v for k, v in (profile.preferences or {}).items() if v not in (None, "", [])
        },
        "education": [e.get("degree") for e in parsed.get("education", [])][:3],
        "projects": [p.get("title") for p in parsed.get("projects", [])][:5],
        "experience": [e.get("role") for e in parsed.get("experience", [])][:5],
    }


def list_deadlines(ctx: ToolContext, args: s.ListDeadlinesArgs) -> dict[str, Any]:
    saved = set(ctx.db.scalars(select(SavedJob.job_id).where(SavedJob.user_id == ctx.user_id)))
    tracked = dict(
        ctx.db.execute(
            select(Application.job_id, Application.status).where(Application.user_id == ctx.user_id)
        )
        .tuples()
        .all()
    )
    end = ctx.today + timedelta(days=args.within_days)
    mine = ctx.db.scalars(
        select(Job)
        .where(
            Job.id.in_(saved | set(tracked)),
            Job.status == JobStatus.indexed,
            Job.deadline.between(ctx.today, end),
        )
        .order_by(Job.deadline)
    )
    rows = [{**_compact(ctx, j), "saved": j.id in saved, "stage": tracked.get(j.id)} for j in mine][
        :8
    ]
    known = [r["job_id"] for r in rows]
    others = search(
        ctx.db,
        "",
        Filters(closing_within_days=args.within_days, exclude_ids=known),
        profile=ctx.profile,
        limit=max(0, 6 - len(rows)),
        today=ctx.today,
    )
    return {
        "saved_or_tracked": rows,
        "other_closing_soon": [_compact(ctx, h.job) for h in others.hits],
    }


def compare_jobs(ctx: ToolContext, args: s.CompareJobsArgs) -> dict[str, Any]:
    rows = []
    for job_id in dict.fromkeys(args.job_ids):
        job = _visible(ctx, job_id)
        row = _compact(ctx, job)
        if not ctx.profile.is_empty:
            detail = score_job(job, ctx.profile, get_search_config().rerank, ctx.today)
            row["missing_skills"] = detail["missing_skills"]
        row["duration_months"] = job.duration_months
        rows.append(row)
    if len(rows) < 2:
        raise ToolError("Give at least two different job_ids.")
    return {"jobs": rows}


def explain_fit(ctx: ToolContext, args: s.ExplainFitArgs) -> dict[str, Any]:
    job = _visible(ctx, args.job_id)
    if ctx.profile.is_empty:
        return {"job": _compact(ctx, job), "profile_empty": True}
    detail = score_job(job, ctx.profile, get_search_config().rerank, ctx.today)
    return {
        "job": _compact(ctx, job),
        "match_percent": detail["match_percent"],
        "parts": [
            {"part": c["label"], "value": c["value"], "note": c["note"]}
            for c in detail["components"]
            if c["key"] != "urgency"
        ],
        "matched_skills": detail["matched_skills"],
        "missing_skills": detail["missing_skills"],
        "preferences": detail["preference_checks"],
        "note": "Compares fit only. It is not a chance of selection.",
    }


def skill_gap(ctx: ToolContext, args: s.SkillGapArgs) -> dict[str, Any]:
    job = _visible(ctx, args.job_id)
    detail = score_job(job, ctx.profile, get_search_config().rerank, ctx.today)
    return {
        "job": _compact(ctx, job),
        "has": detail["matched_skills"],
        "missing": detail["missing_skills"],
        "profile_empty": ctx.profile.is_empty,
    }


# ---------------------------------------------------------------- write tools


def save_job(ctx: ToolContext, args: s.SaveJobArgs) -> dict[str, Any]:
    job = _visible(ctx, args.job_id)
    if ctx.db.get(SavedJob, (ctx.user_id, job.id)):
        return {"already_saved": True, "job": _compact(ctx, job)}
    ctx.propose("save_job", f"Save {job.title} at {job.company}", {"job_id": job.id})
    return {"waiting_for_confirmation": True, "job": _compact(ctx, job)}


def track_application(ctx: ToolContext, args: s.TrackApplicationArgs) -> dict[str, Any]:
    job = _visible(ctx, args.job_id)
    stage = {"oa": "online assessment"}.get(args.status.value, args.status.value)
    ctx.propose(
        "track_application",
        f"Track {job.title} at {job.company} as {stage}",
        {"job_id": job.id, "status": args.status.value, "notes": args.notes},
    )
    return {"waiting_for_confirmation": True, "job": _compact(ctx, job), "status": stage}


_LABELS = {
    "roles": "roles",
    "locations": "locations",
    "remote_ok": "remote work",
    "job_types": "job types",
    "duration": "internship length",
    "start_window": "start",
    "min_stipend": "lowest stipend",
}


def _readable(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(value) or "none"
    if key == "duration":
        return f"{value} months"
    if key == "min_stipend":
        return f"₹{value:,} a month"
    return str(value)


def update_preferences(ctx: ToolContext, args: s.UpdatePreferencesArgs) -> dict[str, Any]:
    changes = args.changes.model_dump(exclude_none=True)
    if not changes:
        raise ToolError("Name at least one preference to change.")
    parts = [f"{_LABELS[k]}: {_readable(k, v)}" for k, v in changes.items()]
    ctx.propose("update_preferences", f"Update preferences ({'; '.join(parts)})", changes)
    return {"waiting_for_confirmation": True, "changes": changes}


# ---------------------------------------------------------------- registry


@dataclass(frozen=True)
class Tool:
    name: str
    args: type[BaseModel]
    run: Callable[[ToolContext, Any], dict[str, Any]] | None
    status: str


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool("search_jobs", s.SearchJobsArgs, search_jobs, "Searching postings"),
        Tool("get_job", s.GetJobArgs, get_job, "Reading the posting"),
        Tool("get_profile", s.GetProfileArgs, get_profile, "Checking your profile"),
        Tool(
            "update_preferences",
            s.UpdatePreferencesArgs,
            update_preferences,
            "Preparing a preference change",
        ),
        Tool("save_job", s.SaveJobArgs, save_job, "Preparing to save a posting"),
        Tool(
            "track_application",
            s.TrackApplicationArgs,
            track_application,
            "Preparing a tracker update",
        ),
        Tool("list_deadlines", s.ListDeadlinesArgs, list_deadlines, "Checking deadlines"),
        Tool("compare_jobs", s.CompareJobsArgs, compare_jobs, "Comparing postings"),
        Tool("explain_fit", s.ExplainFitArgs, explain_fit, "Working out the fit"),
        Tool("skill_gap", s.SkillGapArgs, skill_gap, "Comparing skills"),
        Tool("final_answer", s.FinalAnswerArgs, None, "Writing the answer"),
    )
}
WRITE_TOOLS = {"save_job", "track_application", "update_preferences"}


def _inline_refs(schema: Any, definitions: dict[str, Any]) -> Any:
    """Resolve $ref, which some providers do not accept in tool schemas."""
    if isinstance(schema, dict):
        if "$ref" in schema:
            name = schema["$ref"].rsplit("/", 1)[1]
            rest = {k: v for k, v in schema.items() if k != "$ref"}
            return {**_inline_refs(definitions[name], definitions), **rest}
        return {
            k: _inline_refs(v, definitions)
            for k, v in schema.items()
            if k not in ("$defs", "title") or (k == "title" and isinstance(v, dict))
        }
    if isinstance(schema, list):
        return [_inline_refs(item, definitions) for item in schema]
    return schema


def tool_specs(names: list[str] | None = None) -> list[dict[str, Any]]:
    specs = []
    for name in names or list(TOOLS):
        raw = TOOLS[name].args.model_json_schema()
        parameters = _inline_refs(raw, raw.get("$defs", {}))
        description = parameters.pop("description", "")
        specs.append(
            {
                "type": "function",
                "function": {"name": name, "description": description, "parameters": parameters},
            }
        )
    return specs


def execute(ctx: ToolContext, name: str, raw_arguments: str) -> tuple[bool, str]:
    """Validate and run one tool. Returns (ok, compact JSON for the model)."""
    arguments: dict[str, Any] = {}
    try:
        tool = TOOLS.get(name)
        if tool is None or tool.run is None:
            raise ToolError(f"There is no tool called {name}.")
        loaded = json.loads(raw_arguments or "{}")
        if not isinstance(loaded, dict):
            raise ToolError("Arguments must be a JSON object.")
        arguments = loaded
        result = tool.run(ctx, tool.args.model_validate(arguments))
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "arguments"
        outcome: dict[str, Any] = {"error": f"{where}: {first['msg']}"}
    except (ToolError, json.JSONDecodeError) as exc:
        outcome = {"error": str(exc)}
    else:
        summary = ""
        if isinstance(result.get("results"), list):
            summary = f"{len(result['results'])} results"
        ctx.trace.append(s.ToolTrace(name=name, arguments=arguments, ok=True, summary=summary))
        content = json.dumps(result, separators=(",", ":"), default=str, ensure_ascii=False)
        ctx.outputs.append(content)
        return True, content
    ctx.trace.append(
        s.ToolTrace(name=name, arguments=arguments, ok=False, summary=outcome["error"][:200])
    )
    return False, json.dumps(outcome)
