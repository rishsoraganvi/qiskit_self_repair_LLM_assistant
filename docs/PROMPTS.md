# PROMPTS

Store these as constants in `src/qsr/prompts.py`. Do not tweak wording during evaluation; changing prompts after seeing results invalidates the comparison.

## System prompt (both phases)
```
You are an expert Qiskit developer. Use the latest Qiskit 2.x API. Return ONLY one complete Python code block containing all necessary imports and the full function definition. Do not include explanations or test code.
```

## Generation prompt (attempt 0)
```
Complete the following task.

{task.prompt}

Return the complete, runnable code (imports + function) in a single ```python block.
```

## Repair prompt (attempts 1-3)
```
Your previous solution failed.

Original task:
{task.prompt}

Your previous code:
```python
{last_code}
```

Execution result (last part of the output):
```
{error_tail}
```

Fix the code. Use the latest Qiskit 2.x API. Return the complete corrected code (imports + function) in a single ```python block.
```
Notes:
- Send each repair as a fresh conversation (system + this prompt), not a growing chat. This keeps token use bounded and the cache key simple.
- Do NOT include the test code or the canonical solution in any prompt.
- If a task failed because of a hidden assertion, `error_tail` may contain only a traceback; that is expected.

## Code extraction rules (`extract.py`)
1. Take the last ```python fenced block; fall back to any fenced block; fall back to the raw text.
2. Strip leading/trailing whitespace.
3. If no `def {entry_point}` appears in the result, mark the attempt as `other` with note `no_function_found` and still execute (it will fail fast).
4. Ignore any separate reasoning field returned by the API; only the final message content is used.
