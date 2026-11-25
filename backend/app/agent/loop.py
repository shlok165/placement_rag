"""The agent loop: model, tools, checks, answer."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.agent import grounding
from app.agent.schemas import Citation, FinalAnswerArgs
from app.agent.tools import TOOLS, ToolContext, execute, tool_specs
from app.core.config import Settings
from app.llm.client import LLMClient, extract_json
from app.llm.types import LLMError, LLMResponse, Message, ToolCall

logger = logging.getLogger("app.agent")

MAX_REPAIRS = 1
MAX_CALLS_PER_STEP = 4

NOTICES = {
    "budget": "The live assistant has used its budget for now, so this answer comes from built-in "
    "rules over the same postings.",
    "provider": "The live assistant is not reachable right now, so this answer comes from built-in "
    "rules over the same postings.",
    "limit": "I stopped early to stay within the limits for one message.",
}


@dataclass
class TurnResult:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    followups: list[str] = field(default_factory=list)
    notice: str | None = None
    # The model produced a valid structured answer that passed every check.
    structured: bool = False
    repaired: bool = False
    iterations: int = 0
    tokens: int = 0
    mode: str = "mock"
    stopped: bool = False


def fallback_answer(ctx: ToolContext) -> TurnResult:
    """Built only from tool results, so it is always grounded."""
    if not ctx.seen:
        return TurnResult(
            "I do not have an answer for that from the postings. Try naming a role, a skill or a "
            "city, or ask what is closing soon."
        )
    cited = list(ctx.seen.values())[:5]
    lines = [f"- **{c.title}** at {c.company} [#{c.job_id}]" for c in cited]
    return TurnResult("Here is what I found:\n\n" + "\n".join(lines), citations=cited)


def _final(call: ToolCall) -> FinalAnswerArgs:
    return FinalAnswerArgs.model_validate(extract_json(call.arguments))


def _from_text(text: str) -> tuple[FinalAnswerArgs | None, bool]:
    """Some models answer in plain text. Accept JSON in the right shape, or wrap the text."""
    try:
        return FinalAnswerArgs.model_validate(extract_json(text)), True
    except (ValueError, ValidationError):
        pass
    if not text.strip():
        return None, False
    return FinalAnswerArgs(answer_markdown=text.strip()[:4000]), False


def _assistant_message(response: LLMResponse) -> Message:
    return {
        "role": "assistant",
        "content": response.content or "",
        "tool_calls": [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": c.arguments},
            }
            for c in response.tool_calls[:MAX_CALLS_PER_STEP]
        ],
    }


def run_turn(
    llm: LLMClient,
    ctx: ToolContext,
    messages: list[Message],
    settings: Settings,
    *,
    emit: Callable[[str], None] = lambda _: None,
    cancelled: Callable[[], bool] = lambda: False,
    scope: str = "app",
    model: str | None = None,
    allow_fallback: bool = True,
) -> TurnResult:
    messages = list(messages)
    tokens = repairs = 0
    notice: str | None = None
    mode = "mock"
    modes: list[str] = []
    step = 0

    def finish(result: TurnResult) -> TurnResult:
        result.iterations, result.tokens = step, tokens
        result.notice = result.notice or notice
        result.repaired = repairs > 0
        # A turn counts as live if any of its calls reached the provider.
        result.mode = next((m for m in ("live", "cache") if m in modes), mode)
        return result

    def check(answer: FinalAnswerArgs, structured: bool) -> TurnResult | list[str]:
        found = grounding.problems(answer, ctx.seen)
        if found:
            return found
        return TurnResult(
            answer.answer_markdown,
            grounding.citations(answer, ctx.seen),
            answer.suggested_followups,
            structured=structured,
        )

    while step < settings.agent_max_iterations:
        step += 1
        if cancelled():
            return finish(TurnResult("", stopped=True))
        last = step == settings.agent_max_iterations or tokens > settings.agent_max_tokens_per_turn
        specs = tool_specs(["final_answer"] if last else None)
        try:
            response = llm.chat(
                "agent_turn",
                messages,
                tools=specs,
                temperature=0.0,
                max_tokens=settings.agent_max_output_tokens,
                user_id=ctx.user_id,
                scope=scope,
                model=model,
                allow_fallback=allow_fallback,
            )
        except LLMError as exc:
            logger.warning("agent call failed", extra={"code": exc.code})
            if not allow_fallback:
                raise
            result = fallback_answer(ctx)
            result.notice = exc.message
            return finish(result)
        tokens += response.input_tokens + response.output_tokens
        modes.append(response.mode)
        if response.degraded:
            notice = NOTICES[response.degraded]

        if not response.tool_calls:
            plain, structured = _from_text(response.content)
            outcome = check(plain, structured) if plain else ["the answer was empty"]
            if isinstance(outcome, TurnResult):
                return finish(outcome)
            if repairs >= MAX_REPAIRS or last:
                break
            repairs += 1
            messages += [
                {"role": "assistant", "content": response.content or ""},
                {
                    "role": "user",
                    "content": f"Not shown to the student because {'; '.join(outcome)}. "
                    "Correct it and call final_answer.",
                },
            ]
            continue

        messages.append(_assistant_message(response))
        done: TurnResult | None = None
        for call in response.tool_calls[:MAX_CALLS_PER_STEP]:
            if call.name == "final_answer":
                emit(TOOLS["final_answer"].status)
                try:
                    outcome = check(_final(call), True)
                except (ValueError, ValidationError) as exc:
                    outcome = [f"the arguments were not valid: {str(exc)[:200]}"]
                if isinstance(outcome, TurnResult):
                    done = outcome
                    break
                repairs += 1
                reply = {"error": f"Not shown to the student because {'; '.join(outcome)}."}
                content = str(reply)
            else:
                if call.name in TOOLS:
                    emit(TOOLS[call.name].status)
                _, content = execute(ctx, call.name, call.arguments)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
        if done:
            return finish(done)
        if repairs > MAX_REPAIRS:
            break

    result = fallback_answer(ctx)
    if step >= settings.agent_max_iterations and repairs <= MAX_REPAIRS:
        result.notice = NOTICES["limit"]
    return finish(result)


def turn_messages(system: str, history: list[dict[str, Any]], text: str) -> list[Message]:
    return [{"role": "system", "content": system}, *history, {"role": "user", "content": text}]
