from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.errors import AppError

Message = dict[str, Any]
# agent_repair: an agent call that re-asks for a structured or grounded answer.
Purpose = Literal[
    "parse_job", "parse_resume", "agent_turn", "agent_repair", "extract_memory", "judge"
]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str


class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    # live: the provider answered now. cache: an earlier live answer. mock: rules, no model.
    mode: Literal["live", "cache", "mock"] = "mock"
    # Why a live call was replaced by the rule-based fallback, if it was.
    degraded: Literal["budget", "provider"] | None = None


class LLMError(AppError):
    status_code = 502
    code = "llm_unavailable"


class LLMConfigError(LLMError):
    code = "llm_config"


class BudgetExceeded(LLMError):
    status_code = 429
    code = "llm_budget"
