"""Rule-based error classifier (taxonomy in docs/EVAL_SPEC.md)."""
from __future__ import annotations

import re

from .executor import ExecResult
from .extract import NO_FUNCTION_FOUND

PASS = "pass"
TIMEOUT = "timeout"
SYNTAX = "syntax"
API_VERSION = "api_version"
LOGIC = "logic"
OTHER = "other"
ERROR_CLASSES = (SYNTAX, API_VERSION, LOGIC, TIMEOUT, OTHER)

_EXC_LINE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Warning|Exit|Interrupt))(?::\s*(.*))?$")
_API_TYPES = {"ImportError", "ModuleNotFoundError", "AttributeError", "MissingOptionalLibraryError"}
# Call-signature mismatches (renamed/removed keyword or positional args) are API drift.
_SIGNATURE = re.compile(r"unexpected keyword argument|positional argument|required (?:positional|keyword)")
_FRAME = re.compile(r'^\s*File "([^"]+)"', re.MULTILINE)
# Qiskit object names that mark a TypeError as an API mismatch ("TypeError mentioning Qiskit objects/args").
_QISKIT_NAMES = re.compile(
    r"qiskit|QuantumCircuit|QuantumRegister|ClassicalRegister|Sampler|Estimator|Aer|Backend|transpile|"
    r"PassManager|Operator|Statevector|DensityMatrix|SparsePauliOp|Pauli|Gate|Instruction|Parameter|"
    r"CouplingMap|Target|Layout|PrimitiveResult|PubResult|BitArray|Session|Options"
)


def final_exception(stderr: str) -> tuple[str, str]:
    """Return (short exception type, message) of the last exception line in a traceback."""
    for line in reversed(stderr.strip().splitlines()):
        m = _EXC_LINE.match(line.strip())
        if m:
            return m.group(1).rsplit(".", 1)[-1], (m.group(2) or "")
    return "", ""


def _last_frame_in_qiskit(stderr: str) -> bool:
    frames = _FRAME.findall(stderr)
    return bool(frames) and "qiskit" in frames[-1].lower()


def classify(result: ExecResult, note: str = "") -> str:
    if result.passed:
        return PASS
    if result.timed_out:
        return TIMEOUT
    if note == NO_FUNCTION_FOUND:
        return OTHER
    exc_type, message = final_exception(result.stderr)
    if exc_type in {"SyntaxError", "IndentationError", "TabError"}:
        return SYNTAX
    if exc_type == "AssertionError":
        return LOGIC
    if exc_type in _API_TYPES:
        return API_VERSION
    if exc_type == "TypeError" and (
        _QISKIT_NAMES.search(message) or _SIGNATURE.search(message) or _last_frame_in_qiskit(result.stderr)
    ):
        return API_VERSION
    if re.search(r"deprecat|removed", message, re.IGNORECASE):
        return API_VERSION
    return OTHER
