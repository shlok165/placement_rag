"""Long-term facts and the rolling summary of a conversation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.grounding import MARKER
from app.agent.memory_rules import worth_extracting
from app.agent.prompts import MEMORY
from app.agent.schemas import ProposedFact, ProposedFacts
from app.db.models import ChatMessage, MemoryFact
from app.ingest.duplicates import normalise
from app.llm.client import LLMClient
from app.llm.types import LLMError

MAX_FACTS = 30
SUMMARY_CHARS = 900


def active_facts(db: Session, user_id: int) -> list[MemoryFact]:
    query = (
        select(MemoryFact)
        .where(MemoryFact.user_id == user_id, MemoryFact.is_active)
        .order_by(MemoryFact.id.desc())
        .limit(MAX_FACTS)
    )
    return list(reversed(db.scalars(query).all()))


def propose_facts(
    llm: LLMClient, db: Session, user_id: int, text: str, scope: str = "app"
) -> list[ProposedFact]:
    """New facts in this message. The student confirms each one before it is kept."""
    if not worth_extracting(text):
        return []
    known = {normalise(f.text) for f in active_facts(db, user_id)}
    try:
        result, _ = llm.structured(
            "extract_memory",
            MEMORY,
            text,
            ProposedFacts,
            user_id=user_id,
            scope=scope,
            max_tokens=300,
        )
    except LLMError:
        return []
    fresh = []
    for fact in result.facts:
        key = normalise(fact.text)
        if key and key not in known:
            known.add(key)
            fresh.append(fact)
    return fresh


def summarise(messages: list[ChatMessage]) -> str:
    """Condense older messages without a model call: what was asked, and which postings came up."""
    asked = [m.content.strip().replace("\n", " ")[:110] for m in messages if m.role == "user"]
    ids: dict[str, None] = {}
    for message in messages:
        for job_id in MARKER.findall(message.content):
            ids.setdefault(job_id)
    lines = [f"- The student asked: {q}" for q in asked[-6:]]
    if ids:
        listed = ", ".join(list(ids)[-8:])
        lines.append(f"- Postings discussed (fetch again before mentioning): {listed}")
    return "\n".join(lines)[:SUMMARY_CHARS]
