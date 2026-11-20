# ARCHITECTURE

## Repo layout
```
qiskit-selfrepair/
  CLAUDE.md  PRD.md  README.md  requirements.txt  .env.example  .gitignore
  docs/  (ARCHITECTURE.md EVAL_SPEC.md PROMPTS.md TASKS.md VERIFIED.md)
  data/  (raw/ valid_tasks.json invalid_tasks.json subset.json)
  cache/ (llm responses, one JSON per call)
  runs/  (attempts.jsonl)
  results/ (results.csv summary.md plots/*.png)
  src/qsr/
    __main__.py   cli.py   config.py
    dataset.py    validate.py   sample.py
    llm.py        executor.py   extract.py
    baseline.py   repair.py     classify.py   report.py
  tests/
```

## Modules
| Module | Responsibility |
|---|---|
| `config.py` | Central config (model ID, temperature, token limits, timeouts, rate limits, seed). Values from env/defaults |
| `dataset.py` | Load and cache benchmark; return `Task` dataclass |
| `validate.py` | Run canonical solution + test per task via executor; emit valid/invalid lists |
| `sample.py` | Seeded sample of N valid tasks |
| `llm.py` | Groq wrapper: cache, limiter, retry/backoff, token accounting |
| `extract.py` | Pull Python code from model response (see PROMPTS.md rules) |
| `executor.py` | Run `program` in subprocess with timeout; return `ExecResult` |
| `baseline.py` | Attempt 0 for each task |
| `repair.py` | Attempts 1..3 for tasks whose latest attempt failed |
| `classify.py` | Map `ExecResult` to error class |
| `report.py` | Aggregate `attempts.jsonl` to CSV, markdown summary, plots |

## Data schemas
**Task:** `task_id, prompt, canonical_solution, test, entry_point` (verify names on Day 1).

**Attempt record (one JSON line in `runs/attempts.jsonl`):**
```json
{"task_id": "...", "attempt": 0, "code": "...", "passed": false,
 "error_class": "api_version", "stderr_tail": "...", "exec_seconds": 2.1,
 "prompt_tokens": 0, "completion_tokens": 0, "cache_hit": false}
```
`attempt 0` = baseline. `attempt k>=1` = repair rounds.

## Program assembly for execution
`program = generated_code + "\n\n" + task.test + "\n\n" + f"check({task.entry_point})\n"`
The model is asked to return the complete code (imports + function), so no prompt/completion stitching is needed. Validation uses `task.prompt + task.canonical_solution` as `generated_code`. If the benchmark's test format differs (e.g. it already calls `check`), adapt on Day 1 and document in `docs/VERIFIED.md`.

## Executor
- `subprocess.run([sys.executable, file], timeout=EXEC_TIMEOUT_S, capture_output=True, cwd=tempdir)`
- Default timeout 60 s (Aer runs can be slow); configurable.
- Return: `passed` (exit code 0), `stdout`, `stderr`, `timed_out`, `seconds`.
- Truncate stderr to its last ~4000 characters before it enters any repair prompt.

## Groq client (`llm.py`)
- Model: `openai/gpt-oss-120b` (verify ID). Key from `GROQ_API_KEY`.
- **Cache key** = sha256(model + messages + temperature + max tokens + reasoning effort + attempt index). Cache hit returns stored response with zero API calls.
- **Rate limiting:** config values `RPM_LIMIT`, `TPM_LIMIT`, `DAILY_TOKEN_BUDGET`. The user reads the current free-tier numbers from the Groq console and puts them in `.env`; do not hardcode from memory.
- **429 / transient errors:** exponential backoff with jitter, max 6 retries, honor `retry-after` if present.
- **Budget guard:** if the daily budget would be exceeded, stop cleanly, print remaining work, and exit so the run can resume next day or after reset.
- Log prompt/completion tokens per call. Report total tokens in `summary.md`.
- Reasoning: set reasoning effort to the lowest setting that works (default `medium`; verify parameter name and allowed values). Cap `max_completion_tokens` (default 4096).

## Call budget (planning estimate)
30 baseline calls + at most 3 x (number of failing tasks) repair calls. Worst case about 120 calls, plus a few dozen for development. Reusing attempt 0 as the baseline is what keeps this affordable.
