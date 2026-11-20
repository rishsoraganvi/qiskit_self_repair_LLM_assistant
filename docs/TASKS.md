# TASKS: Build checklist for Claude Code

Tick each box only after its exit check passes and `pytest` is green. If blocked, stop and report.

## Day 1: Unblock
- [x] Project skeleton, `requirements.txt` (pinned), `.env.example`, `.gitignore` (includes `.env`, `cache/`)
- [x] `config.py`, `dataset.py`: load benchmark, cache raw data
- [x] `executor.py` with tests (pass, fail, timeout cases)
- [x] `validate.py`: run all canonical solutions on installed Qiskit 2.x
- [x] `docs/VERIFIED.md`: record actual Groq model ID, reasoning parameter, benchmark field names, Qiskit version, validated vs. invalid task counts
- [x] **Exit check:** `python -m qsr validate` prints `N valid / M invalid`; one task runs end to end with its canonical solution.
- [x] If fewer than 30 valid tasks, STOP and report (decision needed from the team). (Not triggered: 121 valid.)

## Day 2: Baseline (gate day)
- [x] `llm.py` with cache, limiter, backoff, budget guard (+ unit tests with a fake client)
- [x] `extract.py` (+ tests), `prompts.py`
- [x] `sample.py` produces `data/subset.json`
- [x] `baseline.py` + `classify.py`
- [x] **Exit check:** `python -m qsr baseline` completes on 30 tasks and prints baseline pass@1. Rerun costs 0 API calls.
- **Gate:** no baseline number by end of day 2 means the team switches to the fidelity-prediction fallback.

## Day 3: Repair loop
- [x] `repair.py`: attempts 1-3 for failing tasks, reuse attempt 0, stop on pass
- [x] Assert no task passes at attempt 0 and later fails (no regressions)
- [x] **Exit check:** `python -m qsr repair` completes; `runs/attempts.jsonl` has all attempts; rerun costs 0 API calls.

## Day 4: Evaluation
- [x] `report.py`: CSV, `summary.md`, two plots
- [x] Manual review of 10 error-class assignments; fix rules if needed
- [x] **Exit check:** `python -m qsr report` produces all outputs matching `EVAL_SPEC.md`.
- [ ] Stretch only now, and only if asked: nothing is pre-approved.

## Day 5: Package
- [x] `README.md`: setup, `.env`, commands, how to reproduce from cache
- [x] `run-all` command; fresh-clone test
- [x] Final `summary.md` includes excluded tasks, token cost, limitations
- [x] **Exit check:** fresh environment reproduces the reported numbers from cache.
