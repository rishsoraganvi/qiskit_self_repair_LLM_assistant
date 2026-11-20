# VERIFIED: facts checked against live sources (2026-11-19)

## Groq (sources: console.groq.com/docs/model/openai/gpt-oss-120b, /docs/reasoning, /docs/rate-limits)
| Item | Verified value |
|---|---|
| Model ID | `openai/gpt-oss-120b` |
| Context window / max output | 131,072 / 65,536 tokens |
| Reasoning parameter | `reasoning_effort`; allowed values for GPT-OSS: `low`, `medium`, `high`. The default for GPT-OSS isn't documented, so we always send `medium` explicitly. |
| Max tokens parameter | `max_completion_tokens` (API default 1024; we set 4096) |
| Temperature | supported, range 0.0-2.0, API default 0.6. Docs recommend 0.5-0.7 for reasoning models; we use 0 per PRD assumption. |
| Reasoning output | `reasoning_format` is **not supported** for gpt-oss. Reasoning goes into `message.reasoning` by default; `include_reasoning: false` suppresses it. Plan: send `include_reasoning=False` to save tokens and use only `message.content` (PROMPTS.md rule 4). |
| Rate limits | The docs table shows RPM 30, RPD 1K, TPM 8K, TPD 200K, but labels them as **Developer plan** base limits. Free-tier values are **unconfirmed**: read them from console.groq.com/settings/limits and put them in `.env`. |
| 429 headers | `retry-after` (seconds, only on 429); `x-ratelimit-{limit,remaining,reset}-requests` (RPD), `x-ratelimit-{limit,remaining,reset}-tokens` (TPM) |

Note: TPM 8K with `max_completion_tokens` 4096 means about 1-2 calls per minute at most, so the limiter must track tokens, not only requests.

## Benchmark (source: datasets-server.huggingface.co, dataset `Qiskit/qiskit_humaneval`)
- Split `test`, 151 rows. Fields: `task_id`, `prompt`, `canonical_solution`, `test`, `entry_point`, plus an extra `difficulty_scale` (basic/intermediate/difficult), which we keep.
- `task_id` format: `qiskitHumanEval/<n>`.
- `test` defines `def check(candidate)` and does **not** call it, so ARCHITECTURE.md's assembly (`code + test + check(entry_point)`) works as written. Tests rely on names imported by the code (e.g. `QuantumCircuit`), which is fine because the model returns full code with imports.
- Download: `datasets` (pyarrow) failed to load its DLL here ("filename or extension is too long"), so we fetch from the HF dataset-viewer `/rows` JSON API instead and cache to `data/raw/qiskit_humaneval.jsonl` (committed so a fresh clone needs no network). `datasets` is dropped from requirements.

## Environment
- Python 3.11.9, Windows 11. Repo at `C:\code\qiskit-selfrepair`: a short path is required on Windows (deep paths break the pyarrow/qiskit-aer/Pillow DLLs). Pinned: qiskit 2.6.2, qiskit-aer 0.18.4, groq 1.7.0 (see `requirements.txt`).
- Added by team decision (2026-11-19) so benchmark tasks that import them can be validated: qiskit-ibm-runtime 0.52.1, qiskit-ibm-transpiler 0.14.2, qiskit-qasm3-import 0.6.0. Installing them left qiskit at 2.6.2.

## Validation result (final, 2026-11-20): **121 valid / 30 invalid**
Run sequentially (`--workers 1`, 60 s timeout) on qiskit 2.6.2. The subset (seed 42, n=30) was drawn from these 121 tasks and frozen in `data/subset.json`:
4, 5, 12, 14, 15, 18, 26, 28, 30, 32, 37, 42, 69, 80, 85, 87, 91, 93, 100, 102, 107, 110, 112, 115, 127, 136, 137, 141, 147, 148.

Invalid tasks by cause (full list with reasons in `data/invalid_tasks.json` and in `results/summary.md`):
| Cause | Tasks | Count |
|---|---|---|
| Needs a saved IBM Quantum account (`AccountNotFoundError`) | 43, 97, 98, 129, 133, 134, 146 | 7 |
| qiskit-ibm-runtime 0.52 rejects the canonical `SamplerOptions` usage (`TypeError`) | 31, 40, 96, 121, 128 | 5 |
| Canonical result doesn't match its test (`AssertionError`); test or solution outdated for 2.x / simulator output | 33, 34, 51, 52, 53, 54, 55, 56, 66, 72, 103, 104, 132 | 13 |
| Optional drawing library not installed (pylatexenc, Graphviz, seaborn) | 3, 29, 123 | 3 |
| qiskit-ibm-transpiler imports a module removed from Qiskit 2.x | 122 | 1 |
| Timeout (>60 s) | 35 | 1 |

We did not install pylatexenc, Graphviz or seaborn (only 3 tasks, and outside the agreed stack); ask if wanted.

### History of earlier, discarded runs
1. 94 valid / 57 invalid: 28 long-path DLL errors plus 29 missing IBM packages.
2. 95 / 56 after the IBM packages: 55 long-path DLL errors.
3. 117 / 34 on the short path with 6 parallel workers. 4 tasks (64, 67, 101, 117) failed with access violations (exit 0xC0000005) or timeouts but pass when run alone; Aer multithreads, so parallel validation is unreliable. Validation is now sequential by default. A subset drawn from that run was discarded before any evaluation.

## Implementation decisions
- **Executor output scrubbing:** tracebacks contain the random temp dir. The executor replaces it with `<workdir>` so that re-executing cached code yields identical repair prompts, and therefore identical cache keys. Without this, "rerun costs 0 API calls" fails after `runs/attempts.jsonl` is deleted.
- **Executor isolation:** `python -I -X utf8 program.py` in a fresh temp dir. `GROQ_API_KEY` is removed from the child environment, and `MPLBACKEND=Agg`.
- **TPM limiter:** reserves `prompt_estimate + max_completion_tokens/4` before a call and replaces it with the actual usage afterward. A 429 still triggers backoff and honors `retry-after`.
- **Daily budget:** summed from `runs/llm_calls.jsonl` for the current UTC date. Cache hits are free.
- **Reproducibility:** `cache/` is gitignored as TASKS.md requires. `runs/attempts.jsonl`, `runs/llm_calls.jsonl`, `data/` and `results/` are meant to be committed, so `report` reproduces from a fresh clone. Re-execution needs the `cache/` folder shared separately.

## Error classifier: ambiguous cases
- The class comes from the **last** exception line in stderr (chained exceptions use the final one).
- `MissingOptionalLibraryError` counts as `api_version` (an import-type failure).
- `TypeError` is `api_version` only if its message names a Qiskit object (QuantumCircuit, Sampler, Estimator, transpile, Backend, Options, ...) or the innermost frame is inside a `qiskit*` package. Otherwise it's `other`.
- Any other exception whose message contains "deprecat" or "removed" is `api_version`.
- `AssertionError` is `logic`, even when the assertion fails because an API returns a differently shaped result.
- No `def <entry_point>` in the extracted code gives `other` with note `no_function_found`. The code is still executed.
- A non-zero exit with no traceback, e.g. a native crash, is `other`.

## Evaluation run (2026-11-20)
- **Settings:** `reasoning_effort=low` (team decision for the free-tier daily budget; set via `QSR_REASONING_EFFORT` in `.env`), temperature 0, `max_completion_tokens` 4096, Groq free tier (RPM 30, TPM 8000, daily budget 200000). Average call was about 800 tokens.
- **Harness fix after the first baseline execution:** benchmark tests use names that only the task prompt imports (e.g. `random_clifford`, `entropy`, `YGate`). The original benchmark runs prompt + completion, so those names always exist. Our model returns complete code and sometimes rewrites the imports, so tasks 110, 136 and 147 failed with `NameError` inside `check()`. The executor now prepends the prompt's top-level import statements (`executor.prompt_imports`). LLM generations, prompts and parameters were unchanged: attempt 0 was re-scored from the cache with 0 API calls, which moved baseline from 15/30 to 17/30 (110 and 136 pass). The pre-fix records are kept in `runs/discarded/attempts_before_prompt_imports.jsonl`.
- **Discarded API calls:** a repair run started before the fix was stopped after 3 recorded attempts on task 14, plus 1 call whose attempt wasn't saved. That makes 4 of the 64 calls in `runs/llm_calls.jsonl` belong to no reported attempt. The reported run used 30 baseline + 30 repair calls.
- **Classifier rule change after review:** a `TypeError` whose message is a call-signature mismatch ("unexpected keyword argument", "positional argument", "required ... argument") is now `api_version`. Example: `circuit_to_instruction(..., name=)`, `LieTrotter(num_steps=)`. Per EVAL_SPEC this is a "TypeError mentioning Qiskit args".

## Manual review of error classes (13 attempt-0 failures, 2026-11-20)
| Task | Final exception | Class | Verdict |
|---|---|---|---|
| 14, 15, 37 | `TypeError: Sampler.__init__() got an unexpected keyword argument 'backend'` | api_version | correct |
| 32 | `TypeError: Estimator.__init__() got an unexpected keyword argument 'backend'` | api_version | correct |
| 28 | `ImportError: cannot import name 'Aer' from 'qiskit'` | api_version | correct |
| 91 | `TypeError: circuit_to_instruction() got an unexpected keyword argument 'name'` | api_version | correct (after rule change) |
| 112 | `TypeError: LieTrotter.__init__() got an unexpected keyword argument 'num_steps'` | api_version | correct (after rule change) |
| 147 | `TypeError: QuantumCircuit.mcry() got an unexpected keyword argument 'ancilla_qubits'` | api_version | correct |
| 141 | `AttributeError: 'Pauli' object has no attribute 'num_terms'` | api_version | correct |
| 127 | `AssertionError: Generated circuit does not match expected circuit` | logic | correct |
| 137 | `QiskitError: Input density matrix must be a 2-qubit state.` | other | correct (wrong input, not API drift) |
| 102 | `TypeError: 'str' object is not callable` (`backend.name()`) | other | **ambiguous**: really API drift (`name` became an attribute in BackendV2), but indistinguishable by rule from a generic bug |
| 115 | `AttributeError: Instruction u is already in the target` | api_version | **ambiguous**: EVAL_SPEC maps all AttributeErrors to api_version, but this is API misuse, not version drift |

Result: 11/13 clearly correct, 2 ambiguous. They're kept as the spec's rules dictate and noted here rather than special-cased.
- **Path scrubbing extended (2026-11-20):** tracebacks from Qiskit's own files contained the virtualenv path, so repair prompts, and therefore cache keys, depended on where the repo was cloned. The executor now also replaces `sys.prefix` with `<venv>` and `sys.base_prefix` with `<python>`. Repair was rerun after this change: 12 prompts changed and were re-called; results were identical (17/30 to 25/30). The records from before the change are in `runs/discarded/attempts_before_path_scrub.jsonl`. `runs/llm_calls.jsonl` now has 76 calls; 60 belong to the reported attempts.
- **Default reasoning effort is `low`** in `config.py`, so a clone without `.env` reproduces the cached run.

## Fresh-environment reproduction (Day 5 exit check), 2026-11-20
A copy in a different folder (`C:\code\qsr-fresh`) with a new virtualenv, **no `.env`/API key**, no `runs/attempts.jsonl`, and only `cache/` carried over: `baseline` + `repair` + `report` made **0 API calls** (60/60 cache hits) and produced identical task/attempt/passed/error_class rows (only execution seconds differ). Headline: baseline 17/30 = 56.7%, after 3 repairs 25/30 = 83.3%.
