# Qiskit Self-Repair

An LLM assistant that writes and self-repairs Qiskit code, built as an evaluation harness.

It measures whether feeding execution errors back to **GPT-OSS-120B** (via Groq's free tier) improves
functional correctness on a 30-task subset of **Qiskit HumanEval**, running on **Qiskit 2.x**.
It compares a single-shot baseline (attempt 0) with an execute-and-repair loop (up to 3 repair attempts).
See `docs/PRD.md` for the research question and `docs/EVAL_SPEC.md` for the protocol.

## Setup

Requires Python 3.11+. On Windows, keep the repo on a **short path** such as `C:\code\qiskit-selfrepair`.
Deep paths break DLL loading for pyarrow, qiskit-aer and Pillow ("The filename or extension is too long").

```powershell
cd C:\code\qiskit-selfrepair
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

(`uv venv --python 3.11 .venv` then `uv pip install -r requirements.txt -e .` works too.)

### `.env`

```powershell
Copy-Item .env.example .env
```

Then edit `.env`:

| Variable | Meaning |
|---|---|
| `GROQ_API_KEY` | your key from console.groq.com (never commit it) |
| `RPM_LIMIT`, `TPM_LIMIT` | requests/tokens per minute for `openai/gpt-oss-120b`, from console.groq.com/settings/limits |
| `DAILY_TOKEN_BUDGET` | stop cleanly before using more than this many tokens per UTC day (set it a bit below your TPD) |
| `QSR_REASONING_EFFORT` | optional; defaults to `low`, which the reported results use. Changing it invalidates the cache. |

Leave a limit blank to disable it. The client still backs off on HTTP 429 and honors `retry-after`.

## Commands

```powershell
python -m qsr validate                  # run every canonical solution; writes data/valid_tasks.json, invalid_tasks.json
python -m qsr sample --n 30 --seed 42   # freeze data/subset.json (refuses to resample with other params)
python -m qsr baseline                  # attempt 0 for each task -> runs/attempts.jsonl
python -m qsr repair --max-repairs 3    # attempts 1..3 for failing tasks; stops a task on first pass
python -m qsr report                    # results/results.csv, results/summary.md, results/plots/*.png
python -m qsr run-all                   # all of the above in order
```

Every command is **resumable and cache-first**:
- `validate` reuses its saved results unless you pass `--force`.
- `baseline` and `repair` skip attempts already in `runs/attempts.jsonl`.
- Every LLM response is cached in `cache/<sha256>.json`, so a rerun costs **0 API calls**.
- If the daily token budget would be exceeded, the run stops, prints the remaining tasks and exits with code 3.
  Run the same command again after the reset.

## Reproducing the reported numbers

Two levels:

1. **From the recorded attempts (fresh clone, no key):** `runs/attempts.jsonl`, `data/` and `results/` are committed.
   `python -m qsr report` rebuilds the CSV, summary and plots from them.
2. **Re-executing from the LLM cache (no API calls):** copy the `cache/` folder from the original run.
   It's gitignored; share it as a zip. Then delete `runs/attempts.jsonl` and run `baseline`, `repair` and `report`.
   Each generation comes from the cache, and the code is executed again locally.
   Execution output is scrubbed of temp-dir, virtualenv and Python-install paths, so the repair prompts and their cache keys are the same in any folder (verified, see docs/VERIFIED.md).
   Results can still differ if a test samples from a simulator.

## How it works

| Module | Role |
|---|---|
| `src/qsr/dataset.py` | downloads `Qiskit/qiskit_humaneval` (151 tasks) via the HF dataset-viewer API; caches to `data/raw/` |
| `src/qsr/validate.py` | runs `prompt + canonical_solution + test + check(entry_point)` per task |
| `src/qsr/sample.py` | seeded sample of valid tasks |
| `src/qsr/llm.py` | the only Groq caller: cache, RPM/TPM limiter, retry/backoff, daily budget, token log (`runs/llm_calls.jsonl`) |
| `src/qsr/prompts.py` | prompt constants from `docs/PROMPTS.md` |
| `src/qsr/extract.py` | pulls the last ```python block out of the response |
| `src/qsr/executor.py` | runs code in a subprocess (`python -I`, temp dir, timeout, no API key in env) |
| `src/qsr/classify.py` | syntax / api_version / logic / timeout / other |
| `src/qsr/baseline.py`, `repair.py` | attempt 0, then repair rounds (fresh conversation each round) |
| `src/qsr/report.py` | metrics, Wilson intervals, plots |

Verified API details and dataset quirks are in `docs/VERIFIED.md`.

## Tests

```powershell
python -m pytest
```

The tests cover code extraction, the error classifier, the executor (pass/fail/timeout), cache key stability,
the rate limiter, retries, the budget guard, and an end-to-end baseline, repair and report run with a fake LLM client.
