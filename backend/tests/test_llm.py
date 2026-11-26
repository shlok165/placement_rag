import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import ChatMessage, ChatSession, LlmCache, LlmCall
from app.llm.client import MAX_MESSAGE_CHARS, LLMClient, extract_json
from app.llm.quota import budget_status, chat_quota
from app.llm.types import BudgetExceeded, LLMConfigError, LLMError

MODELS = {"data": [{"id": "maker/model-a", "aliases": ["model-a"]}]}
HELLO = [{"role": "user", "content": "hello"}]


def ok(content: str = "hi", tool_calls: list[dict[str, Any]] | None = None) -> httpx.Response:
    message: dict[str, Any] = {"content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    usage = {"prompt_tokens": 11, "completion_tokens": 3}
    return httpx.Response(200, json={"choices": [{"message": message}], "usage": usage})


class Provider:
    """Scripted provider. Each chat request takes the next reply; the last one repeats."""

    def __init__(self, *replies: httpx.Response | Exception) -> None:
        self.replies = list(replies) or [ok()]
        self.requests: list[httpx.Request] = []
        self.models: dict[str, Any] = MODELS

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=self.models)
        self.requests.append(request)
        reply = self.replies[0] if len(self.replies) == 1 else self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


Factory = Callable[..., tuple[LLMClient, Provider, list[float]]]


@pytest.fixture
def make() -> Factory:
    def build(*replies: httpx.Response | Exception, **overrides: Any) -> Any:
        settings: Settings = get_settings().model_copy(
            update={
                "llm_mode": "live",
                "llm_api_key": SecretStr("not-a-real-key"),
                "llm_model": "model-a",
                "llm_base_url": "https://provider.test",
                **overrides,
            }
        )
        provider = Provider(*replies)
        waits: list[float] = []
        client = LLMClient(settings, transport=httpx.MockTransport(provider), sleep=waits.append)
        return client, provider, waits

    return build


def calls(db: Session) -> list[LlmCall]:
    db.expire_all()
    return list(db.scalars(select(LlmCall).order_by(LlmCall.id)))


def test_mock_mode_is_the_default_and_makes_no_request(db: Session) -> None:
    assert get_settings().llm_mode == "mock"
    response = LLMClient().chat("parse_job", [{"role": "user", "content": "Company: A\nRole: B"}])
    assert response.mode == "mock"
    (row,) = calls(db)
    assert (row.is_live, row.model) == (False, "mock")


def test_a_real_request_fails_the_test_suite() -> None:
    with pytest.raises(AssertionError, match="external services"):
        httpx.get("https://example.com")


def test_live_without_a_key_stays_mock() -> None:
    settings = get_settings().model_copy(update={"llm_mode": "live"})
    assert settings.is_live is False


def test_live_call_is_logged_and_sends_the_key_only_to_the_provider(
    make: Factory, db: Session
) -> None:
    client, provider, _ = make(ok("answer"))
    response = client.chat("judge", HELLO, user_id=None)
    assert (response.content, response.mode) == ("answer", "live")
    (request,) = provider.requests
    assert request.url.host == "provider.test"
    assert request.headers["Authorization"] == "Bearer not-a-real-key"
    (row,) = calls(db)
    assert (row.status, row.is_live, row.input_tokens, row.output_tokens) == ("ok", True, 11, 3)


def test_identical_calls_hit_the_api_once(make: Factory, db: Session) -> None:
    client, provider, _ = make(ok("answer"))
    client.chat("judge", HELLO)
    again = client.chat("judge", HELLO)
    assert (again.content, again.mode) == ("answer", "cache")
    assert len(provider.requests) == 1
    client.chat("judge", HELLO, temperature=0.5)
    assert len(provider.requests) == 2
    assert [c.cache_hit for c in calls(db)] == [False, True, False]


def test_cache_survives_a_new_client(make: Factory) -> None:
    first, _, _ = make(ok("answer"))
    first.chat("judge", HELLO)
    second, provider, _ = make(ok("different"))
    assert second.chat("judge", HELLO).content == "answer"
    assert provider.requests == []


def test_cached_answers_remember_their_owner(make: Factory, db: Session, make_user: Any) -> None:
    user = make_user("a@example.com")
    client, _, _ = make()
    client.chat("judge", HELLO, user_id=user.id)
    assert db.scalar(select(LlmCache.user_id)) == user.id


@pytest.mark.parametrize(
    "failure",
    [httpx.Response(500), httpx.Response(429), httpx.ConnectError("down"), httpx.ReadTimeout("t")],
)
def test_temporary_errors_are_retried(make: Factory, db: Session, failure: Any) -> None:
    client, provider, waits = make(failure, ok("fine"))
    assert client.chat("judge", HELLO, allow_fallback=False).content == "fine"
    assert len(provider.requests) == 2
    assert waits == [1.0]
    assert [c.is_live for c in calls(db)] == [True, True]


def test_at_most_two_retries_with_backoff(make: Factory) -> None:
    client, provider, waits = make(httpx.Response(503))
    with pytest.raises(LLMError):
        client.chat("judge", HELLO, allow_fallback=False)
    assert len(provider.requests) == 3
    assert waits == [1.0, 2.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
def test_client_errors_are_not_retried(make: Factory, status: int) -> None:
    client, provider, waits = make(httpx.Response(status))
    with pytest.raises(LLMError):
        client.chat("judge", HELLO, allow_fallback=False)
    assert (len(provider.requests), waits) == (1, [])


def test_retry_after_is_honoured(make: Factory) -> None:
    client, _, waits = make(httpx.Response(429, headers={"Retry-After": "7"}), ok())
    client.chat("judge", HELLO, allow_fallback=False)
    assert waits == [7.0]


def test_long_retry_after_gives_up(make: Factory) -> None:
    client, provider, waits = make(httpx.Response(429, headers={"Retry-After": "900"}))
    with pytest.raises(LLMError):
        client.chat("judge", HELLO, allow_fallback=False)
    assert (len(provider.requests), waits) == (1, [])


def test_empty_provider_balance_is_a_budget_error(make: Factory) -> None:
    client, provider, _ = make(httpx.Response(402))
    with pytest.raises(BudgetExceeded):
        client.chat("judge", HELLO, allow_fallback=False)
    assert len(provider.requests) == 1


def test_daily_cap_blocks_and_falls_back(make: Factory, db: Session) -> None:
    client, provider, _ = make(ok(), llm_daily_call_cap=1)
    client.chat("judge", HELLO)
    text = [{"role": "user", "content": "Company: A\nRole: B Intern"}]
    with pytest.raises(BudgetExceeded):
        client.chat("parse_job", text, allow_fallback=False)
    fallback = client.chat("parse_job", text)
    assert (fallback.mode, fallback.degraded) == ("mock", "budget")
    assert len(provider.requests) == 1
    assert budget_status(db, client.settings)["remaining_today"] == 0


def test_cached_answers_still_work_over_budget(make: Factory) -> None:
    client, _, _ = make(ok("kept"), llm_daily_call_cap=1)
    client.chat("judge", HELLO)
    assert client.chat("judge", HELLO, allow_fallback=False).content == "kept"


def test_total_cap_counts_earlier_days(make: Factory, db: Session) -> None:
    client, _, _ = make(ok(), llm_total_call_cap=1)
    client.chat("judge", HELLO)
    row = calls(db)[0]
    row.created_at = datetime.now(UTC) - timedelta(days=3)
    db.commit()
    with pytest.raises(BudgetExceeded):
        client.chat("judge", [{"role": "user", "content": "x"}], allow_fallback=False)


def test_retries_count_against_the_cap(make: Factory) -> None:
    client, provider, _ = make(httpx.Response(500), llm_daily_call_cap=2)
    with pytest.raises(BudgetExceeded):
        client.chat("judge", HELLO, allow_fallback=False)
    assert len(provider.requests) == 2


def test_eval_cap_is_per_run(make: Factory) -> None:
    client, provider, _ = make(ok(), llm_eval_call_cap=2)
    for index in range(2):
        client.chat("judge", [{"role": "user", "content": str(index)}], scope="eval:1")
    with pytest.raises(BudgetExceeded):
        client.chat("judge", HELLO, scope="eval:1", allow_fallback=False)
    client.chat("judge", HELLO, scope="eval:2", allow_fallback=False)
    assert len(provider.requests) == 3


def test_unlisted_model_is_a_clear_error(make: Factory) -> None:
    client, provider, _ = make(llm_model="gone")
    with pytest.raises(LLMConfigError, match="not offered"):
        client.chat("judge", HELLO)
    assert provider.requests == []


def test_missing_model_is_a_clear_error(make: Factory) -> None:
    client, _, _ = make(llm_model="")
    with pytest.raises(LLMConfigError, match="LLM_MODEL"):
        client.chat("judge", HELLO)


def test_long_messages_are_shortened(make: Factory) -> None:
    client, provider, _ = make()
    client.chat("judge", [{"role": "user", "content": "x" * 50_000}])
    sent = json.loads(provider.requests[0].content)["messages"][0]["content"]
    assert len(sent) <= MAX_MESSAGE_CHARS + 20


def test_tool_calls_are_parsed(make: Factory) -> None:
    raw = {"id": "a", "function": {"name": "get_job", "arguments": '{"job_id":1}'}}
    client, provider, _ = make(ok("", [raw]))
    response = client.chat("agent_turn", HELLO, tools=[{"type": "function"}])
    assert response.tool_calls[0].name == "get_job"
    assert json.loads(provider.requests[0].content)["tool_choice"] == "auto"


TOOLS = [{"type": "function", "function": {"name": "final_answer"}}]
CAPABLE = {"data": [{"id": "model-a", "supported_parameters": ["tools", "tool_choice"]}]}


def test_tool_choice_is_sent_when_the_model_lists_it(make: Factory) -> None:
    client, provider, _ = make()
    provider.models = CAPABLE
    client.chat("agent_turn", HELLO, tools=TOOLS, tool_choice="required")
    assert json.loads(provider.requests[0].content)["tool_choice"] == "required"
    assert client.supports("model-a", "tool_choice")


def test_tool_choice_is_dropped_when_the_model_does_not_list_it(make: Factory) -> None:
    client, provider, _ = make()
    client.chat("agent_turn", HELLO, tools=TOOLS, tool_choice="required")
    assert json.loads(provider.requests[0].content)["tool_choice"] == "auto"
    assert not client.supports("model-a", "tool_choice")


def test_the_model_list_is_read_once(make: Factory) -> None:
    seen: list[str] = []
    client, provider, _ = make()
    provider.models = CAPABLE
    original = provider.__call__

    def counting(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return original(request)

    client._transport = httpx.MockTransport(counting)
    for text in ("one", "two"):
        client.chat("agent_turn", [{"role": "user", "content": text}], tools=TOOLS)
    assert seen.count("/v1/models") == 1


def test_a_forced_choice_is_cached_apart_from_auto(make: Factory) -> None:
    client, provider, _ = make()
    provider.models = CAPABLE
    client.chat("agent_turn", HELLO, tools=TOOLS)
    client.chat("agent_turn", HELLO, tools=TOOLS, tool_choice="required")
    client.chat("agent_turn", HELLO, tools=TOOLS, tool_choice="required")
    assert len(provider.requests) == 2


def test_unreadable_reply_is_an_error(make: Factory) -> None:
    client, _, _ = make(httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(LLMError):
        client.chat("judge", HELLO, allow_fallback=False)


class Grade(BaseModel):
    score: int


def test_structured_retries_once_on_schema_errors(make: Factory) -> None:
    client, provider, _ = make(ok("no json"), ok('```json\n{"score": 4}\n```'))
    value, _ = client.structured("judge", "Grade it", "text", Grade)
    assert value.score == 4
    assert len(provider.requests) == 2


def test_structured_gives_up_after_two_bad_replies(make: Factory) -> None:
    client, provider, _ = make(ok('{"score": "high"}'))
    with pytest.raises(LLMError):
        client.structured("judge", "Grade it", "text", Grade)
    assert len(provider.requests) == 2


def test_extract_json_finds_the_object() -> None:
    assert extract_json('Sure! {"a": {"b": 1}} Done.') == {"a": {"b": 1}}
    with pytest.raises(ValueError, match="no JSON"):
        extract_json("nothing here")


def test_secrets_never_reach_the_logs(make: Factory, caplog: pytest.LogCaptureFixture) -> None:
    client, _, _ = make(httpx.Response(500, text="echo not-a-real-key"), ok())
    with caplog.at_level("DEBUG"):
        client.chat("judge", HELLO)
    assert "not-a-real-key" not in caplog.text
    assert "not-a-real-key" not in repr(client.settings)


def test_settings_accept_provider_specific_names(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("POLLINATIONS_API_KEY", "k")
    monkeypatch.setenv("POLLINATIONS_MODEL", "m")
    monkeypatch.setenv("POLLINATIONS_BASE_URL", "https://host.test/v1/")
    settings = Settings()
    assert settings.llm_api_key.get_secret_value() == "k"
    assert settings.llm_model == "m"
    assert settings.llm_base_url == "https://host.test"


def test_chat_quota_counts_only_today(db: Session, make_user: Any) -> None:
    user = make_user("a@example.com")
    session = ChatSession(user_id=user.id)
    db.add(session)
    db.flush()
    for days in (0, 0, 2):
        when = datetime.now(UTC) - timedelta(days=days)
        db.add(ChatMessage(session_id=session.id, role="user", content="x", created_at=when))
    db.add(ChatMessage(session_id=session.id, role="assistant", content="y"))
    db.commit()
    quota = chat_quota(db, user, get_settings())
    assert (quota["used"], quota["remaining"]) == (2, quota["limit"] - 2)


def test_coordinators_get_a_higher_quota(db: Session, make_user: Any) -> None:
    settings = get_settings()
    student = chat_quota(db, make_user("a@example.com"), settings)
    coordinator = chat_quota(db, make_user("c@example.com", "coordinator"), settings)
    assert coordinator["limit"] > student["limit"]


@pytest.mark.live
def test_live_smoke(db: Session) -> None:
    """At most 5 calls: one plain, one cached repeat, one structured, one tool call."""
    client = LLMClient(get_settings().model_copy(update={"llm_daily_call_cap": 5}))
    if not client.settings.is_live:
        pytest.skip("no key configured")
    prompt = [{"role": "user", "content": "Reply with the single word: ready"}]
    first = client.chat("judge", prompt, allow_fallback=False, max_tokens=400)
    assert "ready" in first.content.lower()
    assert client.chat("judge", prompt, allow_fallback=False).mode == "cache"
    grade, _ = client.structured(
        "judge", "Return a score of 3.", "Grade this.", Grade, allow_fallback=False
    )
    assert grade.score == 3
    tool = {
        "type": "function",
        "function": {
            "name": "get_job",
            "description": "Full details of one posting",
            "parameters": {
                "type": "object",
                "properties": {"job_id": {"type": "integer"}},
                "required": ["job_id"],
            },
        },
    }
    asked = [{"role": "user", "content": "Use the tool to fetch the posting with id 7."}]
    reply = client.chat("agent_turn", asked, tools=[tool], allow_fallback=False)
    assert [c.name for c in reply.tool_calls] == ["get_job"]
    used = db.scalar(select(func.count()).select_from(LlmCall).where(LlmCall.is_live))
    assert used <= 5
