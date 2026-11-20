"""Repair rounds 1..k for tasks whose latest attempt failed. Attempt 0 is reused, never regenerated."""
from __future__ import annotations

import logging

from .attempts import AttemptStore, check_no_regressions, run_attempt
from .baseline import PhaseResult
from .config import Config
from .llm import BudgetExceeded, LLMClient
from .prompts import repair_messages
from .sample import load_subset

log = logging.getLogger(__name__)


class MissingBaseline(RuntimeError):
    pass


def run_repair(cfg: Config, max_repairs: int, llm: LLMClient | None = None) -> PhaseResult:
    tasks = load_subset(cfg)
    store = AttemptStore(cfg.paths.attempts)
    missing = [t.task_id for t in tasks if store.get(t.task_id, 0) is None]
    if missing:
        raise MissingBaseline(f"{len(missing)} tasks have no attempt 0; run `python -m qsr baseline` first.")
    llm = llm or LLMClient(cfg)
    stopped = ""
    for task in tasks:
        last = store.latest(task.task_id)
        while last is not None and not last.passed and last.attempt < max_repairs:
            k = last.attempt + 1
            messages = repair_messages(task.prompt, last.code, last.stderr_tail)
            try:
                attempt = run_attempt(cfg, llm, task, messages, k)
            except BudgetExceeded as exc:
                stopped = str(exc)
                break
            store.add(attempt)
            log.info("%s attempt %d: %s", task.task_id, k, "PASS" if attempt.passed else attempt.error_class)
            last = attempt
        if stopped:
            log.warning("Stopping: %s", stopped)
            break

    ids = [t.task_id for t in tasks]
    check_no_regressions(store, ids)
    latest = {tid: store.latest(tid) for tid in ids}
    remaining = [tid for tid, a in latest.items() if a and not a.passed and a.attempt < max_repairs]
    return PhaseResult(
        total=len(tasks),
        passed=sum(1 for a in latest.values() if a and a.passed),
        done=len(tasks) - len(remaining),
        remaining=remaining,
        api_calls=llm.api_calls,
        cache_hits=llm.cache_hits,
        stopped_reason=stopped,
    )
