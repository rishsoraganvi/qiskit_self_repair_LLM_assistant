"""Attempt records and the append-only runs/attempts.jsonl store."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .classify import classify
from .config import Config
from .dataset import Task
from .executor import ExecResult, execute, tail
from .extract import extract_code, extraction_note
from .llm import LLMClient, Messages


@dataclass(frozen=True)
class Attempt:
    task_id: str
    attempt: int
    code: str
    passed: bool
    error_class: str
    stderr_tail: str
    exec_seconds: float
    prompt_tokens: int
    completion_tokens: int
    cache_hit: bool
    timed_out: bool = False
    note: str = ""
    finish_reason: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Attempt":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


class AttemptStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._by_key: dict[tuple[str, int], Attempt] = {}
        if path.exists():
            with path.open(encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        a = Attempt.from_dict(json.loads(line))
                        self._by_key[(a.task_id, a.attempt)] = a

    def get(self, task_id: str, attempt: int) -> Attempt | None:
        return self._by_key.get((task_id, attempt))

    def for_task(self, task_id: str) -> list[Attempt]:
        return sorted((a for (t, _), a in self._by_key.items() if t == task_id), key=lambda a: a.attempt)

    def latest(self, task_id: str) -> Attempt | None:
        attempts = self.for_task(task_id)
        return attempts[-1] if attempts else None

    def all(self) -> list[Attempt]:
        return sorted(self._by_key.values(), key=lambda a: (a.task_id, a.attempt))

    def add(self, attempt: Attempt) -> None:
        if (attempt.task_id, attempt.attempt) in self._by_key:
            raise ValueError(f"duplicate attempt {attempt.task_id} #{attempt.attempt}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(attempt), ensure_ascii=False) + "\n")
        self._by_key[(attempt.task_id, attempt.attempt)] = attempt


def error_tail(result: ExecResult, timeout_s: float, n_chars: int) -> str:
    """Last part of the execution output that goes into the repair prompt."""
    if result.timed_out:
        return tail(f"Execution timed out after {timeout_s:.0f} seconds.\n{result.stderr}".strip(), n_chars)
    text = result.stderr.strip() or result.stdout.strip() or f"Process exited with code {result.returncode}."
    return tail(text, n_chars)


def run_attempt(cfg: Config, llm: LLMClient, task: Task, messages: Messages, attempt_no: int) -> Attempt:
    """Generate -> extract -> execute (subprocess) -> classify."""
    response = llm.complete(messages, attempt=attempt_no, task_id=task.task_id)
    code = extract_code(response.content)
    note = extraction_note(code, task.entry_point)
    result = execute(code, task, cfg.exec_timeout_s)
    return Attempt(
        task_id=task.task_id,
        attempt=attempt_no,
        code=code,
        passed=result.passed,
        error_class=classify(result, note),
        stderr_tail="" if result.passed else error_tail(result, cfg.exec_timeout_s, cfg.stderr_tail_chars),
        exec_seconds=round(result.seconds, 3),
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        cache_hit=response.cache_hit,
        timed_out=result.timed_out,
        note=note,
        finish_reason=response.finish_reason,
    )


def check_no_regressions(store: AttemptStore, task_ids: list[str]) -> None:
    """No task may have any attempt after a passing one (attempt 0 is reused, stop on pass)."""
    for tid in task_ids:
        seen_pass = False
        for a in store.for_task(tid):
            if seen_pass:
                raise AssertionError(f"{tid}: attempt {a.attempt} exists after a passing attempt")
            seen_pass = seen_pass or a.passed
