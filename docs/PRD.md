# PRD: Qiskit Self-Repair LLM Assistant

## 1. Summary
A CLI evaluation harness that measures whether an execute-and-repair loop improves GPT-OSS-120B (via Groq) at writing correct Qiskit code, using a 30-task subset of Qiskit HumanEval on Qiskit 2.x.

## 2. Research question
Does feeding execution errors back to the LLM (max 3 repair attempts) raise functional correctness over a single-shot baseline, and which error classes does the loop fix or fail to fix?

## 3. Constraints (hard)
| Item | Value |
|---|---|
| Timeline | 5 days, team of 3-4 |
| LLM | `openai/gpt-oss-120b` via Groq API, **free tier** |
| Quantum SDK | Latest Qiskit 2.x (pin exact version in `requirements.txt` on Day 1) |
| Evaluation size | 30 tasks |
| Interface | CLI scripts only. No UI, no notebook, no web app |
| Built with | Claude Code, driven by the `.md` files in this folder |

## 4. Non-goals (do NOT build)
- RAG over Qiskit docs, multi-agent designs, multiple LLMs, fine-tuning
- Streamlit/web UI, Jupyter deliverable
- Full 151-task run
- Any stretch goal before Day 4 results exist

## 5. Functional requirements
| ID | Requirement |
|---|---|
| FR1 | Load Qiskit HumanEval (task_id, prompt, canonical_solution, test, entry_point) and cache it locally |
| FR2 | **Validate** every task: run canonical solution + test under the pinned Qiskit 2.x; write `data/valid_tasks.json` and `data/invalid_tasks.json` (with failure reason) |
| FR3 | Sample 30 tasks from valid tasks with a fixed seed (42); write `data/subset.json` |
| FR4 | Sandboxed executor: subprocess, wall-clock timeout, captured stdout/stderr, structured result |
| FR5 | Groq client: rate limiter, 429 backoff, on-disk response cache, token accounting, resumable runs |
| FR6 | Baseline runner: one generation per task, no feedback |
| FR7 | Repair loop: failing tasks get up to 3 repair attempts; attempt 0 is the baseline generation (reused, not regenerated) |
| FR8 | Error classifier: syntax / api_version / logic / timeout / other, rule-based |
| FR9 | Report generator: `results/results.csv`, `results/summary.md`, PNG plots |
| FR10 | CLI: `validate`, `sample`, `baseline`, `repair`, `report`, `run-all` |

## 6. Acceptance criteria
1. `validate` shows how many of the benchmark's tasks pass with canonical solutions on Qiskit 2.x; invalid ones are listed with reasons.
2. `baseline` completes on all 30 tasks and writes pass/fail per task.
3. `repair` completes without re-calling the LLM for cached prompts (rerun costs zero API calls).
4. `report` prints baseline pass@1, post-repair pass rate, tasks fixed per retry round, and error-class breakdown.
5. Fresh clone + `README.md` steps reproduces results from cache.

## 7. Deliverables
- Repo with code, `README.md`, pinned `requirements.txt`
- `results/summary.md` and plots
- Short slide deck (Day 5, outside Claude Code's scope)

## 8. Risks
| Risk | Mitigation |
|---|---|
| Canonical solutions fail on Qiskit 2.x | FR2 validation; sample only valid tasks; report excluded count as a finding |
| Groq free-tier limits stall runs | Config-driven limiter, disk cache, resumable runs, daily token budget guard |
| 30 tasks is a small sample (1 task = 3.3 percentage points) | Report raw counts next to percentages; no significance claims |
| Reasoning model returns long outputs and burns tokens | Cap `max_completion_tokens`; keep reasoning effort low/medium (see ARCHITECTURE.md) |
| Generated code hangs or is unsafe | Subprocess with timeout, temp working directory, no network use required |

## 9. Assumptions (correct me if wrong)
- Benchmark is the public Qiskit HumanEval dataset; exact source and field names are verified on Day 1.
- Temperature 0 (or lowest allowed); results still may not be perfectly deterministic.
- Success is measured only by the benchmark's own tests.
