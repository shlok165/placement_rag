"""Decides whether a message holds something to remember, and extracts it in mock mode."""

import re

from app.agent.schemas import ProposedFact, ProposedFacts

# A turn is worth an extraction call only if the student says something about themselves.
_PERSONAL = re.compile(
    r"\b(i|i'm|i am|i've|my|me)\b.{0,60}\b(prefer|want|only|never|don't want|do not want|avoid|"
    r"target|targeting|aim|aiming|interested|looking for|hope|plan|graduat|available|free|"
    r"cannot|can't|relocat|love|hate|like|dislike|based|live)",
    re.IGNORECASE,
)
_SHORTHAND = re.compile(
    r"^\s*(no|only|never|avoid|prefer|targeting|remember)\b.{4,}", re.IGNORECASE
)


def worth_extracting(text: str) -> bool:
    if text.strip().endswith("?") and not re.search(r"\bremember\b", text, re.IGNORECASE):
        # Questions such as "can I see only remote roles?" are requests, not lasting facts.
        sentences = [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if not x.endswith("?")]
        text = " ".join(sentences)
    return bool(_PERSONAL.search(text) or _SHORTHAND.search(text))


def extract_rules(text: str) -> ProposedFacts:
    """Rules used in mock mode."""
    facts: list[ProposedFact] = []
    for sentence in re.split(r"(?<=[.!?;])\s+|\n", text):
        sentence = sentence.strip().strip(".!;")
        if not sentence or sentence.endswith("?") or not worth_extracting(sentence):
            continue
        cleaned = re.sub(
            r"^(please\s+)?(remember\s+(that\s+)?)?(i am|i'm|i'd|i would|i|we)\s+",
            "",
            sentence,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^(please\s+)?remember\s+(that\s+)?", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned[:1].upper() + cleaned[1:]
        kind = (
            "fact"
            if re.search(r"\b(graduat|based|live|available|free)", cleaned, re.I)
            else "preference"
        )
        if 3 <= len(cleaned) <= 160:
            facts.append(ProposedFact(kind=kind, text=cleaned))
    return ProposedFacts(facts=facts[:3])
