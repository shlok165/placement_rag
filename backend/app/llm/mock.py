"""Deterministic stand-in for the model, keyed by purpose."""

from typing import Any

from app.ingest.rules import parse_posting
from app.llm.types import LLMResponse, Message, Purpose


def _last_user(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _parse_job(messages: list[Message], _: list[dict[str, Any]] | None) -> LLMResponse:
    return LLMResponse(content=parse_posting(_last_user(messages)).model_dump_json())


_HANDLERS = {"parse_job": _parse_job}


def complete(
    purpose: Purpose, messages: list[Message], tools: list[dict[str, Any]] | None
) -> LLMResponse:
    response = _HANDLERS[purpose](messages, tools)
    response.mode = "mock"
    size = sum(len(str(m.get("content") or "")) for m in messages)
    response.input_tokens = size // 4
    response.output_tokens = len(response.content) // 4
    return response
