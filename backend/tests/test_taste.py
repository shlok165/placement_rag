from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import InteractionEvent, Job, JobStatus, StudentProfile, User
from app.search.config import TasteConfig, get_search_config
from app.search.engine import search
from app.search.profiles import load_ranking_profile, refresh_embedding, to_ranking_profile
from app.search.ranking import cosine, score_job
from app.search.taste import combine, taste_vector
from tests.conftest import PASSWORD, Api
from tests.test_search import TODAY, add

NOW = datetime(2026, 6, 1, tzinfo=UTC)


@pytest.fixture
def catalogue(db: Session) -> dict[str, Job]:
    return {
        "mobile-1": add(db, title="Android Developer Intern", description="Ship phone apps.",
                        skills=["Kotlin", "Android"]),
        "mobile-2": add(db, title="Mobile App Developer", description="Build Android features.",
                        skills=["Kotlin", "Android", "Git"]),
        "mobile-3": add(db, title="Flutter Developer Intern", description="Cross-platform phone apps.",
                        skills=["Flutter", "Android"]),
        "backend": add(db, title="Backend Intern", description="Build APIs.", skills=["Python"]),
        "civil": add(db, title="Structural Engineer", description="Design bridges.",
                     skills=["AutoCAD"], location="Delhi"),
    }  # fmt: skip


def me(client: Api) -> int:
    return int(client.get("/api/auth/me").json()["id"])


def events(db: Session, user_id: int) -> list[tuple[int, str]]:
    rows = db.execute(
        select(InteractionEvent.job_id, InteractionEvent.kind)
        .where(InteractionEvent.user_id == user_id)
        .order_by(InteractionEvent.id)
    )
    return [(r.job_id, r.kind) for r in rows]


def with_profile(db: Session, user_id: int) -> None:
    profile = db.get(StudentProfile, user_id) or StudentProfile(user_id=user_id)
    profile.skills = ["Python", "Git"]
    profile.preferences = {"roles": ["Software"], "job_types": ["internship"]}
    refresh_embedding(profile)
    db.add(profile)
    db.commit()


# ---------------------------------------------------------------- cold start


def test_without_events_the_ranking_is_exactly_unchanged(
    db: Session, student: Api, catalogue: dict[str, Job]
) -> None:
    user_id = me(student)
    with_profile(db, user_id)
    loaded = load_ranking_profile(db, user_id)
    assert loaded.taste is None
    plain = to_ranking_profile(db.get(StudentProfile, user_id))
    for query in ("", "developer intern", "bridges"):
        a = search(db, query, profile=loaded, today=TODAY)
        b = search(db, query, profile=plain, today=TODAY)
        assert [(h.job.id, h.score, h.breakdown) for h in a.hits] == [
            (h.job.id, h.score, h.breakdown) for h in b.hits
        ]
    detail = student.get(f"/api/jobs/{catalogue['backend'].id}").json()
    assert "taste" not in {c["key"] for c in detail["breakdown"]["components"]}


def test_impressions_and_opens_do_not_create_taste(
    db: Session, student: Api, catalogue: dict[str, Job]
) -> None:
    user_id = me(student)
    job_id = catalogue["mobile-1"].id
    student.post("/api/events", json={"events": [{"job_id": job_id, "kind": "impression"}]})
    student.get(f"/api/jobs/{job_id}")
    assert {k for _, k in events(db, user_id)} == {"impression", "open"}
    assert load_ranking_profile(db, user_id).taste is None


# ---------------------------------------------------------------- recording


def test_events_are_recorded_once_and_only_for_visible_postings(
    db: Session, student: Api, catalogue: dict[str, Job]
) -> None:
    hidden = catalogue["civil"]
    hidden.status = JobStatus.archived
    db.commit()
    shown = catalogue["backend"].id
    batch = [
        {"job_id": shown, "kind": "impression"},
        {"job_id": shown, "kind": "impression"},
        {"job_id": shown, "kind": "apply_clicked"},
        {"job_id": hidden.id, "kind": "impression"},
        {"job_id": 999_999, "kind": "impression"},
    ]
    reply = student.post("/api/events", json={"events": batch})
    assert reply.status_code == 202
    assert reply.json() == {"recorded": 2}
    assert sorted(events(db, me(student))) == [(shown, "apply_clicked"), (shown, "impression")]


@pytest.mark.parametrize("kind", ["save", "thumb_up", "open", "anything"])
def test_the_browser_cannot_send_server_side_kinds(student: Api, kind: str) -> None:
    reply = student.post("/api/events", json={"events": [{"job_id": 1, "kind": kind}]})
    assert reply.status_code == 422


def test_events_need_a_signed_in_user(anonymous: Api) -> None:
    reply = anonymous.post("/api/events", json={"events": [{"job_id": 1, "kind": "impression"}]})
    assert reply.status_code in (401, 403)


def test_events_carry_no_text(db: Session) -> None:
    columns = set(InteractionEvent.__table__.columns.keys())
    assert columns == {"id", "user_id", "job_id", "kind", "created_at"}


def test_saving_records_once_and_unsaving_removes_it(
    db: Session, student: Api, catalogue: dict[str, Job]
) -> None:
    user_id, job_id = me(student), catalogue["mobile-1"].id
    student.put(f"/api/saved/{job_id}")
    student.put(f"/api/saved/{job_id}")
    assert events(db, user_id) == [(job_id, "save")]
    student.delete(f"/api/saved/{job_id}")
    assert events(db, user_id) == []


def test_reactions_can_be_set_changed_and_cleared(
    db: Session, student: Api, catalogue: dict[str, Job]
) -> None:
    job_id = catalogue["backend"].id
    url = f"/api/jobs/{job_id}/reaction"
    assert student.put(url, json={"reaction": "up"}).json() == {"reaction": "up"}
    assert student.get(f"/api/jobs/{job_id}").json()["reaction"] == "up"
    student.put(url, json={"reaction": "down"})
    assert student.get(f"/api/jobs/{job_id}").json()["reaction"] == "down"
    student.put(url, json={"reaction": None})
    assert student.get(f"/api/jobs/{job_id}").json()["reaction"] is None
    kinds = [k for j, k in events(db, me(student)) if k.startswith("thumb")]
    assert kinds == []


def test_reacting_to_a_hidden_posting_is_refused(
    db: Session, student: Api, catalogue: dict[str, Job]
) -> None:
    job = catalogue["civil"]
    job.status = JobStatus.draft
    db.commit()
    assert student.put(f"/api/jobs/{job.id}/reaction", json={"reaction": "up"}).status_code == 404


def test_deleting_the_account_removes_events_and_export_lists_them(
    db: Session, student: Api, catalogue: dict[str, Job]
) -> None:
    user_id, job_id = me(student), catalogue["backend"].id
    student.put(f"/api/saved/{job_id}")
    exported = student.get("/api/profile/export").json()
    assert {"job_id": job_id, "kind": "save"}.items() <= exported["activity"][0].items()
    reply = student.post("/api/profile/delete-account", json={"password": PASSWORD})
    assert reply.status_code == 204
    db.expire_all()
    assert db.get(User, user_id) is None
    count = select(func.count()).select_from(InteractionEvent)
    assert db.scalar(count.where(InteractionEvent.user_id == user_id)) == 0


# ---------------------------------------------------------------- the taste vector


def test_no_positive_events_means_no_taste(catalogue: dict[str, Job]) -> None:
    vector = list(catalogue["civil"].embedding)
    config = TasteConfig()
    assert combine([], config, NOW) is None
    assert combine([("thumb_down", NOW, vector)], config, NOW) is None
    assert combine([("save", NOW, vector)], config.model_copy(update={"save": 0}), NOW) is None


def test_older_events_count_less(catalogue: dict[str, Job]) -> None:
    mobile, civil = list(catalogue["mobile-1"].embedding), list(catalogue["civil"].embedding)
    config = TasteConfig(half_life_days=10)
    fresh_mobile = combine(
        [("save", NOW, mobile), ("save", NOW - timedelta(days=60), civil)], config, NOW
    )
    fresh_civil = combine(
        [("save", NOW - timedelta(days=60), mobile), ("save", NOW, civil)], config, NOW
    )
    assert fresh_mobile and fresh_civil
    assert cosine(fresh_mobile, mobile) > cosine(fresh_civil, mobile)


def test_a_thumb_down_pushes_away(catalogue: dict[str, Job]) -> None:
    mobile, civil = list(catalogue["mobile-1"].embedding), list(catalogue["civil"].embedding)
    liked = combine([("save", NOW, mobile)], TasteConfig(), NOW)
    disliked = combine([("save", NOW, mobile), ("thumb_down", NOW, civil)], TasteConfig(), NOW)
    assert liked and disliked
    assert cosine(disliked, civil) < cosine(liked, civil)


def test_taste_can_be_switched_off(db: Session, student: Api, catalogue: dict[str, Job]) -> None:
    user_id = me(student)
    student.put(f"/api/saved/{catalogue['mobile-1'].id}")
    assert taste_vector(db, user_id, TasteConfig()) is not None
    assert taste_vector(db, user_id, TasteConfig(enabled=False)) is None


def test_saved_postings_lift_similar_ones_and_say_why(
    db: Session, student: Api, catalogue: dict[str, Job]
) -> None:
    user_id = me(student)
    with_profile(db, user_id)
    before = load_ranking_profile(db, user_id)
    for key in ("mobile-1", "mobile-2"):
        student.put(f"/api/saved/{catalogue[key].id}")
    after = load_ranking_profile(db, user_id)
    assert after.taste is not None
    config = get_search_config().rerank
    target, other = catalogue["mobile-3"], catalogue["civil"]

    def score(profile: Any, job: Job) -> float:
        return float(score_job(job, profile, config, TODAY)["score"])

    assert score(after, target) - score(after, other) > score(before, target) - score(before, other)
    detail = student.get(f"/api/jobs/{target.id}").json()
    (part,) = [c for c in detail["breakdown"]["components"] if c["key"] == "taste"]
    assert part["label"] == "Similar to jobs you saved"
    assert part["contribution"] > 0
