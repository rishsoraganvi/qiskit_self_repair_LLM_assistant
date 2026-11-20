# Demo script: Qiskit Self-Repair LLM Assistant

A guide for presenting the project to the professor: what to say, which commands to run, and which results to show.
It's planned for **about 12–15 minutes**, plus questions.

> Slides: the "Qiskit Self-Repair LLM Assistant" deck (6 slides) follows the same order as this script:
> 1 Cover · 2 Problem · 3 Solution · 4 Architecture · 5 Evaluation results · 6 Observations and limitations.
> Repo: https://github.com/rishsoraganvi/qiskit_self_repair_LLM_assistant

---

## 0. Before the professor arrives (5 min)

Open **PowerShell** and get ready:

```powershell
cd C:\code\qiskit-selfrepair
.\.venv\Scripts\Activate.ps1
```

Check that everything works (should print `44 passed`):

```powershell
python -m pytest -q
```

Open these in advance so you aren't searching for them during the demo:
- `results/summary.md`
- `results/plots/cumulative_pass.png`
- `results/plots/error_classes.png`
- the slide deck

> Nothing in the demo calls the Groq API. Every LLM response is cached in `cache/`, so the demo works offline and costs 0 tokens.
> Don't delete `cache/` or `runs/attempts.jsonl` before the demo.

---

## 1. The problem (1–2 min, slides 1–2)

**What to say:**

> "LLMs are trained mostly on older Qiskit code. Qiskit 1.0 and 2.0 removed many APIs, so models often write code that looks right but fails right away, for example `from qiskit import Aer` or `Sampler(backend=...)`.
>
> Our research question: if we **run** the model's code and **feed the error message back** to it, up to 3 times, does correctness go up compared with a single attempt? And which kinds of errors does this loop fix?"

**Key facts:**
- Model: **GPT-OSS-120B** via the Groq API (free tier)
- Benchmark: **Qiskit HumanEval** (151 tasks, each with a hidden test)
- Quantum SDK: **Qiskit 2.6.2**

---

## 2. The solution (2 min, slide 3)

**What to say:**

> "The loop has four steps:
> 1. **Generate:** the model gets the task and returns complete code.
> 2. **Execute:** we run that code with the benchmark's test in an isolated subprocess, with a 60-second timeout.
> 3. **Check:** if the test passes, we're done.
> 4. **Repair:** if it fails, we send the task, the model's previous code, and the last 4,000 characters of the error back to the model. Then we go back to step 2. At most 3 repairs.
>
> Three design rules keep the comparison fair:
> - **Paired design:** attempt 0 *is* the baseline, and the loop reuses it, so every task is compared with itself.
> - **Stop on first pass:** a passing task is never retried, so the loop can't make anything worse.
> - **Nothing changes between attempts:** same model, same parameters, same prompts. The model **never sees the test code or the reference answer**, only the error output."

---

## 3. The architecture (2 min, slide 4)

**What to say:**

> "It's a command-line tool with one command per step. Two modules matter most:
> - **`llm.py`** is the *only* place that calls Groq. It caches every response on disk under a hash of the request, rate-limits requests and tokens per minute, retries on HTTP 429, and stops cleanly at a daily token budget. Because of the cache, re-running anything costs zero API calls.
> - **`executor.py`** runs generated code in a separate process, in a temp folder, with a timeout. The API key is removed from its environment. We never `exec()` model output inside our own program.
>
> Errors are classified by rules into 5 classes: syntax, api_version, logic, timeout and other."

**Show the code layout (optional):**

```powershell
Get-ChildItem src\qsr
```

---

## 4. Live demo: the commands (5–6 min)

Run these **one at a time** and explain each output.

### 4.1 Validate the benchmark

```powershell
python -m qsr validate
```

**Expected:** `121 valid / 30 invalid`, followed by the list of invalid tasks with reasons.

**What to say:**
> "Before testing the model, we ran each task's **official reference solution** on Qiskit 2.6.2. 30 of the 151 fail even with the official answer: they need an IBM Quantum account, their tests are outdated, or they need extra drawing libraries. Those tasks can't measure the model, so we excluded them."

### 4.2 Sample the 30 tasks

```powershell
python -m qsr sample --n 30 --seed 42
```

**Expected:** `Subset: 30 tasks (seed 42)` and the task numbers.

**What to say:**
> "We sample 30 of the valid tasks with a fixed seed. The sample is then frozen, and the tool refuses to resample with different settings."

### 4.3 Baseline (single shot)

```powershell
python -m qsr baseline
```

**Expected:** `Baseline pass@1: 17/30 = 56.7%` and `API calls this run: 0`

**What to say:**
> "This is attempt 0: one answer per task, no feedback. **17 of 30 pass.** Note the zero API calls: everything comes from the cache."

### 4.4 Repair loop

```powershell
python -m qsr repair --max-repairs 3
```

**Expected:** `After up to 3 repairs: 25/30 passing = 83.3%` and `API calls this run: 0`

**What to say:**
> "Each failing task gets up to 3 repairs. **25 of 30 now pass**: 8 more tasks fixed, 0 broken."

### 4.5 Report

```powershell
python -m qsr report
```

**Expected:**
```
Baseline pass@1:         17/30 = 56.7%
Post-repair pass rate:   25/30 = 83.3%
  fixed in round 1: 3   (pass rate k=1: 20/30 = 66.7%)
  fixed in round 2: 3   (pass rate k=2: 23/30 = 76.7%)
  fixed in round 3: 2   (pass rate k=3: 25/30 = 83.3%)
Never fixed: 5   Broken by loop: 0
```

Then **open the two plots** and `results/summary.md`.

### 4.6 One real repair, step by step (the best moment of the demo)

Show how task 28 was fixed:

```powershell
python -X utf8 -c "import json; [print(a['attempt'], a['error_class'], a['stderr_tail'].strip().splitlines()[-1][:110] if a['stderr_tail'] else 'PASS') for a in map(json.loads, open('runs/attempts.jsonl', encoding='utf-8')) if a['task_id']=='qiskitHumanEval/28']"
```

**Expected:**
```
0 api_version ImportError: cannot import name 'Aer' from 'qiskit' ...
1 api_version TypeError: int() argument must be ... not 'Counts'
2 pass PASS
```

**What to say:**
> "Task 28 asks for a histogram of two Bell states.
> - **Attempt 0:** the model imported `Aer` from `qiskit`, which was removed in Qiskit 1.0.
> - **Attempt 1:** after seeing the ImportError, it removed that import, but then passed the results to the plot the wrong way.
> - **Attempt 2:** after seeing that error, it called `get_counts()` correctly, and the test passed.
>
> The model fixed two different bugs, one per round, using only the error messages."

### 4.7 (Optional, about 5 min) Prove the results are reproducible

Only if there's time. This re-executes all 60 generated programs from the cache:

```powershell
Move-Item runs\attempts.jsonl runs\attempts.backup.jsonl
```

```powershell
python -m qsr run-all
```

**Expected:** the same `17/30` and `25/30`, still with 0 API calls. Then restore the original file:

```powershell
Move-Item -Force runs\attempts.backup.jsonl runs\attempts.jsonl
```

---

## 5. Results to show (slide 5)

| Metric | Result |
|---|---|
| Baseline pass@1 | **17/30 = 56.7%** |
| After 1 repair | 20/30 = 66.7% (+3) |
| After 2 repairs | 23/30 = 76.7% (+3) |
| After 3 repairs | **25/30 = 83.3%** (+2) |
| Never fixed | 5 tasks (14, 15, 32, 37, 141) |
| Broken by the loop | 0 |
| 95% interval (Wilson) | baseline 39–73%, after repair 66–93% |
| Total tokens | 26,836 prompt + 23,033 completion (~50K) |
| API calls for the reported run | 60 (30 baseline + 30 repair) |

**Baseline failures by error class:**

| Class | Failed at attempt 0 | Fixed by repair |
|---|---|---|
| api_version | 10 | 5 (50%) |
| other | 2 | 2 (100%) |
| logic | 1 | 1 (100%) |
| syntax | 0 | – |
| timeout | 0 | – |

---

## 6. Observations (2 min, slide 6)

**What to say:**

1. **Outdated APIs are the main problem.** 10 of the 13 baseline failures were `api_version` errors. The model's *knowledge* is out of date; its reasoning is mostly fine.
2. **When the error names the broken call, repair works.** "cannot import name 'Aer'" or "unexpected keyword argument": the model usually finds the 2.x form within 1–2 tries.
3. **The V2 primitives defeat it.** 4 of the 5 never-fixed tasks use `Sampler(backend=...)` or `Estimator(backend=...)`. Fixing them needs a different API design, not a renamed import, and the model never found it.
4. **It's cheap and safe.** About 830 tokens per call with low reasoning effort, and no passing task was ever broken.

**Lessons from building the harness** (not on the slides; mention them out loud or keep them for questions):
- The benchmark's tests use names imported in the task *prompt*. The model sometimes rewrote those imports, so correct answers were failing. We now add the prompt's imports back. This re-scored the baseline from 15 to 17 **without any new API calls**.
- Error messages contained folder paths, which changed the repair prompts depending on where the repo lived. We now replace them with placeholders, so the cache works in any folder. We verified this in a fresh copy with no API key.
- Running Qiskit Aer simulations in parallel caused false failures, so validation runs one task at a time.

---

## 7. Likely questions from the professor

**Q: Why only 30 tasks?**
A: The 5-day timeline and Groq's free-tier limits. We say so openly: with n = 30, one task is 3.3 percentage points, so we report counts next to percentages, and we make no claims of statistical significance.

**Q: Isn't 17 → 25 just luck?**
A: The design is paired: each task is compared with itself, and the loop can only add passes, never remove them. The 95% intervals overlap (39–73% vs 66–93%), so we report it as a clear improvement on this sample, not a proven effect. A larger run would be the next step.

**Q: Could the model be cheating, for example by seeing the test?**
A: No. The prompts contain only the task description, the model's own previous code and the error output. The test code and reference solution are never sent; `docs/PROMPTS.md` and `src/qsr/prompts.py` show this.

**Q: Why exclude 30 tasks? Isn't that cherry-picking?**
A: Those tasks fail *even with the benchmark's official solution* on Qiskit 2.x, so a model can't pass them either. We excluded them **before** running the model, sampled with a fixed seed, and list every excluded task with its reason in `summary.md`.

**Q: Why low reasoning effort and temperature 0?**
A: Low effort keeps us within the free-tier token budget, at about 830 tokens per call. Temperature 0 makes the outputs as repeatable as possible. Both were fixed before the run and are the same for every attempt.

**Q: How do you classify errors?**
A: By rules on the last exception in the traceback. For example, ImportError or AttributeError counts as `api_version`, and AssertionError counts as `logic`. We hand-checked 13 classifications: 11 were clearly correct and 2 were ambiguous. Both are documented in `docs/VERIFIED.md`.

**Q: You changed the harness after seeing results. Isn't that a problem?**
A: We changed how code is *executed*, not the prompts or model settings. Adding the prompt's imports matches how the original benchmark runs (prompt + solution). The LLM outputs were reused from the cache unchanged, and all the old records are kept in `runs/discarded/` for transparency.

**Q: Is the result reproducible?**
A: Yes. A fresh copy with no API key reproduced identical results from the cache, with 0 API calls. Without the cache, a new run could differ slightly, because LLM outputs aren't perfectly deterministic. We list that as a limitation.

**Q: What would you do next?**
A:
- Run on all 121 valid tasks.
- Measure run-to-run variation.
- Give the model current Qiskit documentation (retrieval), which should help with the V2-primitives failures.

That's out of scope for this project, but it's the natural next step.

---

## 8. Limitations to state yourself (before you're asked)

- Small sample: 30 tasks; one task = 3.3 points.
- One model, one Qiskit version, low reasoning effort.
- "Correct" means the benchmark's test passes, nothing more.
- Run-to-run variation wasn't measured.
- 30 benchmark tasks couldn't be used on Qiskit 2.x.

---

## Quick reference: all demo commands

```powershell
cd C:\code\qiskit-selfrepair
.\.venv\Scripts\Activate.ps1
python -m pytest -q
python -m qsr validate
python -m qsr sample --n 30 --seed 42
python -m qsr baseline
python -m qsr repair --max-repairs 3
python -m qsr report
python -m qsr run-all
```
