"""Run every canonical solution against its test on the installed Qiskit; split valid/invalid."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from .config import Config
from .dataset import Task, load_tasks, save_tasks
from .executor import ExecResult, execute

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvalidTask:
    task_id: str
    entry_point: str
    reason: str
    timed_out: bool
    stderr_tail: str


def canonical_code(task: Task) -> str:
    return task.prompt + task.canonical_solution


def failure_reason(result: ExecResult) -> str:
    if result.timed_out:
        return "timeout"
    lines = [ln.strip() for ln in result.stderr.strip().splitlines() if ln.strip()]
    return lines[-1][:300] if lines else f"exit code {result.returncode}"


def validate_task(task: Task, timeout_s: float) -> tuple[Task, ExecResult]:
    return task, execute(canonical_code(task), task, timeout_s)


def run_validation(tasks: list[Task], timeout_s: float, workers: int) -> tuple[list[Task], list[InvalidTask]]:
    valid: list[Task] = []
    invalid: list[InvalidTask] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for task, res in pool.map(lambda t: validate_task(t, timeout_s), tasks):
            if res.passed:
                valid.append(task)
            else:
                invalid.append(
                    InvalidTask(task.task_id, task.entry_point, failure_reason(res), res.timed_out, res.stderr[-2000:])
                )
                log.info("INVALID %s: %s", task.task_id, failure_reason(res))
    return valid, invalid


def validate(cfg: Config, force: bool = False, workers: int | None = None) -> tuple[list[Task], list[InvalidTask]]:
    """Validate all tasks; reuse previous results unless force=True (resumable, cache-first)."""
    p = cfg.paths
    if not force and p.valid_tasks.exists() and p.invalid_tasks.exists():
        from .dataset import read_tasks

        log.info("Using cached validation results (pass --force to rerun)")
        invalid_raw = json.loads(p.invalid_tasks.read_text(encoding="utf-8"))
        return read_tasks(p.valid_tasks), [InvalidTask(**d) for d in invalid_raw]

    tasks = load_tasks(cfg)
    # Sequential by default: Aer already multithreads, and parallel runs caused spurious crashes/timeouts.
    n_workers = workers or 1
    log.info("Validating %d tasks with %d workers (timeout %.0fs)", len(tasks), n_workers, cfg.exec_timeout_s)
    valid, invalid = run_validation(tasks, cfg.exec_timeout_s, n_workers)
    save_tasks(p.valid_tasks, valid)
    p.invalid_tasks.write_text(json.dumps([asdict(i) for i in invalid], indent=2), encoding="utf-8")
    return valid, invalid
