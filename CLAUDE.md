# CLAUDE.md: Instructions for Claude Code

## Project
CLI harness evaluating GPT-OSS-120B (Groq, free tier) on Qiskit HumanEval (30-task subset, Qiskit 2.x), baseline vs. execute-and-repair loop. Read `PRD.md` first, then `ARCHITECTURE.md`, `EVAL_SPEC.md`, `PROMPTS.md`, `TASKS.md`.

## Hard rules
1. **Scope:** build only what `PRD.md` lists. No UI, no RAG, no multi-agent, no extra models. Ask before adding anything.
2. **Never hardcode or commit secrets.** API key comes from `GROQ_API_KEY` in `.env` (gitignored). Ship `.env.example`.
3. **Every LLM call goes through `src/qsr/llm.py`**, which handles cache, rate limiting, retries, and token logging. Never call Groq directly elsewhere.
4. **Every generated-code execution goes through `src/qsr/executor.py`** (subprocess + timeout + temp dir). Never `exec()`/`eval()` model output in-process.
5. **Runs must be resumable and cache-first.** Re-running a command must not repeat completed work or spend API calls.
6. **Do not assume API details from memory.** Verify the Groq model ID, parameters (`reasoning_effort`, token limits), and Qiskit HumanEval field names against the live docs/dataset on Day 1, and record findings in `docs/VERIFIED.md`.
7. Pin exact versions in `requirements.txt` (qiskit, qiskit-aer, groq, pandas, matplotlib, pytest, python-dotenv, datasets or equivalent).

## Stack
Python 3.11+, `groq` SDK, Qiskit 2.x + qiskit-aer, pandas, matplotlib, pytest, argparse (or typer). Plain files for storage: JSON/JSONL/CSV. No database.

## Commands (target interface)
```
python -m qsr validate
python -m qsr sample --n 30 --seed 42
python -m qsr baseline
python -m qsr repair --max-repairs 3
python -m qsr report
python -m qsr run-all
```

## Code style
Type hints, small functions, dataclasses for records, `logging` not `print` (except CLI summaries). Unit tests for: code extraction, error classifier, executor timeout, cache key stability, rate limiter.

## Definition of done per milestone
Follow the exit checks in `TASKS.md`. After finishing each, run `pytest` and tick the checkbox. If an exit check cannot be met, stop and report why instead of working around it.
