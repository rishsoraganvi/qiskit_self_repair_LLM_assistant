from qsr.extract import NO_FUNCTION_FOUND, extract_code, extraction_note, has_function


def test_last_python_block_wins():
    text = "```python\nx = 1\n```\nthen\n```python\ndef f():\n    return 2\n```\n"
    assert extract_code(text) == "def f():\n    return 2"


def test_python_block_preferred_over_later_plain_block():
    text = "```python\ndef f(): pass\n```\n```\nnot code\n```"
    assert extract_code(text) == "def f(): pass"


def test_fallback_any_block():
    assert extract_code("Here:\n```\ndef g(): pass\n```") == "def g(): pass"


def test_fallback_raw_text():
    assert extract_code("  def h(): pass  \n") == "def h(): pass"


def test_none_and_crlf():
    assert extract_code(None) == ""
    assert extract_code("```python\r\ndef f(): pass\r\n```") == "def f(): pass"


def test_has_function():
    code = "import x\n\ndef create_circuit(n):\n    pass\n"
    assert has_function(code, "create_circuit")
    assert not has_function(code, "create")
    assert extraction_note(code, "other") == NO_FUNCTION_FOUND
    assert extraction_note(code, "create_circuit") == ""
