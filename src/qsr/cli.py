"""Command-line interface: validate, sample, baseline, repair, report, run-all."""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace

from .config import Config, get_config

EXIT_BUDGET = 3


def cmd_validate(args: argparse.Namespace, cfg: Config) -> int:
    from .validate import validate

    valid, invalid = validate(cfg, force=getattr(args, "force", False), workers=getattr(args, "workers", None))
    print(f"{len(valid)} valid / {len(invalid)} invalid")
    for inv in invalid:
        print(f"  {inv.task_id}: {inv.reason}")
    if len(valid) < cfg.subset_size:
        print(f"STOP: fewer than {cfg.subset_size} valid tasks; decision needed before sampling.")
        return 1
    return 0


def cmd_sample(args: argparse.Namespace, cfg: Config) -> int:
    from .sample import sample

    tasks = sample(cfg, n=args.n, seed=args.seed)
    print(f"Subset: {len(tasks)} tasks (seed {args.seed}) -> {cfg.paths.subset}")
    print("  " + ", ".join(t.task_id.rsplit("/", 1)[-1] for t in tasks))
    return 0


def _print_phase(name: str, r, cfg: Config) -> int:
    print(f"{name}: {r.passed}/{r.total} passing = {100 * r.passed / r.total:.1f}%  "
          f"(API calls this run: {r.api_calls}, cache hits: {r.cache_hits})")
    if r.stopped_reason or r.remaining:
        print(f"Stopped early: {r.stopped_reason or 'incomplete'}")
        print(f"Remaining ({len(r.remaining)}): {', '.join(r.remaining)}")
        print("Rerun the same command later to resume; completed work is not repeated.")
        return EXIT_BUDGET
    return 0


def cmd_baseline(args: argparse.Namespace, cfg: Config) -> int:
    from .baseline import run_baseline

    r = run_baseline(cfg)
    if not r.remaining:
        print(f"Baseline pass@1: {r.passed}/{r.total} = {100 * r.passed / r.total:.1f}%")
    return _print_phase("Baseline", r, cfg)


def cmd_repair(args: argparse.Namespace, cfg: Config) -> int:
    from .repair import run_repair

    r = run_repair(cfg, max_repairs=args.max_repairs)
    return _print_phase(f"After up to {args.max_repairs} repairs", r, cfg)


def cmd_report(args: argparse.Namespace, cfg: Config) -> int:
    from .report import build_report, fmt

    s = build_report(cfg)
    print(f"Baseline pass@1:         {fmt(s.baseline_pass, s.n)}")
    print(f"Post-repair pass rate:   {fmt(s.pass_by_k[s.max_repairs], s.n)}")
    for k in range(1, s.max_repairs + 1):
        print(f"  fixed in round {k}: {s.fixed_by_round[k]}   (pass rate k={k}: {fmt(s.pass_by_k[k], s.n)})")
    print(f"Never fixed: {len(s.never_fixed)}   Broken by loop: {s.broken_by_loop}")
    print("Error class   attempt0  final  fixed/failed")
    for cls in ("syntax", "api_version", "logic", "timeout", "other"):
        fixed, failed = s.fix_rate_by_class.get(cls, (0, 0))
        print(f"  {cls:<12}{s.mix_at_0.get(cls, 0):>8}{s.mix_final.get(cls, 0):>7}   {fixed}/{failed}")
    print(f"Tokens: {s.prompt_tokens:,} prompt + {s.completion_tokens:,} completion; API calls logged: {s.api_calls}")
    print(f"Wrote {cfg.paths.results / 'results.csv'}, summary.md, plots/")
    return 0


def cmd_run_all(args: argparse.Namespace, cfg: Config) -> int:
    steps = [
        ("validate", lambda: cmd_validate(args, cfg)),
        ("sample", lambda: cmd_sample(argparse.Namespace(n=cfg.subset_size, seed=cfg.seed), cfg)),
        ("baseline", lambda: cmd_baseline(args, cfg)),
        ("repair", lambda: cmd_repair(argparse.Namespace(max_repairs=args.max_repairs), cfg)),
        ("report", lambda: cmd_report(args, cfg)),
    ]
    for name, step in steps:
        print(f"== {name} ==")
        code = step()
        if code:
            return code
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qsr", description="Qiskit self-repair evaluation harness")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="run canonical solutions on installed Qiskit")
    p.add_argument("--force", action="store_true", help="ignore cached validation results")
    p.add_argument("--workers", type=int, default=None, help="parallel subprocesses")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("sample", help="seeded sample of valid tasks (frozen once written)")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_sample)

    sub.add_parser("baseline", help="attempt 0 for each task").set_defaults(func=cmd_baseline)

    p = sub.add_parser("repair", help="repair attempts for failing tasks")
    p.add_argument("--max-repairs", type=int, default=3)
    p.set_defaults(func=cmd_repair)

    sub.add_parser("report", help="aggregate results").set_defaults(func=cmd_report)

    p = sub.add_parser("run-all", help="validate, sample, baseline, repair, report")
    p.add_argument("--max-repairs", type=int, default=3)
    p.set_defaults(func=cmd_run_all)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg = get_config()
    if getattr(args, "max_repairs", None) is not None:
        cfg = replace(cfg, max_repairs=args.max_repairs)
    try:
        return args.func(args, cfg)
    except Exception as exc:  # surface clean errors for expected failures
        from .llm import LLMError
        from .repair import MissingBaseline
        from .report import ReportError
        from .sample import SubsetError

        if isinstance(exc, (LLMError, MissingBaseline, ReportError, SubsetError)):
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
