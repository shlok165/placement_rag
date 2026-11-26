"""Deterministic stand-in for the model, keyed by purpose."""

from typing import Any

from app.agent.memory_rules import extract_rules
from app.agent.mock_agent import agent_turn
from app.ingest.resume_rules import parse_resume_rules
from app.ingest.rules import parse_posting
from app.llm.types import LLMResponse, Message, Purpose


def _last_user(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _parse_job(messages: list[Message], _: list[dict[str, Any]] | None) -> LLMResponse:
    return LLMResponse(content=parse_posting(_last_user(messages)).model_dump_json())


def _parse_resume(messages: list[Message], _: list[dict[str, Any]] | None) -> LLMResponse:
    return LLMResponse(content=parse_resume_rules(_last_user(messages)).model_dump_json())


def _extract_memory(messages: list[Message], _: list[dict[str, Any]] | None) -> LLMResponse:
    return LLMResponse(content=extract_rules(_last_user(messages)).model_dump_json())


def _agent_turn(messages: list[Message], tools: list[dict[str, Any]] | None) -> LLMResponse:
    return agent_turn(messages, tools)


_HANDLERS = {
    "parse_job": _parse_job,
    "parse_resume": _parse_resume,
    "extract_memory": _extract_memory,
    "agent_turn": _agent_turn,
    "agent_repair": _agent_turn,
}


def complete(
    purpose: Purpose, messages: list[Message], tools: list[dict[str, Any]] | None
) -> LLMResponse:
    response = _HANDLERS[purpose](messages, tools)
    response.mode = "mock"
    size = sum(len(str(m.get("content") or "")) for m in messages)
    response.input_tokens = size // 4
    response.output_tokens = len(response.content) // 4
    return response
