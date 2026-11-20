"""Seeded sample of N valid tasks, frozen in data/subset.json (never resampled)."""
from __future__ import annotations

import json
import logging
import random

from .config import Config
from .dataset import Task, read_tasks, save_tasks

log = logging.getLogger(__name__)


class SubsetError(RuntimeError):
    pass


def _task_number(task: Task) -> int:
    return int(task.task_id.rsplit("/", 1)[-1])


def draw_sample(valid: list[Task], n: int, seed: int) -> list[Task]:
    if len(valid) < n:
        raise SubsetError(f"Only {len(valid)} valid tasks; need {n}.")
    ordered = sorted(valid, key=_task_number)  # stable order independent of validation order
    chosen = random.Random(seed).sample(ordered, n)
    return sorted(chosen, key=_task_number)


def _meta_path(cfg: Config):
    return cfg.paths.data / "subset_meta.json"


def sample(cfg: Config, n: int, seed: int) -> list[Task]:
    p = cfg.paths
    if p.subset.exists():
        meta = json.loads(_meta_path(cfg).read_text(encoding="utf-8")) if _meta_path(cfg).exists() else {}
        if meta and (meta.get("n"), meta.get("seed")) != (n, seed):
            raise SubsetError(
                f"data/subset.json is frozen with n={meta.get('n')}, seed={meta.get('seed')}; refusing to resample."
            )
        log.info("Using frozen subset %s", p.subset)
        return read_tasks(p.subset)
    if not p.valid_tasks.exists():
        raise SubsetError("data/valid_tasks.json not found; run `python -m qsr validate` first.")
    chosen = draw_sample(read_tasks(p.valid_tasks), n, seed)
    save_tasks(p.subset, chosen)
    _meta_path(cfg).write_text(json.dumps({"n": n, "seed": seed}, indent=2), encoding="utf-8")
    return chosen


def load_subset(cfg: Config) -> list[Task]:
    if not cfg.paths.subset.exists():
        raise SubsetError("data/subset.json not found; run `python -m qsr sample` first.")
    return read_tasks(cfg.paths.subset)
