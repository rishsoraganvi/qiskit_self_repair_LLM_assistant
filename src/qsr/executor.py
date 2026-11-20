"""Run generated programs in a subprocess with a wall-clock timeout in a temp dir.

Model output is never exec()'d in-process.
"""
from __future__ import annotations

import ast
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path

from .dataset import Task

log = logging.getLogger(__name__)

PROGRAM_FILE = "program.py"


@dataclass(frozen=True)
class ExecResult:
    passed: bool
    stdout: str
    stderr: str
    timed_out: bool
    seconds: float
    returncode: int | None


def prompt_imports(prompt: str) -> str:
    """Top-level import statements from the task prompt (before the first def).

    Benchmark tests use names imported only in the prompt (e.g. `random_clifford`, `YGate`). The original
    benchmark executes prompt + completion, so those names always exist; we prepend the same imports so a
    model that rewrites the imports isn't failed by the test harness.
    """
    header_lines: list[str] = []
    for line in prompt.splitlines():
        if line.startswith(("def ", "async def ", "class ", "@")):
            break
        header_lines.append(line)
    header = "\n".join(header_lines)
    try:
        tree = ast.parse(header)
    except SyntaxError:
        return "\n".join(l for l in header_lines if l.startswith(("import ", "from ")))
    segments = [ast.get_source_segment(header, node) or "" for node in tree.body
                if isinstance(node, (ast.Import, ast.ImportFrom))]
    return "\n".join(s for s in segments if s)


def assemble_program(code: str, task: Task) -> str:
    """prompt imports + generated code + test + check(entry_point). Tests define check() but never call it."""
    imports = prompt_imports(task.prompt)
    head = f"{imports}\n\n" if imports else ""
    return f"{head}{code}\n\n{task.test}\n\ncheck({task.entry_point})\n"


def tail(text: str, n_chars: int = 4000) -> str:
    return text if len(text) <= n_chars else text[-n_chars:]


def _decode(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


WORKDIR_PLACEHOLDER = "<workdir>"


def _variants(path: str) -> list[str]:
    forms = {path, str(Path(path).resolve())}
    forms |= {f.replace("\\", "/") for f in forms}
    return sorted(forms, key=len, reverse=True)  # longest first so nested paths are replaced whole


def _scrub(text: str, tmp: str) -> str:
    """Replace machine-specific paths with fixed tokens so outputs (and repair prompts/cache keys) are stable
    across runs and clone locations: the temp dir, the virtualenv and the base Python install."""
    for path, token in ((tmp, WORKDIR_PLACEHOLDER), (sys.prefix, "<venv>"), (sys.base_prefix, "<python>")):
        for variant in _variants(path):
            text = text.replace(variant, token)
    return text


def run_program(program: str, timeout_s: float) -> ExecResult:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "MPLBACKEND": "Agg"}
    env.pop("GROQ_API_KEY", None)  # generated code never needs the key
    with tempfile.TemporaryDirectory(prefix="qsr_exec_") as tmp:
        result = _run_in(program, timeout_s, env, tmp)
        return replace(result, stdout=_scrub(result.stdout, tmp), stderr=_scrub(result.stderr, tmp))


def _run_in(program: str, timeout_s: float, env: dict, tmp: str) -> ExecResult:
    (Path(tmp) / PROGRAM_FILE).write_text(program, encoding="utf-8")
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", PROGRAM_FILE],
            cwd=tmp,
            capture_output=True,
            timeout=timeout_s,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        seconds = time.perf_counter() - start
        log.debug("Timed out after %.1fs", seconds)
        return ExecResult(False, _decode(exc.stdout), _decode(exc.stderr), True, seconds, None)
    return ExecResult(
        passed=proc.returncode == 0,
        stdout=_decode(proc.stdout),
        stderr=_decode(proc.stderr),
        timed_out=False,
        seconds=time.perf_counter() - start,
        returncode=proc.returncode,
    )


def execute(code: str, task: Task, timeout_s: float) -> ExecResult:
    return run_program(assemble_program(code, task), timeout_s)
