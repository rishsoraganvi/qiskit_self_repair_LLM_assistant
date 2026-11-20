import sys

from qsr.dataset import Task
from qsr.executor import assemble_program, execute, prompt_imports, run_program, tail

TASK = Task(
    task_id="t/0",
    prompt="def add(a, b):\n",
    canonical_solution="    return a + b\n",
    test="def check(candidate):\n    assert candidate(2, 3) == 5\n",
    entry_point="add",
)


def test_pass():
    r = execute(TASK.prompt + TASK.canonical_solution, TASK, timeout_s=30)
    assert r.passed and not r.timed_out and r.returncode == 0


def test_fail_assertion():
    r = execute("def add(a, b):\n    return a - b\n", TASK, timeout_s=30)
    assert not r.passed and not r.timed_out
    assert "AssertionError" in r.stderr


def test_syntax_error():
    r = execute("def add(a, b)\n    return a + b\n", TASK, timeout_s=30)
    assert not r.passed
    assert "SyntaxError" in r.stderr


def test_timeout():
    r = run_program("import time\ntime.sleep(30)\n", timeout_s=1)
    assert r.timed_out and not r.passed and r.returncode is None
    assert r.seconds < 10


def test_runs_in_temp_dir_not_repo():
    r = run_program("import os, pathlib\nassert pathlib.Path('program.py').exists()\nprint(os.getcwd())\n", timeout_s=30)
    assert r.passed
    assert r.stdout.strip() == "<workdir>"  # temp dir is scrubbed to a stable token


def test_api_key_not_leaked(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "secret")
    r = run_program("import os\nassert 'GROQ_API_KEY' not in os.environ\n", timeout_s=30)
    assert r.passed


def test_assemble_calls_check():
    prog = assemble_program("CODE", TASK)
    assert prog.startswith("CODE")
    assert prog.rstrip().endswith("check(add)")


def test_tail():
    assert tail("abcdef", 3) == "def"
    assert tail("ab", 3) == "ab"


def test_prompt_imports_prepended():
    prompt = 'from math import (\n    sqrt,\n)\nimport os\ndef r(x):\n    """doc"""\n'
    t = Task("t/1", prompt, "    return sqrt(x)\n", "def check(candidate):\n    assert sqrt(4) == candidate(4)\n", "r")
    assert prompt_imports(t.prompt) == "from math import (\n    sqrt,\n)\nimport os"
    # Model code omits the import the *test* needs; the harness still supplies it.
    r = execute("import math\ndef r(x):\n    return math.sqrt(x)\n", t, timeout_s=30)
    assert r.passed, r.stderr


def test_no_prompt_imports():
    assert prompt_imports("def f():\n    pass\n") == ""
    assert assemble_program("CODE", TASK).startswith("CODE")


def test_venv_and_python_paths_scrubbed():
    r = run_program("import qiskit, os\nraise RuntimeError(os.path.dirname(qiskit.__file__))\n", timeout_s=60)
    assert "<venv>" in r.stderr
    assert sys.prefix not in r.stderr
