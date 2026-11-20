"""The only place that talks to Groq: on-disk cache, rate limiter, retry/backoff, budget guard, token log."""
from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import Config

log = logging.getLogger(__name__)

Messages = list[dict[str, str]]


class BudgetExceeded(RuntimeError):
    """Daily token budget would be exceeded; stop cleanly and resume later."""


class LLMError(RuntimeError):
    """Non-retryable failure or retries exhausted."""


@dataclass(frozen=True)
class LLMResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    cache_hit: bool
    finish_reason: str = ""


@dataclass(frozen=True)
class RequestParams:
    model: str
    temperature: float
    max_completion_tokens: int
    reasoning_effort: str


def cache_key(params: RequestParams, messages: Messages, attempt: int) -> str:
    """sha256(model + messages + temperature + max tokens + reasoning effort + attempt index)."""
    payload = {
        "model": params.model,
        "messages": messages,
        "temperature": params.temperature,
        "max_completion_tokens": params.max_completion_tokens,
        "reasoning_effort": params.reasoning_effort,
        "attempt": attempt,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def estimate_tokens(messages: Messages) -> int:
    """Rough pre-call estimate (~4 chars/token) for limiter and budget checks."""
    return sum(len(m["content"]) for m in messages) // 4 + 16 * len(messages)


class RateLimiter:
    """Sliding 60 s windows for requests (RPM) and tokens (TPM). Clock and sleep are injectable."""

    WINDOW_S = 60.0

    def __init__(
        self,
        rpm: int | None,
        tpm: int | None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.rpm, self.tpm = rpm, tpm
        self.clock, self.sleep = clock, sleep
        self._requests: deque[float] = deque()
        self._tokens: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> None:
        while self._requests and now - self._requests[0] >= self.WINDOW_S:
            self._requests.popleft()
        while self._tokens and now - self._tokens[0][0] >= self.WINDOW_S:
            self._tokens.popleft()

    def _wait_needed(self, now: float, tokens: int) -> float:
        waits = [0.0]
        if self.rpm and len(self._requests) >= self.rpm:
            waits.append(self._requests[0] + self.WINDOW_S - now)
        if self.tpm and self._tokens:
            used = sum(t for _, t in self._tokens)
            need = min(tokens, self.tpm)  # a single huge request still gets through once the window is empty
            if used + need > self.tpm:
                freed, wait = 0, 0.0
                for ts, t in self._tokens:
                    freed += t
                    wait = ts + self.WINDOW_S - now
                    if used - freed + need <= self.tpm:
                        break
                waits.append(wait)
        return max(waits)

    def acquire(self, tokens: int) -> float:
        """Block until a request of `tokens` fits; returns seconds slept. Records the request."""
        slept = 0.0
        while True:
            now = self.clock()
            self._prune(now)
            wait = self._wait_needed(now, tokens)
            if wait <= 0:
                break
            log.info("Rate limiter: sleeping %.1fs", wait)
            self.sleep(wait)
            slept += wait
        now = self.clock()
        self._requests.append(now)
        self._tokens.append((now, tokens))
        return slept

    def record_actual(self, estimated: int, actual: int) -> None:
        """Replace the most recent token reservation with the actual usage."""
        if self._tokens:
            ts, t = self._tokens[-1]
            if t == estimated:
                self._tokens[-1] = (ts, actual)


class ResponseCache:
    """One JSON file per call under cache/, keyed by cache_key."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory

    def path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> dict | None:
        p = self.path(key)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put(self, key: str, record: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path(key))


class UsageLog:
    """Append-only JSONL of real (non-cached) API calls; source of API-call counts and daily budget."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def tokens_on(self, day: str) -> int:
        return sum(e["prompt_tokens"] + e["completion_tokens"] for e in self.entries() if e["date"] == day)

    def append(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def _retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    value = headers.get("retry-after") if hasattr(headers, "get") else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _is_retryable(exc: Exception) -> bool:
    import groq

    if isinstance(exc, (groq.RateLimitError, groq.APIConnectionError, groq.APITimeoutError, groq.InternalServerError)):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


def _make_groq_client(api_key: str | None) -> Any:
    import groq

    if not api_key:
        raise LLMError("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")
    return groq.Groq(api_key=api_key, max_retries=0)  # retries handled here


class LLMClient:
    def __init__(
        self,
        cfg: Config,
        client: Any | None = None,
        api_key: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cfg = cfg
        self.params = RequestParams(cfg.model, cfg.temperature, cfg.max_completion_tokens, cfg.reasoning_effort)
        self.cache = ResponseCache(cfg.paths.cache)
        self.usage = UsageLog(cfg.paths.runs / "llm_calls.jsonl")
        self.limiter = RateLimiter(cfg.rpm_limit, cfg.tpm_limit, clock=clock, sleep=sleep)
        self.sleep = sleep
        self._client = client
        self._api_key = api_key
        self.api_calls = 0
        self.cache_hits = 0

    @property
    def client(self) -> Any:
        if self._client is None:
            import os

            self._client = _make_groq_client(self._api_key or os.getenv("GROQ_API_KEY"))
        return self._client

    def complete(self, messages: Messages, attempt: int, task_id: str = "") -> LLMResponse:
        key = cache_key(self.params, messages, attempt)
        cached = self.cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            log.debug("Cache hit %s (%s attempt %d)", key[:12], task_id, attempt)
            return LLMResponse(cached["content"], cached["prompt_tokens"], cached["completion_tokens"], True,
                               cached.get("finish_reason", ""))

        estimate = estimate_tokens(messages) + self.params.max_completion_tokens // 4
        self._check_budget(estimate)
        response = self._call_with_retries(messages, estimate)
        self.cache.put(key, {**asdict(response), "cache_hit": False, "key": key, "request": {
            **asdict(self.params), "messages": messages, "attempt": attempt}})
        self.usage.append({
            "date": UsageLog.today(), "key": key, "task_id": task_id, "attempt": attempt,
            "prompt_tokens": response.prompt_tokens, "completion_tokens": response.completion_tokens,
        })
        log.info("LLM call %s attempt %d: %d prompt + %d completion tokens (%s)", task_id, attempt,
                 response.prompt_tokens, response.completion_tokens, response.finish_reason)
        return response

    def _check_budget(self, estimate: int) -> None:
        budget = self.cfg.daily_token_budget
        if not budget:
            return
        used = self.usage.tokens_on(UsageLog.today())
        if used + estimate > budget:
            raise BudgetExceeded(f"Daily token budget {budget} would be exceeded (used {used}, next ~{estimate}).")

    def _call_with_retries(self, messages: Messages, estimate: int) -> LLMResponse:
        max_retries = self.cfg.max_retries
        client = self.client  # raises LLMError early if no API key
        for attempt in range(max_retries + 1):
            self.limiter.acquire(estimate)
            try:
                raw = client.chat.completions.create(
                    model=self.params.model,
                    messages=messages,
                    temperature=self.params.temperature,
                    max_completion_tokens=self.params.max_completion_tokens,
                    reasoning_effort=self.params.reasoning_effort,
                    include_reasoning=False,
                )
            except Exception as exc:  # noqa: BLE001 - classified below
                if not _is_retryable(exc) or attempt == max_retries:
                    raise LLMError(f"Groq call failed: {exc!r}") from exc
                delay = _retry_after(exc)
                if delay is None:
                    delay = min(60.0, 2.0 ** attempt) + random.uniform(0, 1)
                log.warning("Retryable error (%s); retry %d/%d in %.1fs", type(exc).__name__,
                            attempt + 1, max_retries, delay)
                self.sleep(delay)
                continue
            self.api_calls += 1
            response = _parse(raw)
            self.limiter.record_actual(estimate, response.prompt_tokens + response.completion_tokens)
            return response
        raise LLMError("unreachable")


def _parse(raw: Any) -> LLMResponse:
    choice = raw.choices[0]
    usage = getattr(raw, "usage", None)
    return LLMResponse(
        content=choice.message.content or "",  # reasoning field is ignored by design
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        cache_hit=False,
        finish_reason=str(getattr(choice, "finish_reason", "") or ""),
    )
