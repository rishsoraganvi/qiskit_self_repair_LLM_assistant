from qsr.classify import API_VERSION, LOGIC, OTHER, PASS, SYNTAX, TIMEOUT, classify, final_exception
from qsr.executor import ExecResult


def res(stderr: str = "", passed: bool = False, timed_out: bool = False) -> ExecResult:
    return ExecResult(passed, "", stderr, timed_out, 1.0, None if timed_out else (0 if passed else 1))


TB = 'Traceback (most recent call last):\n  File "{f}", line 3, in <module>\n{last}\n'


def tb(last: str, f: str = "program.py") -> str:
    return TB.format(f=f, last=last)


def test_pass_and_timeout():
    assert classify(res(passed=True)) == PASS
    assert classify(res(timed_out=True)) == TIMEOUT


def test_syntax():
    assert classify(res('  File "program.py", line 1\n    def f(\nSyntaxError: invalid syntax')) == SYNTAX
    assert classify(res("IndentationError: unexpected indent")) == SYNTAX


def test_logic():
    assert classify(res(tb("AssertionError: Expected 3 qubits"))) == LOGIC
    assert classify(res(tb("AssertionError"))) == LOGIC


def test_api_version_types():
    assert classify(res(tb("ImportError: cannot import name 'execute' from 'qiskit'"))) == API_VERSION
    assert classify(res(tb("ModuleNotFoundError: No module named 'qiskit.providers.aer'"))) == API_VERSION
    assert classify(res(tb("AttributeError: 'QuantumCircuit' object has no attribute 'cnot'"))) == API_VERSION
    assert classify(res(tb("qiskit.exceptions.MissingOptionalLibraryError: needs x"))) == API_VERSION


def test_type_error_depends_on_qiskit():
    assert classify(res(tb("TypeError: Sampler.run() got an unexpected keyword argument 'shots'",
                           f="C:/venv/Lib/site-packages/qiskit/primitives/sampler.py"))) == API_VERSION
    assert classify(res(tb("TypeError: QuantumCircuit.__init__() got bad arg"))) == API_VERSION
    assert classify(res(tb("TypeError: unsupported operand type(s) for +: 'int' and 'str'"))) == OTHER
    assert classify(res(tb("TypeError: circuit_to_instruction() got an unexpected keyword argument 'name'")))         == API_VERSION
    assert classify(res(tb("TypeError: f() takes 1 positional argument but 2 were given"))) == API_VERSION


def test_deprecated_or_removed_message():
    assert classify(res(tb("RuntimeError: this function was removed in 2.0"))) == API_VERSION


def test_other():
    assert classify(res(tb("ZeroDivisionError: division by zero"))) == OTHER
    assert classify(res("")) == OTHER


def test_no_function_found_is_other():
    assert classify(res(tb("NameError: name 'f' is not defined")), note="no_function_found") == OTHER


def test_final_exception_uses_last_exception():
    stderr = tb("KeyError: 'a'") + "\nDuring handling...\n" + tb("ValueError: bad")
    assert final_exception(stderr) == ("ValueError", "bad")
