"""Tests for scripts/benchmark.py: the compare logic behind "benchmark scores must not go down".

These are pure-function tests with small hand-made metrics, so they need no M3 report and no
network. A final test checks that the committed benchmarks/baseline.json is well formed.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.m3(suite_name="scripts")

ROOT = Path(__file__).resolve().parents[2]


def load_benchmark() -> ModuleType:
    spec = importlib.util.spec_from_file_location("script_benchmark", ROOT / "scripts/benchmark.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bm = load_benchmark()

TOOLS = ["arxiv_get_paper", "arxiv_search", "osv_query_package"]


def feedback(tests: list[tuple[str, str, int]], *, rate: float | None = 1.0) -> dict:
    """A minimal feedback.json: ``(node_id, outcome, number of execution ids)`` per test."""
    stats = {}
    if rate is not None:
        stats = {"m3.matcher.to_have_tool_call.v1": {"pass_rate": rate, "evaluation_count": 3}}
    executions = sum(n for _, _, n in tests)
    return {
        "summary": {"run_status": "finished", "terminal_executions": executions},
        "tests": [
            {"node_id": node, "outcome": outcome, "execution_ids": [f"e{i}"] * count}
            for i, (node, outcome, count) in enumerate(tests)
        ],
        "evaluation_stats": stats,
    }


BASE_TESTS = [
    ("m3_tests/adapters/arxiv/test_arxiv.py::test_search", "passed", 1),
    ("m3_tests/adapters/arxiv/test_arxiv.py::test_paper", "passed", 1),
    ("m3_tests/adapters/osv/test_osv.py::test_query", "passed", 1),
    ("m3_tests/core/test_text.py::test_truncate", "passed", 0),
]


@pytest.fixture
def baseline() -> dict:
    return bm.extract_metrics(feedback(BASE_TESTS), TOOLS)


def statuses(rows: list) -> dict[str, str]:
    return {row.metric: row.status for row in rows}


def test_group_of_names_the_adapter_or_the_top_directory() -> None:
    assert bm.group_of("m3_tests/adapters/osv/test_osv.py::test_x[a-b]") == "adapters/osv"
    assert bm.group_of("m3_tests/agent/test_fixture_agent.py::test_x") == "agent"
    assert bm.group_of("m3_tests/core/test_http.py::test_y") == "core"


def test_extract_counts_executions_per_group_and_leaves_out_untouched_groups(
    baseline: dict,
) -> None:
    assert baseline["passing_tests"] == sorted(n for n, _, _ in BASE_TESTS)
    assert baseline["m3_calls"] == {
        "executions_total": 3,
        "tests_with_execution": {"adapters/arxiv": 2, "adapters/osv": 1},
    }
    assert baseline["evaluator_pass_rates"] == {"m3.matcher.to_have_tool_call.v1": 1.0}
    assert baseline["tools"] == TOOLS


def test_an_identical_run_is_all_same(baseline: dict) -> None:
    rows = bm.compare(baseline, copy.deepcopy(baseline))
    assert {row.status for row in rows} == {bm.SAME}
    assert not bm.regressions(rows)


def test_a_removed_test_is_a_regression(baseline: dict) -> None:
    run = [t for t in BASE_TESTS if not t[0].endswith("test_paper")]
    rows = bm.compare(baseline, bm.extract_metrics(feedback(run), TOOLS))
    assert statuses(rows)["Passing tests"] == bm.DOWN
    assert "test_paper: missing from this run" in bm.describe(bm.regressions(rows))


def test_a_failing_test_is_a_regression_and_says_how_it_failed(baseline: dict) -> None:
    run = [(n, "failed" if n.endswith("test_query") else o, c) for n, o, c in BASE_TESTS]
    rows = bm.compare(baseline, bm.extract_metrics(feedback(run), TOOLS))
    assert statuses(rows)["Passing tests"] == bm.DOWN
    assert "test_query: now failed" in bm.describe(bm.regressions(rows))


def test_replacing_a_test_with_a_new_one_is_still_a_regression(baseline: dict) -> None:
    run = [(n.replace("test_paper", "test_other"), o, c) for n, o, c in BASE_TESTS]
    rows = bm.compare(baseline, bm.extract_metrics(feedback(run), TOOLS))
    assert statuses(rows)["Passing tests"] == bm.DOWN


def test_new_tests_and_new_calls_are_improvements(baseline: dict) -> None:
    run = [*BASE_TESTS, ("m3_tests/adapters/pypi/test_pypi.py::test_new", "passed", 1)]
    rows = bm.compare(baseline, bm.extract_metrics(feedback(run), [*TOOLS, "pypi_get_package"]))
    found = statuses(rows)
    assert found["Passing tests"] == bm.UP
    assert found["M3-recorded tests: adapters/pypi"] == bm.UP
    assert found["M3 executions (total)"] == bm.UP
    assert found["Tools"] == bm.UP
    assert not bm.regressions(rows) and bm.improvements(rows)


def test_a_test_that_stops_calling_the_server_lowers_the_adapter_coverage(baseline: dict) -> None:
    run = [(n, o, 0 if n.endswith("test_search") else c) for n, o, c in BASE_TESTS]
    found = statuses(bm.compare(baseline, bm.extract_metrics(feedback(run), TOOLS)))
    assert found["Passing tests"] == bm.SAME
    assert found["M3-recorded tests: adapters/arxiv"] == bm.DOWN
    assert found["M3 executions (total)"] == bm.DOWN


def test_a_group_that_vanishes_is_a_regression(baseline: dict) -> None:
    run = [t for t in BASE_TESTS if "/osv/" not in t[0]]
    found = statuses(bm.compare(baseline, bm.extract_metrics(feedback(run), TOOLS)))
    assert found["M3-recorded tests: adapters/osv"] == bm.DOWN


def test_a_lower_or_missing_evaluator_pass_rate_is_a_regression(baseline: dict) -> None:
    name = "Evaluator pass rate: m3.matcher.to_have_tool_call.v1"
    lower = bm.extract_metrics(feedback(BASE_TESTS, rate=0.5), TOOLS)
    assert statuses(bm.compare(baseline, lower))[name] == bm.DOWN
    missing = bm.extract_metrics(feedback(BASE_TESTS, rate=None), TOOLS)
    assert statuses(bm.compare(baseline, missing))[name] == bm.DOWN


def test_a_removed_tool_is_a_regression_and_a_new_one_is_not(baseline: dict) -> None:
    rows = bm.compare(baseline, bm.extract_metrics(feedback(BASE_TESTS), TOOLS[:-1]))
    assert statuses(rows)["Tools"] == bm.DOWN
    assert "osv_query_package: removed" in bm.describe(bm.regressions(rows))
    renamed = bm.extract_metrics(feedback(BASE_TESTS), [*TOOLS[:-1], "osv_search"])
    assert statuses(bm.compare(baseline, renamed))["Tools"] == bm.DOWN


def test_float_noise_in_a_pass_rate_is_not_a_regression() -> None:
    assert bm._status(2 / 3, 0.6666666666) == bm.SAME
    assert bm._status(1.0, 0.99) == bm.DOWN


def test_the_table_has_the_four_columns_and_one_row_per_metric(baseline: dict) -> None:
    rows = bm.compare(baseline, baseline)
    lines = bm.render_table(rows).splitlines()
    assert [cell.strip() for cell in lines[0].split("|")[1:-1]] == [
        "Metric",
        "Baseline",
        "Now",
        "Status",
    ]
    assert len(lines) == len(rows) + 2
    assert "Passing tests" in lines[2] and bm.SAME in lines[2]


# The rules CI applies to a pull request.


def lower(metrics: dict) -> dict:
    out = copy.deepcopy(metrics)
    out["tools"] = out["tools"][:-1]
    return out


def test_judge_without_a_pr_baseline_fails_on_any_drop(baseline: dict) -> None:
    verdict = bm.judge(baseline, lower(baseline))
    assert verdict.failed
    assert "benchmark scores went down" in verdict.messages[0]
    assert "make test && make benchmark" in verdict.messages[0]
    assert bm.APPROVAL_LABEL in verdict.messages[0]


def test_judge_passes_an_identical_run_and_hints_at_a_raised_score(baseline: dict) -> None:
    assert not bm.judge(baseline, baseline).failed
    better = copy.deepcopy(baseline)
    better["m3_calls"]["executions_total"] += 1
    verdict = bm.judge(baseline, better)
    assert not verdict.failed
    assert "make benchmark-baseline" in verdict.messages[0]


def test_judge_fails_a_pr_whose_run_is_lower_than_main(baseline: dict) -> None:
    verdict = bm.judge(baseline, lower(baseline), pr_base=copy.deepcopy(baseline))
    assert verdict.failed
    assert sum("FAIL" in m for m in verdict.messages) == 1  # the same rows are not listed twice


def test_judge_fails_a_pr_that_lowers_the_baseline_file_even_if_the_run_matches(
    baseline: dict,
) -> None:
    pr_baseline = lower(baseline)
    verdict = bm.judge(baseline, baseline, pr_base=pr_baseline)
    assert verdict.failed and "Tools" in verdict.messages[0]


def test_judge_lets_the_label_wave_through_a_drop_that_the_baseline_file_follows(
    baseline: dict,
) -> None:
    run = lower(baseline)
    verdict = bm.judge(baseline, run, pr_base=copy.deepcopy(run), is_approved=True)
    assert not verdict.failed
    assert "label" in verdict.messages[0]


def test_judge_does_not_let_the_label_wave_through_a_stale_baseline_file(baseline: dict) -> None:
    verdict = bm.judge(baseline, lower(baseline), pr_base=copy.deepcopy(baseline), is_approved=True)
    assert verdict.failed
    assert "promises more than this run delivers" in "\n".join(verdict.messages)


def test_judge_accepts_a_pr_that_raises_the_baseline_and_meets_it(baseline: dict) -> None:
    better = copy.deepcopy(baseline)
    better["m3_calls"]["executions_total"] += 5
    assert not bm.judge(baseline, better, pr_base=better).failed


def test_judge_rejects_a_pr_baseline_that_is_higher_than_its_own_run(baseline: dict) -> None:
    claimed = copy.deepcopy(baseline)
    claimed["m3_calls"]["executions_total"] += 5
    verdict = bm.judge(baseline, baseline, pr_base=claimed)
    assert verdict.failed and "promises more" in verdict.messages[0]


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ('["adapter", "benchmark-change-approved"]', True),
        ('["adapter"]', False),
        ("[]", False),
        ("", False),
        ("not json", False),
        ('"benchmark-change-approved"', False),
    ],
)
def test_the_approval_label_is_read_from_a_json_list(labels: str, expected: bool) -> None:
    assert bm.approved({bm.LABELS_ENV: labels}) is expected
    assert bm.approved({}) is False


def test_report_problems_flags_an_unfinished_or_empty_run() -> None:
    assert bm.report_problems(feedback(BASE_TESTS)) == []
    broken = feedback(BASE_TESTS)
    broken["summary"]["run_status"] = "running"
    assert "did not finish" in bm.report_problems(broken)[0]
    assert "no tests" in bm.report_problems({"summary": {"run_status": "finished"}})[0]


# The nightly agent comparison.


def agent(**cases: tuple[int, int]) -> dict:
    return {
        "harness": "codex",
        "trials": 3,
        "results": {k: {"tool": "t", "passed": p, "total": n} for k, (p, n) in cases.items()},
    }


def test_agent_rates_compare_as_fractions_not_counts() -> None:
    base = agent(a=(1, 1), b=(2, 3), c=(3, 3))
    now = agent(a=(3, 3), b=(1, 3), c=(2, 3))
    found = statuses(bm.compare_agent(base, now))
    assert found == {
        "Agent prompt: a": bm.SAME,  # 1/1 and 3/3 are the same rate
        "Agent prompt: b": bm.DOWN,
        "Agent prompt: c": bm.DOWN,
    }


def test_an_agent_prompt_that_is_no_longer_measured_is_a_drop() -> None:
    found = statuses(bm.compare_agent(agent(a=(1, 1), b=(1, 1)), agent(a=(1, 1), c=(1, 1))))
    assert found["Agent prompt: b"] == bm.DOWN
    assert found["Agent prompt: c"] == bm.UP


# The committed baseline.


def test_the_committed_baseline_is_well_formed_and_deterministic() -> None:
    path = ROOT / "benchmarks" / "baseline.json"
    data = bm.load_baseline(path)
    assert data["passing_tests"] == sorted(set(data["passing_tests"]))
    assert data["tools"] == sorted(set(data["tools"]))
    assert path.read_text(encoding="utf-8") == bm.dump_baseline(data)
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == bm.SCHEMA_VERSION


def test_the_label_does_nothing_outside_a_pull_request(baseline: dict) -> None:
    assert bm.judge(baseline, lower(baseline), pr_base=None, is_approved=True).failed


def test_a_lowered_baseline_file_gets_its_own_message(baseline: dict) -> None:
    verdict = bm.judge(baseline, baseline, pr_base=lower(baseline))
    assert "baseline.json in this pull request is lower" in verdict.messages[0]
    assert "git checkout origin/main -- benchmarks/baseline.json" in verdict.messages[0]
