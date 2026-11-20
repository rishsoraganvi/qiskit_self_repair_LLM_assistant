from dataclasses import replace
from types import SimpleNamespace

import groq
import httpx
import pytest

from qsr.config import Config, Paths
from qsr.llm import BudgetExceeded, LLMClient, LLMError, RateLimiter, RequestParams, cache_key

MSGS = [{"role": "system", "content": "sys"}, {"role": "user", "content": "do it"}]
PARAMS = RequestParams("openai/gpt-oss-120b", 0.0, 4096, "medium")


def make_cfg(tmp_path, **kw) -> Config:
    paths = Paths(root=tmp_path, data=tmp_path / "data", raw=tmp_path / "raw",
                  cache=tmp_path / "cache", runs=tmp_path / "runs", results=tmp_path / "results")
    return replace(Config(), paths=paths, rpm_limit=None, tpm_limit=None, daily_token_budget=None,
                   model="openai/gpt-oss-120b", temperature=0.0, reasoning_effort="medium",
                   max_completion_tokens=4096, **kw)


def fake_completion(content="```python\ndef f(): pass\n```", p=100, c=50):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, reasoning="hidden"), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=p, completion_tokens=c),
    )


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def rate_limit_error(retry_after=None):
    headers = {"retry-after": str(retry_after)} if retry_after is not None else {}
    resp = httpx.Response(429, headers=headers, request=httpx.Request("POST", "https://api.groq.com"))
    return groq.RateLimitError("rate limited", response=resp, body=None)


# --- cache key stability ---------------------------------------------------

def test_cache_key_stable_and_sensitive():
    k = cache_key(PARAMS, MSGS, 0)
    assert k == cache_key(PARAMS, [dict(m) for m in MSGS], 0)
    assert len(k) == 64
    assert k != cache_key(PARAMS, MSGS, 1)
    assert k != cache_key(replace(PARAMS, temperature=0.5), MSGS, 0)
    assert k != cache_key(replace(PARAMS, reasoning_effort="low"), MSGS, 0)
    assert k != cache_key(replace(PARAMS, max_completion_tokens=1024), MSGS, 0)
    assert k != cache_key(replace(PARAMS, model="other"), MSGS, 0)
    assert k != cache_key(PARAMS, MSGS[:1], 0)


def test_cache_key_known_value():
    # Guards against accidental changes to key derivation (would silently invalidate the cache).
    assert cache_key(PARAMS, MSGS, 0) == "7ecfd2d0bf7a12842d8773618728b0b11396d0bc7d044b67b64cc9cf7d562de4"


# --- client: cache, params, retries, budget --------------------------------

def test_second_call_is_cache_hit(tmp_path):
    fake = FakeClient([fake_completion()])
    llm = LLMClient(make_cfg(tmp_path), client=fake, sleep=lambda s: None)
    r1 = llm.complete(MSGS, attempt=0, task_id="t")
    r2 = llm.complete(MSGS, attempt=0, task_id="t")
    assert not r1.cache_hit and r2.cache_hit
    assert r1.content == r2.content and r2.prompt_tokens == 100
    assert len(fake.calls) == 1 and llm.api_calls == 1 and llm.cache_hits == 1
    # A fresh client over the same cache dir also makes zero calls.
    fake2 = FakeClient([])
    assert LLMClient(make_cfg(tmp_path), client=fake2).complete(MSGS, 0).cache_hit
    assert fake2.calls == []


def test_request_parameters(tmp_path):
    fake = FakeClient([fake_completion()])
    LLMClient(make_cfg(tmp_path), client=fake).complete(MSGS, 0)
    call = fake.calls[0]
    assert call["model"] == "openai/gpt-oss-120b"
    assert call["reasoning_effort"] == "medium"
    assert call["max_completion_tokens"] == 4096
    assert call["include_reasoning"] is False
    assert call["temperature"] == 0.0


def test_retry_honors_retry_after(tmp_path):
    sleeps: list[float] = []
    fake = FakeClient([rate_limit_error(7), fake_completion()])
    r = LLMClient(make_cfg(tmp_path), client=fake, sleep=sleeps.append).complete(MSGS, 0)
    assert r.content and sleeps == [7.0]


def test_retry_backoff_then_give_up(tmp_path):
    sleeps: list[float] = []
    cfg = make_cfg(tmp_path)
    fake = FakeClient([rate_limit_error()] * (cfg.max_retries + 1))
    with pytest.raises(LLMError):
        LLMClient(cfg, client=fake, sleep=sleeps.append).complete(MSGS, 0)
    assert len(sleeps) == cfg.max_retries
    assert all(b >= a - 1 for a, b in zip(sleeps, sleeps[1:]))  # roughly increasing with jitter


def test_non_retryable_error_fails_fast(tmp_path):
    resp = httpx.Response(400, request=httpx.Request("POST", "https://api.groq.com"))
    fake = FakeClient([groq.BadRequestError("bad", response=resp, body=None)])
    with pytest.raises(LLMError):
        LLMClient(make_cfg(tmp_path), client=fake, sleep=lambda s: None).complete(MSGS, 0)
    assert len(fake.calls) == 1


def test_budget_guard(tmp_path):
    cfg = replace(make_cfg(tmp_path), daily_token_budget=1200)
    fake = FakeClient([fake_completion(p=900, c=200), fake_completion()])
    llm = LLMClient(cfg, client=fake)
    llm.complete(MSGS, 0)  # uses 1100 tokens
    with pytest.raises(BudgetExceeded):
        llm.complete(MSGS, 1)
    assert len(fake.calls) == 1
    assert llm.complete(MSGS, 0).cache_hit  # cache hits are free even over budget


def test_missing_key_message(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        LLMClient(make_cfg(tmp_path)).complete(MSGS, 0)


# --- rate limiter ------------------------------------------------------------

class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.slept.append(s)
        self.now += s


def test_rpm_limit():
    t = FakeTime()
    rl = RateLimiter(rpm=2, tpm=None, clock=t.clock, sleep=t.sleep)
    rl.acquire(1)
    t.now = 10
    rl.acquire(1)
    assert t.slept == []
    rl.acquire(1)  # must wait until first request leaves the window (t=60)
    assert t.now == pytest.approx(60.0)


def test_tpm_limit():
    t = FakeTime()
    rl = RateLimiter(rpm=None, tpm=1000, clock=t.clock, sleep=t.sleep)
    rl.acquire(600)
    t.now = 5
    rl.acquire(300)
    assert t.slept == []
    rl.acquire(300)  # 600+300+300 > 1000 -> wait for the 600 to expire at t=60
    assert t.now == pytest.approx(60.0)


def test_tpm_oversized_request_passes_when_window_empty():
    t = FakeTime()
    rl = RateLimiter(rpm=None, tpm=100, clock=t.clock, sleep=t.sleep)
    rl.acquire(5000)
    assert t.slept == []


def test_record_actual_replaces_estimate():
    t = FakeTime()
    rl = RateLimiter(rpm=None, tpm=1000, clock=t.clock, sleep=t.sleep)
    rl.acquire(900)
    rl.record_actual(900, 100)
    rl.acquire(800)
    assert t.slept == []


def test_no_limits_never_sleeps():
    t = FakeTime()
    rl = RateLimiter(rpm=None, tpm=None, clock=t.clock, sleep=t.sleep)
    for _ in range(100):
        rl.acquire(10_000)
    assert t.slept == []
