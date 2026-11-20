# Results: Qiskit self-repair (GPT-OSS-120B via Groq)

Model `openai/gpt-oss-120b`, temperature 0.0, reasoning_effort `low`, max_completion_tokens 4096, exec timeout 60s. Subset: 30 tasks sampled with seed 42 from 121 valid tasks.

## Headline

| Metric | Count | Wilson 95% CI |
|---|---|---|
| Baseline pass@1 (attempt 0) | 17/30 = 56.7% | [39.2%, 72.6%] |
| Loop pass rate (k=1) | 20/30 = 66.7% | [48.8%, 80.8%] |
| Loop pass rate (k=2) | 23/30 = 76.7% | [59.1%, 88.2%] |
| Loop pass rate (k=3) | 25/30 = 83.3% | [66.4%, 92.7%] |

Paired design: tasks fixed by the loop = **8**, tasks broken by the loop = **0** (attempt 0 is reused and passing tasks are never retried; asserted).

## Fixed per repair round

| Round | Tasks first passing |
|---|---|
| 1 | 3 |
| 2 | 3 |
| 3 | 2 |
| never fixed | 5 |

Never fixed: `qiskitHumanEval/14`, `qiskitHumanEval/15`, `qiskitHumanEval/32`, `qiskitHumanEval/37`, `qiskitHumanEval/141`

## Error mix

Failing tasks by error class at attempt 0 and after the final attempt.

| Class | Attempt 0 | After final attempt | Fixed / failed at attempt 0 |
|---|---|---|---|
| syntax | 0 | 0 | n/a |
| api_version | 10 | 3 | 5/10 = 50.0% |
| logic | 1 | 0 | 1/1 = 100.0% |
| timeout | 0 | 0 | n/a |
| other | 2 | 2 | 2/2 = 100.0% |
| **total failing** | 13 | 5 | |

## Cost

| Item | Value |
|---|---|
| Prompt tokens (all attempts) | 26,836 |
| Completion tokens (all attempts) | 23,033 |
| Total tokens | 49,869 |
| Attempts (LLM generations) | 60 |
| Real API calls logged (`runs/llm_calls.jsonl`; includes discarded runs, see `docs/VERIFIED.md`) | 76 |
| Attempts served from cache when recorded | 48 |

Completion tokens exclude hidden reasoning text (`include_reasoning=false`) but Groq still bills reasoning tokens inside `completion_tokens`.

## Per-task outcome

| Task | Attempt 0 | First pass at | Attempts | Final class |
|---|---|---|---|---|
| `qiskitHumanEval/4` | pass | 0 | 1 | pass |
| `qiskitHumanEval/5` | pass | 0 | 1 | pass |
| `qiskitHumanEval/12` | pass | 0 | 1 | pass |
| `qiskitHumanEval/14` | api_version | never | 4 | api_version |
| `qiskitHumanEval/15` | api_version | never | 4 | other |
| `qiskitHumanEval/18` | pass | 0 | 1 | pass |
| `qiskitHumanEval/26` | pass | 0 | 1 | pass |
| `qiskitHumanEval/28` | api_version | 2 | 3 | pass |
| `qiskitHumanEval/30` | pass | 0 | 1 | pass |
| `qiskitHumanEval/32` | api_version | never | 4 | other |
| `qiskitHumanEval/37` | api_version | never | 4 | api_version |
| `qiskitHumanEval/42` | pass | 0 | 1 | pass |
| `qiskitHumanEval/69` | pass | 0 | 1 | pass |
| `qiskitHumanEval/80` | pass | 0 | 1 | pass |
| `qiskitHumanEval/85` | pass | 0 | 1 | pass |
| `qiskitHumanEval/87` | pass | 0 | 1 | pass |
| `qiskitHumanEval/91` | api_version | 2 | 3 | pass |
| `qiskitHumanEval/93` | pass | 0 | 1 | pass |
| `qiskitHumanEval/100` | pass | 0 | 1 | pass |
| `qiskitHumanEval/102` | other | 1 | 2 | pass |
| `qiskitHumanEval/107` | pass | 0 | 1 | pass |
| `qiskitHumanEval/110` | pass | 0 | 1 | pass |
| `qiskitHumanEval/112` | api_version | 3 | 4 | pass |
| `qiskitHumanEval/115` | api_version | 1 | 2 | pass |
| `qiskitHumanEval/127` | logic | 3 | 4 | pass |
| `qiskitHumanEval/136` | pass | 0 | 1 | pass |
| `qiskitHumanEval/137` | other | 1 | 2 | pass |
| `qiskitHumanEval/141` | api_version | never | 4 | api_version |
| `qiskitHumanEval/147` | api_version | 2 | 3 | pass |
| `qiskitHumanEval/148` | pass | 0 | 1 | pass |

## Excluded tasks (30 invalid on the pinned Qiskit 2.x)

Canonical solution failed its own test in this environment, so the task was not eligible for sampling.

| Task | Reason |
|---|---|
| `qiskitHumanEval/3` | qiskit.exceptions.MissingOptionalLibraryError: "The 'pylatexenc' library is required to use 'MatplotlibDrawer'. You can install it with 'pip install pylatexenc' |
| `qiskitHumanEval/29` | qiskit.exceptions.MissingOptionalLibraryError: "The 'Graphviz' library is required to use 'plot_coupling_map'.  To install, follow the instructions at https://g |
| `qiskitHumanEval/31` | TypeError: Expected SamplerOptions or dict, got <class 'qiskit_ibm_runtime.options.sampler_options.SamplerOptions'> |
| `qiskitHumanEval/33` | AssertionError: Unexpected result value, got [{'01': 4096}, {'01': 2036, '00': 2060}] |
| `qiskitHumanEval/34` | AssertionError: Value not within expected tolerance |
| `qiskitHumanEval/35` | timeout |
| `qiskitHumanEval/40` | TypeError: Expected SamplerOptions or dict, got <class 'qiskit_ibm_runtime.options.sampler_options.SamplerOptions'> |
| `qiskitHumanEval/43` | qiskit_ibm_runtime.accounts.exceptions.AccountNotFoundError: "Unable to find account. Please make sure an account with the channel name 'ibm_quantum_platform' i |
| `qiskitHumanEval/51` | AssertionError: Unexpected result value |
| `qiskitHumanEval/52` | AssertionError: Unexpected result value |
| `qiskitHumanEval/53` | AssertionError: Unexpected result value |
| `qiskitHumanEval/54` | AssertionError: Unexpected result value |
| `qiskitHumanEval/55` | AssertionError: Unexpected result value |
| `qiskitHumanEval/56` | AssertionError: Unexpected result value |
| `qiskitHumanEval/66` | AssertionError: Value outside expected range |
| `qiskitHumanEval/72` | AssertionError: Unexpected result value |
| `qiskitHumanEval/96` | TypeError: Expected SamplerOptions or dict, got <class 'qiskit_ibm_runtime.options.sampler_options.SamplerOptions'> |
| `qiskitHumanEval/97` | qiskit_ibm_runtime.accounts.exceptions.AccountNotFoundError: "Unable to find account. Please make sure an account with the channel name 'ibm_quantum_platform' i |
| `qiskitHumanEval/98` | qiskit_ibm_runtime.accounts.exceptions.AccountNotFoundError: "Unable to find account. Please make sure an account with the channel name 'ibm_quantum_platform' i |
| `qiskitHumanEval/103` | AssertionError: Expected value not found |
| `qiskitHumanEval/104` | AssertionError: Expected complexity between 189 and 191, got 272 |
| `qiskitHumanEval/121` | TypeError: Expected SamplerOptions or dict, got <class 'qiskit_ibm_runtime.options.sampler_options.SamplerOptions'> |
| `qiskitHumanEval/122` | ModuleNotFoundError: No module named 'qiskit.synthesis.linear.linear_matrix_utils' |
| `qiskitHumanEval/123` | qiskit.exceptions.MissingOptionalLibraryError: "The 'seaborn' library is required to use 'plot_error_map'. You can install it with 'pip install seaborn'." |
| `qiskitHumanEval/128` | TypeError: Expected SamplerOptions or dict, got <class 'qiskit_ibm_runtime.options.sampler_options.SamplerOptions'> |
| `qiskitHumanEval/129` | qiskit_ibm_runtime.accounts.exceptions.AccountNotFoundError: "Unable to find account. Please make sure an account with the channel name 'ibm_quantum_platform' i |
| `qiskitHumanEval/132` | AssertionError: Unexpected result value |
| `qiskitHumanEval/133` | qiskit_ibm_runtime.accounts.exceptions.AccountNotFoundError: "Unable to find account. Please make sure an account with the channel name 'ibm_quantum_platform' i |
| `qiskitHumanEval/134` | qiskit_ibm_runtime.accounts.exceptions.AccountNotFoundError: "Unable to find account. Please make sure an account with the channel name 'ibm_quantum_platform' i |
| `qiskitHumanEval/146` | qiskit_ibm_runtime.accounts.exceptions.AccountNotFoundError: "Unable to find account. Please make sure an account with the channel name 'ibm_quantum_platform' i |

## Limitations

- Small sample: n = 30, so one task is 3.3 percentage points. No significance claims; Wilson intervals are shown for context only.
- One model (GPT-OSS-120B on Groq), one Qiskit version (see `requirements.txt`), one prompt set.
- Correctness is judged only by the benchmark's own tests; some tests sample from a simulator and can be flaky.
- Tasks are restricted to those whose canonical solution passes on Qiskit 2.x in this environment (no IBM Quantum account, no optional drawing libraries). Excluded tasks are listed above.
- Non-determinism was not measured: attempt 0 was not rerun. Even at temperature 0 the API may return different outputs, so a rerun without the cache can give different numbers.
- Error classes are rule-based on the final traceback line; see `docs/VERIFIED.md` for ambiguous cases.

Plots: `results/plots/cumulative_pass.png`, `results/plots/error_classes.png`.
