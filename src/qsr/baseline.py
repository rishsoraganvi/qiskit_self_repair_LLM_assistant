"""Attempt 0: one generation per task, no feedback."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .attempts import AttemptStore, run_attempt
from .config import Config
from .llm import BudgetExceeded, LLMClient
from .prompts import generation_messages
from .sample import load_subset

log = logging.getLogger(__name__)


@dataclass
class PhaseResult:
    total: int
    passed: int
    done: int
    remaining: list[str]
    api_calls: int
    cache_hits: int
    stopped_reason: str = ""


def run_baseline(cfg: Config, llm: LLMClient | None = None) -> PhaseResult:
    tasks = load_subset(cfg)
    store = AttemptStore(cfg.paths.attempts)
    llm = llm or LLMClient(cfg)
    stopped = ""
    for i, task in enumerate(tasks, 1):
        if store.get(task.task_id, 0) is not None:
            continue
        try:
            attempt = run_attempt(cfg, llm, task, generation_messages(task.prompt), 0)
        except BudgetExceeded as exc:
            stopped = str(exc)
            log.warning("Stopping: %s", exc)
            break
        store.add(attempt)
        log.info("[%d/%d] %s attempt 0: %s", i, len(tasks), task.task_id,
                 "PASS" if attempt.passed else attempt.error_class)
    zero = [store.get(t.task_id, 0) for t in tasks]
    return PhaseResult(
        total=len(tasks),
        passed=sum(1 for a in zero if a and a.passed),
        done=sum(1 for a in zero if a),
        remaining=[t.task_id for t, a in zip(tasks, zero) if a is None],
        api_calls=llm.api_calls,
        cache_hits=llm.cache_hits,
        stopped_reason=stopped,
    )
