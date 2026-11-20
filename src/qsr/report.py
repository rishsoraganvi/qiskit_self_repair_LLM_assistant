"""Aggregate runs/attempts.jsonl into results.csv, summary.md and plots."""
from __future__ import annotations

import json
import logging
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .attempts import Attempt, AttemptStore, check_no_regressions
from .classify import ERROR_CLASSES
from .config import Config
from .llm import UsageLog
from .sample import load_subset

log = logging.getLogger(__name__)

# Reference categorical palette (dataviz skill): slot 1 blue, slot 2 orange; light surface and ink.
BLUE, ORANGE = "#2a78d6", "#eb6834"
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


class ReportError(RuntimeError):
    pass


@dataclass
class TaskOutcome:
    task_id: str
    first_pass: int | None  # attempt index of first pass, None if never
    class_at_0: str
    final_class: str
    n_attempts: int


@dataclass
class Summary:
    n: int
    max_repairs: int
    baseline_pass: int
    pass_by_k: dict[int, int]
    fixed_by_round: dict[int, int]
    never_fixed: list[str]
    mix_at_0: dict[str, int]
    mix_final: dict[str, int]
    fix_rate_by_class: dict[str, tuple[int, int]]
    prompt_tokens: int
    completion_tokens: int
    api_calls: int
    attempts_total: int
    cache_hit_attempts: int
    broken_by_loop: int = 0
    outcomes: list[TaskOutcome] = field(default_factory=list)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def fmt(k: int, n: int) -> str:
    return f"{k}/{n} = {100 * k / n:.1f}%" if n else f"{k}/0"


def task_outcome(task_id: str, attempts: list[Attempt]) -> TaskOutcome:
    first_pass = next((a.attempt for a in attempts if a.passed), None)
    return TaskOutcome(task_id, first_pass, attempts[0].error_class, attempts[-1].error_class, len(attempts))


def summarize(outcomes: list[TaskOutcome], attempts: list[Attempt], max_repairs: int, api_calls: int) -> Summary:
    n = len(outcomes)
    failed0 = [o for o in outcomes if o.first_pass != 0]
    fix_rate: dict[str, tuple[int, int]] = {}
    for cls in ERROR_CLASSES:
        group = [o for o in failed0 if o.class_at_0 == cls]
        if group:
            fix_rate[cls] = (sum(1 for o in group if o.first_pass is not None), len(group))
    return Summary(
        n=n,
        max_repairs=max_repairs,
        baseline_pass=sum(1 for o in outcomes if o.first_pass == 0),
        pass_by_k={k: sum(1 for o in outcomes if o.first_pass is not None and o.first_pass <= k)
                   for k in range(max_repairs + 1)},
        fixed_by_round={k: sum(1 for o in outcomes if o.first_pass == k) for k in range(1, max_repairs + 1)},
        never_fixed=[o.task_id for o in outcomes if o.first_pass is None],
        mix_at_0=dict(Counter(o.class_at_0 for o in failed0)),
        mix_final=dict(Counter(o.final_class for o in outcomes if o.first_pass is None)),
        fix_rate_by_class=fix_rate,
        prompt_tokens=sum(a.prompt_tokens for a in attempts),
        completion_tokens=sum(a.completion_tokens for a in attempts),
        api_calls=api_calls,
        attempts_total=len(attempts),
        cache_hit_attempts=sum(1 for a in attempts if a.cache_hit),
        outcomes=outcomes,
    )


# ---------------------------------------------------------------- outputs

def write_csv(path: Path, attempts: list[Attempt]) -> None:
    import pandas as pd

    rows = [{k: v for k, v in asdict(a).items() if k != "code"} | {"code_chars": len(a.code)} for a in attempts]
    df = pd.DataFrame(rows)
    df["stderr_last_line"] = df["stderr_tail"].map(lambda s: (s.strip().splitlines() or [""])[-1][:200])
    df.drop(columns=["stderr_tail"]).to_csv(path, index=False)


def _ci(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"[{100 * lo:.1f}%, {100 * hi:.1f}%]"


def render_markdown(s: Summary, cfg: Config, excluded: list[dict], n_valid: int) -> str:
    n = s.n
    total_tokens = s.prompt_tokens + s.completion_tokens
    lines = [
        "# Results: Qiskit self-repair (GPT-OSS-120B via Groq)",
        "",
        f"Model `{cfg.model}`, temperature {cfg.temperature}, reasoning_effort `{cfg.reasoning_effort}`, "
        f"max_completion_tokens {cfg.max_completion_tokens}, exec timeout {cfg.exec_timeout_s:.0f}s. "
        f"Subset: {n} tasks sampled with seed {cfg.seed} from {n_valid} valid tasks.",
        "",
        "## Headline",
        "",
        "| Metric | Count | Wilson 95% CI |",
        "|---|---|---|",
        f"| Baseline pass@1 (attempt 0) | {fmt(s.baseline_pass, n)} | {_ci(s.baseline_pass, n)} |",
    ]
    for k in range(1, s.max_repairs + 1):
        lines.append(f"| Loop pass rate (k={k}) | {fmt(s.pass_by_k[k], n)} | {_ci(s.pass_by_k[k], n)} |")
    gained = s.pass_by_k[s.max_repairs] - s.baseline_pass
    lines += [
        "",
        f"Paired design: tasks fixed by the loop = **{gained}**, tasks broken by the loop = **{s.broken_by_loop}** "
        "(attempt 0 is reused and passing tasks are never retried; asserted).",
        "",
        "## Fixed per repair round",
        "",
        "| Round | Tasks first passing |",
        "|---|---|",
    ]
    lines += [f"| {k} | {s.fixed_by_round[k]} |" for k in range(1, s.max_repairs + 1)]
    lines += [f"| never fixed | {len(s.never_fixed)} |", ""]
    if s.never_fixed:
        lines += ["Never fixed: " + ", ".join(f"`{t}`" for t in s.never_fixed), ""]

    lines += ["## Error mix", "", "Failing tasks by error class at attempt 0 and after the final attempt.", "",
              "| Class | Attempt 0 | After final attempt | Fixed / failed at attempt 0 |", "|---|---|---|---|"]
    for cls in ERROR_CLASSES:
        fixed, failed = s.fix_rate_by_class.get(cls, (0, 0))
        rate = fmt(fixed, failed) if failed else "n/a"
        lines.append(f"| {cls} | {s.mix_at_0.get(cls, 0)} | {s.mix_final.get(cls, 0)} | {rate} |")
    lines += [
        f"| **total failing** | {sum(s.mix_at_0.values())} | {sum(s.mix_final.values())} | |",
        "",
        "## Cost",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Prompt tokens (all attempts) | {s.prompt_tokens:,} |",
        f"| Completion tokens (all attempts) | {s.completion_tokens:,} |",
        f"| Total tokens | {total_tokens:,} |",
        f"| Attempts (LLM generations) | {s.attempts_total} |",
        f"| Real API calls logged (`runs/llm_calls.jsonl`; includes discarded runs, see `docs/VERIFIED.md`) "
        f"| {s.api_calls} |",
        f"| Attempts served from cache when recorded | {s.cache_hit_attempts} |",
        "",
        "Completion tokens exclude hidden reasoning text (`include_reasoning=false`) but Groq still bills "
        "reasoning tokens inside `completion_tokens`.",
        "",
        "## Per-task outcome",
        "",
        "| Task | Attempt 0 | First pass at | Attempts | Final class |",
        "|---|---|---|---|---|",
    ]
    for o in s.outcomes:
        first = "never" if o.first_pass is None else str(o.first_pass)
        lines.append(f"| `{o.task_id}` | {o.class_at_0} | {first} | {o.n_attempts} | {o.final_class} |")

    lines += ["", f"## Excluded tasks ({len(excluded)} invalid on the pinned Qiskit 2.x)", "",
              "Canonical solution failed its own test in this environment, so the task was not eligible for sampling.",
              "", "| Task | Reason |", "|---|---|"]
    for e in excluded:
        reason = e["reason"].replace("|", "\\|").replace("\n", " ")[:160]
        lines.append(f"| `{e['task_id']}` | {reason} |")

    lines += [
        "",
        "## Limitations",
        "",
        f"- Small sample: n = {n}, so one task is {100 / n:.1f} percentage points. No significance claims; "
        "Wilson intervals are shown for context only.",
        "- One model (GPT-OSS-120B on Groq), one Qiskit version (see `requirements.txt`), one prompt set.",
        "- Correctness is judged only by the benchmark's own tests; some tests sample from a simulator and can be "
        "flaky.",
        "- Tasks are restricted to those whose canonical solution passes on Qiskit 2.x in this environment "
        "(no IBM Quantum account, no optional drawing libraries). Excluded tasks are listed above.",
        "- Non-determinism was not measured: attempt 0 was not rerun. Even at temperature 0 the API may return "
        "different outputs, so a rerun without the cache can give different numbers.",
        "- Error classes are rule-based on the final traceback line; see `docs/VERIFIED.md` for ambiguous cases.",
        "",
        "Plots: `results/plots/cumulative_pass.png`, `results/plots/error_classes.png`.",
        "",
    ]
    return "\n".join(lines)


def _style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plot_cumulative(path: Path, s: Summary) -> None:
    import matplotlib.pyplot as plt

    ks = list(range(s.max_repairs + 1))
    values = [s.pass_by_k[k] for k in ks]
    fig, ax = plt.subplots(figsize=(6.4, 4), facecolor=SURFACE)
    _style_axes(ax)
    bars = ax.bar(ks, values, width=0.55, color=BLUE)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + s.n * 0.015, f"{v}/{s.n}", ha="center", va="bottom",
                color=INK, fontsize=10)
    ax.set_xticks(ks, ["0 (baseline)"] + [f"≤ {k}" for k in ks[1:]])
    ax.set_xlabel("Attempt", color=INK_2)
    ax.set_ylabel("Tasks passing (cumulative)", color=INK_2)
    ax.set_ylim(0, s.n)
    ax.set_title("Cumulative tasks passing by attempt", color=INK, loc="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_error_classes(path: Path, s: Summary) -> None:
    import matplotlib.pyplot as plt

    classes = list(ERROR_CLASSES)
    before = [s.mix_at_0.get(c, 0) for c in classes]
    after = [s.mix_final.get(c, 0) for c in classes]
    x = range(len(classes))
    w = 0.36
    fig, ax = plt.subplots(figsize=(7, 4), facecolor=SURFACE)
    _style_axes(ax)
    ax.bar([i - w / 2 - 0.01 for i in x], before, width=w, color=BLUE, label="Attempt 0")
    ax.bar([i + w / 2 + 0.01 for i in x], after, width=w, color=ORANGE, label="After final attempt")
    for i, (b, a) in enumerate(zip(before, after)):
        for xpos, v in ((i - w / 2, b), (i + w / 2, a)):
            if v:
                ax.text(xpos, v + 0.1, str(v), ha="center", va="bottom", color=INK, fontsize=9)
    ax.set_xticks(list(x), classes)
    ax.set_ylabel("Failing tasks", color=INK_2)
    ax.set_ylim(0, max(before + after + [1]) * 1.2)
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.legend(frameon=False, labelcolor=INK)
    ax.set_title("Error classes before and after repair", color=INK, loc="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def build_report(cfg: Config) -> Summary:
    import matplotlib

    matplotlib.use("Agg")
    tasks = load_subset(cfg)
    store = AttemptStore(cfg.paths.attempts)
    ids = [t.task_id for t in tasks]
    missing = [tid for tid in ids if not store.for_task(tid)]
    if missing:
        raise ReportError(f"{len(missing)} tasks have no attempts; run `python -m qsr baseline` first.")
    check_no_regressions(store, ids)

    attempts = [a for tid in ids for a in store.for_task(tid)]
    outcomes = [task_outcome(tid, store.for_task(tid)) for tid in ids]
    api_calls = len(UsageLog(cfg.paths.runs / "llm_calls.jsonl").entries())
    max_seen = max(a.attempt for a in attempts)
    summary = summarize(outcomes, attempts, max(cfg.max_repairs, max_seen), api_calls)

    out = cfg.paths.results
    (out / "plots").mkdir(parents=True, exist_ok=True)
    write_csv(out / "results.csv", attempts)
    excluded = json.loads(cfg.paths.invalid_tasks.read_text(encoding="utf-8")) if cfg.paths.invalid_tasks.exists() else []
    n_valid = len(json.loads(cfg.paths.valid_tasks.read_text(encoding="utf-8"))) if cfg.paths.valid_tasks.exists() else 0
    (out / "summary.md").write_text(render_markdown(summary, cfg, excluded, n_valid), encoding="utf-8")
    plot_cumulative(out / "plots" / "cumulative_pass.png", summary)
    plot_error_classes(out / "plots" / "error_classes.png", summary)
    return summary
