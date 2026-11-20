"""Prompt constants (verbatim from docs/PROMPTS.md). Do not edit during evaluation."""
from __future__ import annotations

FENCE = "```"

SYSTEM_PROMPT = (
    "You are an expert Qiskit developer. Use the latest Qiskit 2.x API. "
    "Return ONLY one complete Python code block containing all necessary imports "
    "and the full function definition. Do not include explanations or test code."
)

GENERATION_TEMPLATE = (
    "Complete the following task.\n"
    "\n"
    "{prompt}\n"
    "\n"
    "Return the complete, runnable code (imports + function) in a single " + FENCE + "python block."
)

REPAIR_TEMPLATE = (
    "Your previous solution failed.\n"
    "\n"
    "Original task:\n"
    "{prompt}\n"
    "\n"
    "Your previous code:\n"
    + FENCE + "python\n"
    "{last_code}\n"
    + FENCE + "\n"
    "\n"
    "Execution result (last part of the output):\n"
    + FENCE + "\n"
    "{error_tail}\n"
    + FENCE + "\n"
    "\n"
    "Fix the code. Use the latest Qiskit 2.x API. Return the complete corrected code "
    "(imports + function) in a single " + FENCE + "python block."
)

Messages = list[dict[str, str]]


def generation_messages(task_prompt: str) -> Messages:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": GENERATION_TEMPLATE.format(prompt=task_prompt)},
    ]


def repair_messages(task_prompt: str, last_code: str, error_tail: str) -> Messages:
    """Fresh conversation per repair (system + repair prompt), never a growing chat."""
    user = REPAIR_TEMPLATE.format(prompt=task_prompt, last_code=last_code, error_tail=error_tail)
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
