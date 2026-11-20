"""Central configuration. Values come from environment (.env) with defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _env_int(name: str, default: int | None) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    return float(value) if value else default


@dataclass(frozen=True)
class Paths:
    root: Path = REPO_ROOT
    data: Path = REPO_ROOT / "data"
    raw: Path = REPO_ROOT / "data" / "raw"
    cache: Path = REPO_ROOT / "cache"
    runs: Path = REPO_ROOT / "runs"
    results: Path = REPO_ROOT / "results"

    @property
    def raw_tasks(self) -> Path:
        return self.raw / "qiskit_humaneval.jsonl"

    @property
    def valid_tasks(self) -> Path:
        return self.data / "valid_tasks.json"

    @property
    def invalid_tasks(self) -> Path:
        return self.data / "invalid_tasks.json"

    @property
    def subset(self) -> Path:
        return self.data / "subset.json"

    @property
    def attempts(self) -> Path:
        return self.runs / "attempts.jsonl"


@dataclass(frozen=True)
class Config:
    # Benchmark (verified 2026-11-19, see docs/VERIFIED.md)
    dataset_name: str = "Qiskit/qiskit_humaneval"
    dataset_split: str = "test"

    # LLM (verified against Groq docs, see docs/VERIFIED.md)
    model: str = field(default_factory=lambda: _env_str("QSR_MODEL", "openai/gpt-oss-120b"))
    temperature: float = field(default_factory=lambda: _env_float("QSR_TEMPERATURE", 0.0))
    reasoning_effort: str = field(default_factory=lambda: _env_str("QSR_REASONING_EFFORT", "low"))  # evaluation setting, see docs/VERIFIED.md
    max_completion_tokens: int = field(
        default_factory=lambda: _env_int("QSR_MAX_COMPLETION_TOKENS", 4096) or 4096
    )

    # Rate limits: user supplies current free-tier numbers in .env (never hardcoded).
    rpm_limit: int | None = field(default_factory=lambda: _env_int("RPM_LIMIT", None))
    tpm_limit: int | None = field(default_factory=lambda: _env_int("TPM_LIMIT", None))
    daily_token_budget: int | None = field(default_factory=lambda: _env_int("DAILY_TOKEN_BUDGET", None))
    max_retries: int = 6

    # Execution
    exec_timeout_s: float = field(default_factory=lambda: _env_float("QSR_EXEC_TIMEOUT_S", 60.0))
    stderr_tail_chars: int = 4000

    # Evaluation
    seed: int = 42
    subset_size: int = 30
    max_repairs: int = 3

    paths: Paths = field(default_factory=Paths)


def get_config() -> Config:
    return Config()
