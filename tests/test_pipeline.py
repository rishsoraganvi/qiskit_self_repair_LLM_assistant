"""End-to-end baseline -> repair -> report with a fake LLM client (no network)."""
import json
from dataclasses import replace

import pytest

from qsr.attempts import AttemptStore
from qsr.baseline import run_baseline
from qsr.dataset import Task, save_tasks
from qsr.llm import LLMClient
from qsr.repair import MissingBaseline, run_repair
from qsr.report import build_report, wilson
from qsr.sample import SubsetError, draw_sample, sample
from tests.test_llm import FakeClient, fake_completion, make_cfg


def task(i: int, expected: int) -> Task:
    return Task(f"qiskitHumanEval/{i}", f"def f{i}():\n    '''return {expected}'''\n", f"    return {expected}\n",
                f"def check(candidate):\n    assert candidate() == {expected}\n", f"f{i}")


TASKS = [task(1, 1), task(2, 2), task(3, 3)]


def block(code: str) -> object:
    return fake_completion(f"Sure.\n```python\n{code}\n```")


class RoutingClient(FakeClient):
    """Answer by inspecting which task the prompt is about and whether it is a repair."""

    def __init__(self):
        super().__init__([])

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        user = kwargs["messages"][-1]["content"]
        repair = user.startswith("Your previous solution failed")
        if "def f1" in user:
            return block("def f1():\n    return 1")
        if "def f2" in user:
            return block("def f2():\n    return 2" if repair else "def f2(:\n    return 2")
        return block("def f3():\n    return 0")  # never fixed


@pytest.fixture
def cfg(tmp_path):
    c = replace(make_cfg(tmp_path), exec_timeout_s=30, subset_size=3)
    save_tasks(c.paths.subset, TASKS)
    save_tasks(c.paths.valid_tasks, TASKS)
    c.paths.invalid_tasks.write_text(json.dumps([{"task_id": "qiskitHumanEval/9", "reason": "x"}]))
    return c


def test_full_pipeline_and_zero_call_rerun(cfg):
    fake = RoutingClient()
    b = run_baseline(cfg, LLMClient(cfg, client=fake))
    assert (b.passed, b.done, b.api_calls) == (1, 3, 3)

    r = run_repair(cfg, 3, LLMClient(cfg, client=fake))
    store = AttemptStore(cfg.paths.attempts)
    assert [a.attempt for a in store.for_task("qiskitHumanEval/1")] == [0]
    assert [a.attempt for a in store.for_task("qiskitHumanEval/2")] == [0, 1]
    assert [a.attempt for a in store.for_task("qiskitHumanEval/3")] == [0, 1, 2, 3]
    assert store.get("qiskitHumanEval/2", 0).error_class == "syntax"
    assert store.get("qiskitHumanEval/3", 0).error_class == "logic"
    assert r.passed == 2 and r.api_calls == 4

    # Repair prompt carries the previous code and error, never the test.
    repair_prompt = fake.calls[3]["messages"][-1]["content"]
    assert "def f2(:" in repair_prompt and "SyntaxError" in repair_prompt
    assert "check(" not in repair_prompt and "assert candidate" not in repair_prompt

    # Rerunning both phases costs zero API calls and adds no attempts.
    n_lines = len(cfg.paths.attempts.read_text().splitlines())
    empty = FakeClient([])
    assert run_baseline(cfg, LLMClient(cfg, client=empty)).api_calls == 0
    assert run_repair(cfg, 3, LLMClient(cfg, client=empty)).api_calls == 0
    assert empty.calls == []
    assert len(cfg.paths.attempts.read_text().splitlines()) == n_lines

    # Reproduce from cache: drop attempts.jsonl, rerun, same results and zero calls.
    cfg.paths.attempts.unlink()
    run_baseline(cfg, LLMClient(cfg, client=empty))
    r2 = run_repair(cfg, 3, LLMClient(cfg, client=empty))
    assert r2.passed == 2 and empty.calls == []
    assert all(a.cache_hit for a in AttemptStore(cfg.paths.attempts).all())

    s = build_report(cfg)
    assert s.baseline_pass == 1 and s.pass_by_k == {0: 1, 1: 2, 2: 2, 3: 2}
    assert s.fixed_by_round == {1: 1, 2: 0, 3: 0}
    assert s.never_fixed == ["qiskitHumanEval/3"]
    assert s.mix_at_0 == {"syntax": 1, "logic": 1} and s.mix_final == {"logic": 1}
    assert s.fix_rate_by_class == {"syntax": (1, 1), "logic": (0, 1)}
    assert s.api_calls == 7  # only the first real run hit the API
    out = cfg.paths.results
    for p in ("results.csv", "summary.md", "plots/cumulative_pass.png", "plots/error_classes.png"):
        assert (out / p).exists()
    md = (out / "summary.md").read_text(encoding="utf-8")
    assert "1/3 = 33.3%" in md and "qiskitHumanEval/9" in md and "Limitations" in md


def test_repair_requires_baseline(cfg):
    with pytest.raises(MissingBaseline):
        run_repair(cfg, 3, LLMClient(cfg, client=FakeClient([])))


def test_sample_is_seeded_and_frozen(tmp_path):
    tasks = [task(i, i) for i in range(50)]
    a = draw_sample(tasks, 10, 42)
    assert a == draw_sample(list(reversed(tasks)), 10, 42)
    assert a != draw_sample(tasks, 10, 43)
    c = make_cfg(tmp_path)
    save_tasks(c.paths.valid_tasks, tasks)
    first = sample(c, 10, 42)
    assert sample(c, 10, 42) == first
    with pytest.raises(SubsetError):
        sample(c, 10, 7)


def test_wilson():
    lo, hi = wilson(15, 30)
    assert lo == pytest.approx(0.332, abs=0.002) and hi == pytest.approx(0.668, abs=0.002)
    assert wilson(0, 0) == (0.0, 0.0)
