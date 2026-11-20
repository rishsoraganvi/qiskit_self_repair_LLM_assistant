# EVAL_SPEC

## Protocol
1. Validate all benchmark tasks on pinned Qiskit 2.x (canonical solution must pass its test). Record excluded tasks and reasons.
2. Sample 30 valid tasks, seed 42. Freeze `data/subset.json`; never resample.
3. **Attempt 0 (baseline):** one generation per task from the generation prompt. Execute and score.
4. **Repair rounds 1-3:** for each task still failing, send the repair prompt (original task + last code + error output). Execute and score. Stop a task as soon as it passes.
5. Same model, parameters, and subset for all attempts. Attempt 0 is shared between baseline and loop (paired design).

## Metrics
| Metric | Definition |
|---|---|
| Baseline pass@1 | tasks passing at attempt 0 / 30 |
| Loop pass rate (k) | tasks passing at any attempt <= k / 30, for k = 1, 2, 3 |
| Fixed per round | tasks first passing at attempt k |
| Never fixed | tasks failing after attempt 3 |
| Error mix | counts per error class at attempt 0 and after final attempt |
| Fix rate by class | fixed / failed-at-attempt-0, per error class |
| Cost | total prompt and completion tokens, API calls, cache hits |

## Error taxonomy (rule-based on stderr and exit status)
| Class | Rule |
|---|---|
| `timeout` | executor timed out |
| `syntax` | `SyntaxError`, `IndentationError` |
| `api_version` | `ImportError`, `ModuleNotFoundError`, `AttributeError`, `TypeError` mentioning Qiskit objects/args, or messages containing "deprecated"/"removed" |
| `logic` | `AssertionError` from the test, or a clean run with wrong result |
| `other` | everything else |
Document ambiguous cases in `docs/VERIFIED.md`. Manually review a sample of 10 classifications for correctness.

## Statistical honesty
- n = 30 means one task is 3.3 percentage points. Always print counts next to percentages (e.g. 17/30 = 56.7%).
- Because the design is paired, also report: tasks fixed by the loop, and tasks broken by it (should be 0 since attempt 0 is reused; assert this).
- Optionally report Wilson 95% intervals. Do not claim statistical significance.
- Report non-determinism: if time and budget allow, rerun attempt 0 once on 10 tasks and report agreement. Otherwise state it as a limitation.

## Outputs
- `results/results.csv`: one row per (task, attempt)
- `results/summary.md`: tables above, token cost, excluded-task list, limitations
- `results/plots/`: (a) cumulative pass count by attempt, (b) error class counts before/after

## Limitations to state in the report
Small sample, one model, one Qiskit version, test-based correctness only, tasks restricted to those valid on 2.x.
