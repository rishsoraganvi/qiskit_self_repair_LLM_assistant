"""Load Qiskit HumanEval and cache it locally as JSONL."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Task:
    task_id: str
    prompt: str
    canonical_solution: str
    test: str
    entry_point: str
    difficulty_scale: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(
            task_id=d["task_id"],
            prompt=d["prompt"],
            canonical_solution=d["canonical_solution"],
            test=d["test"],
            entry_point=d["entry_point"],
            difficulty_scale=d.get("difficulty_scale") or "",
        )

    def to_dict(self) -> dict:
        return asdict(self)


ROWS_API = "https://datasets-server.huggingface.co/rows"
PAGE_SIZE = 100  # API maximum


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "qsr-harness"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _download(cfg: Config) -> list[dict]:
    """Fetch all rows via the HF dataset-viewer JSON API (avoids pyarrow, which breaks on long Windows paths)."""
    log.info("Downloading %s (split=%s)", cfg.dataset_name, cfg.dataset_split)
    rows: list[dict] = []
    total: int | None = None
    while total is None or len(rows) < total:
        query = urllib.parse.urlencode(
            {"dataset": cfg.dataset_name, "config": "default", "split": cfg.dataset_split,
             "offset": len(rows), "length": PAGE_SIZE}
        )
        page = _fetch_json(f"{ROWS_API}?{query}")
        total = page["num_rows_total"]
        batch = [r["row"] for r in page["rows"]]
        if not batch:
            raise RuntimeError(f"Empty page at offset {len(rows)} of {total}")
        rows.extend(batch)
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_tasks(cfg: Config) -> list[Task]:
    """Return all benchmark tasks, downloading once and reading the local cache after."""
    path = cfg.paths.raw_tasks
    if not path.exists():
        _write_jsonl(path, _download(cfg))
    tasks = [Task.from_dict(r) for r in _read_jsonl(path)]
    log.info("Loaded %d tasks from %s", len(tasks), path)
    return tasks


def save_tasks(path: Path, tasks: list[Task]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([t.to_dict() for t in tasks], indent=2, ensure_ascii=False), encoding="utf-8")


def read_tasks(path: Path) -> list[Task]:
    return [Task.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]
