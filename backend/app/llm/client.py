"""The only place that talks to the LLM provider."""

import hashlib
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.models import LlmCache, LlmCall
from app.db.session import get_sessionmaker
from app.llm import mock
from app.llm.quota import reserve_live_call
from app.llm.types import (
    BudgetExceeded,
    LLMConfigError,
    LLMError,
    LLMResponse,
    Message,
    Purpose,
    ToolCall,
)

logger = logging.getLogger("app.llm")

MAX_RETRIES = 2
MAX_MESSAGE_CHARS = 8_000
MAX_RETRY_WAIT_S = 20.0


def clip(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + "\n[shortened]"


def prompt_hash(
    model: str, messages: list[Message], tools: list[dict[str, Any]] | None, temperature: float
) -> str:
    payload = json.dumps([model, messages, tools, temperature], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def extract_json(text: str) -> Any:
    """Read a JSON object from a reply that may be wrapped in prose or a code fence."""
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    candidate = fenced[1] if fenced else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("The reply contains no JSON object.")
    return json.loads(candidate[start : end + 1])


class LLMClient:
    def __init__(
        self,
        settings: Settings | None = None,
        sessions: sessionmaker[Session] | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self._sessions = sessions or get_sessionmaker()
        self._transport = transport
        self._sleep = sleep
        self._checked_models: set[str] = set()
        self._model_lock = threading.Lock()

    # ------------------------------------------------------------------ public

    def chat(
        self,
        purpose: Purpose,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 900,
        user_id: int | None = None,
        scope: str = "app",
        model: str | None = None,
        allow_fallback: bool = True,
    ) -> LLMResponse:
        messages = [self._clipped(m) for m in messages]
        if not self.settings.is_live:
            return self._mock(purpose, messages, tools, user_id, scope)

        model = model or self.settings.llm_model
        key = prompt_hash(model, messages, tools, temperature)
        cached = self._from_cache(key, purpose, user_id, scope, model)
        if cached:
            return cached
        try:
            self._check_model(model)
            return self._live(
                purpose, messages, tools, temperature, max_tokens, user_id, scope, model, key
            )
        except LLMError as exc:
            if not allow_fallback or isinstance(exc, LLMConfigError):
                raise
            response = self._mock(purpose, messages, tools, user_id, scope)
            response.degraded = "budget" if isinstance(exc, BudgetExceeded) else "provider"
            return response

    def structured[T: BaseModel](
        self,
        purpose: Purpose,
        system: str,
        user: str,
        schema: type[T],
        *,
        user_id: int | None = None,
        scope: str = "app",
        model: str | None = None,
        allow_fallback: bool = True,
        max_tokens: int = 1200,
    ) -> tuple[T, LLMResponse]:
        """Ask for JSON that fits `schema`. Retries once when validation fails."""
        instructions = (
            f"{system}\n\nReply with one JSON object and nothing else. It must fit this JSON "
            f"schema:\n{json.dumps(schema.model_json_schema(), separators=(',', ':'))}"
        )
        messages: list[Message] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user},
        ]
        problem: Exception | None = None
        for _ in range(2):
            response = self.chat(
                purpose,
                messages,
                user_id=user_id,
                scope=scope,
                model=model,
                allow_fallback=allow_fallback,
                max_tokens=max_tokens,
            )
            try:
                return schema.model_validate(extract_json(response.content)), response
            except (ValueError, ValidationError) as exc:
                problem = exc
                messages = [
                    *messages[:2],
                    {"role": "assistant", "content": response.content},
                    {
                        "role": "user",
                        "content": f"That did not fit the schema: {clip(str(exc), 600)}. "
                        "Send the corrected JSON object only.",
                    },
                ]
        raise LLMError("The assistant returned an unreadable answer twice.") from problem

    # ------------------------------------------------------------------ mock

    def _mock(
        self,
        purpose: Purpose,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        user_id: int | None,
        scope: str,
    ) -> LLMResponse:
        started = time.perf_counter()
        response = mock.complete(purpose, messages, tools)
        with self._sessions() as db:
            db.add(
                LlmCall(
                    user_id=user_id,
                    purpose=purpose,
                    scope=scope,
                    model="mock",
                    prompt_hash=prompt_hash("mock", messages, tools, 0.0),
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    status="ok",
                )
            )
            db.commit()
        return response

    # ------------------------------------------------------------------ cache

    def _from_cache(
        self, key: str, purpose: Purpose, user_id: int | None, scope: str, model: str
    ) -> LLMResponse | None:
        with self._sessions() as db:
            row = db.get(LlmCache, key)
            if row is None:
                return None
            db.add(
                LlmCall(
                    user_id=user_id,
                    purpose=purpose,
                    scope=scope,
                    model=model,
                    prompt_hash=key,
                    cache_hit=True,
                    status="ok",
                )
            )
            db.commit()
            return LLMResponse.model_validate({**row.response, "mode": "cache"})

    # ------------------------------------------------------------------ live

    def _http(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.settings.llm_base_url,
            timeout=self.settings.llm_timeout_s,
            transport=self._transport,
        )

    def _check_model(self, model: str) -> None:
        if not model:
            raise LLMConfigError("Set LLM_MODEL in .env before using live mode.")
        with self._model_lock:
            if model in self._checked_models:
                return
            try:
                with self._http() as http:
                    reply = http.get("/v1/models")
                    reply.raise_for_status()
                    listed = reply.json().get("data", [])
            except (httpx.HTTPError, ValueError) as exc:
                raise LLMError("The model list could not be read from the provider.") from exc
            names = {str(entry.get("id")) for entry in listed}
            names |= {str(alias) for entry in listed for alias in entry.get("aliases") or []}
            if model not in names:
                raise LLMConfigError(
                    "The model in LLM_MODEL is not offered by the provider any more. "
                    "Choose one from GET /v1/models."
                )
            self._checked_models.add(model)

    def _live(
        self,
        purpose: Purpose,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
        user_id: int | None,
        scope: str,
        model: str,
        key: str,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        for attempt in range(MAX_RETRIES + 1):
            with self._sessions() as db:
                call_id = reserve_live_call(
                    db,
                    self.settings,
                    user_id=user_id,
                    purpose=purpose,
                    scope=scope,
                    model=model,
                    prompt_hash=key,
                )
            started = time.perf_counter()
            wait: float | None = None
            try:
                with self._http() as http:
                    secret = self.settings.llm_api_key.get_secret_value()
                    reply = http.post(
                        "/v1/chat/completions",
                        json=body,
                        headers={"Authorization": f"Bearer {secret}"},
                    )
            except httpx.TransportError as exc:
                self._finish(call_id, started, f"network:{type(exc).__name__}"[:30])
                wait = 2.0**attempt
            else:
                if reply.status_code == 200:
                    response = self._parse(reply)
                    if response is None:
                        self._finish(call_id, started, "bad_response")
                        raise LLMError("The assistant sent an answer that could not be read.")
                    self._finish(call_id, started, "ok", response)
                    self._store(key, model, response, user_id)
                    return response
                self._finish(call_id, started, f"http_{reply.status_code}")
                if reply.status_code == 402:
                    raise BudgetExceeded("The provider balance is used up.")
                if reply.status_code == 429 or reply.status_code >= 500:
                    wait = self._retry_wait(reply, attempt)
                else:
                    raise LLMError(
                        "The assistant could not process this request "
                        f"(provider status {reply.status_code})."
                    )
            if attempt == MAX_RETRIES or wait is None:
                break
            self._sleep(wait)
        raise LLMError("The assistant is not reachable right now. Please try again shortly.")

    @staticmethod
    def _retry_wait(reply: httpx.Response, attempt: int) -> float | None:
        header = reply.headers.get("Retry-After") or reply.headers.get("RateLimit-Reset")
        if header:
            try:
                seconds = float(header)
            except ValueError:
                seconds = 2.0**attempt
            return seconds if seconds <= MAX_RETRY_WAIT_S else None
        return 2.0**attempt

    @staticmethod
    def _parse(reply: httpx.Response) -> LLMResponse | None:
        try:
            data = reply.json()
            message = data["choices"][0]["message"]
            usage = data.get("usage") or {}
            calls = [
                ToolCall(
                    id=str(item.get("id") or f"call_{index}"),
                    name=item["function"]["name"],
                    arguments=item["function"].get("arguments") or "{}",
                )
                for index, item in enumerate(message.get("tool_calls") or [])
            ]
            return LLMResponse(
                content=message.get("content") or "",
                tool_calls=calls,
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                mode="live",
            )
        except (ValueError, KeyError, IndexError, TypeError):
            return None

    def _finish(
        self, call_id: int, started: float, status: str, response: LLMResponse | None = None
    ) -> None:
        with self._sessions() as db:
            call = db.get(LlmCall, call_id)
            if call is None:
                return
            call.status = status
            call.latency_ms = int((time.perf_counter() - started) * 1000)
            if response:
                call.input_tokens = response.input_tokens
                call.output_tokens = response.output_tokens
            db.commit()
        logger.info("llm call", extra={"status": status, "purpose": call.purpose})

    def _store(self, key: str, model: str, response: LLMResponse, user_id: int | None) -> None:
        if not response.content and not response.tool_calls:
            return
        with self._sessions() as db:
            db.execute(
                insert(LlmCache)
                .values(
                    prompt_hash=key, model=model, user_id=user_id, response=response.model_dump()
                )
                .on_conflict_do_nothing()
            )
            db.commit()

    @staticmethod
    def _clipped(message: Message) -> Message:
        content = message.get("content")
        if isinstance(content, str) and len(content) > MAX_MESSAGE_CHARS:
            return {**message, "content": clip(content)}
        return message


@lru_cache
def get_llm() -> LLMClient:
    return LLMClient()
