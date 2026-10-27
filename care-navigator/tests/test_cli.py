"""Phase 7: cli.py runs the six demo cases."""
from __future__ import annotations

import pytest

import cli
from navigator.models import CareLevel, Outcome
from navigator.pipeline import Navigator


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    return cli.run_demo(Navigator(trace_dir=tmp_path_factory.mktemp("traces")))


def test_six_demo_cases_in_order():
    assert [c.key for c in cli.DEMO_CASES] == ["representative", "midnight", "chest", "vague", "gap", "bad_zip"]


def test_every_demo_case_meets_its_expectation(results):
    for case, result in results:
        assert case.check(result), (case.key, result.outcome, result.message)


def test_expected_outcomes(results):
    outcomes = {case.key: result for case, result in results}
    assert outcomes["representative"].recommendation.decision.level is CareLevel.URGENT_CARE
    assert outcomes["midnight"].recommendation.decision.level is CareLevel.TELEHEALTH
    assert outcomes["chest"].outcome is Outcome.EMERGENCY
    assert outcomes["vague"].outcome is Outcome.FOLLOW_UP
    assert outcomes["gap"].recommendation.alternatives and not outcomes["gap"].recommendation.options
    assert outcomes["bad_zip"].errors and outcomes["bad_zip"].recommendation.decision.level is CareLevel.URGENT_CARE


def test_format_shows_what_a_reviewer_needs(results):
    by_key = {case.key: (case, result) for case, result in results}
    rep = cli.format_result(*by_key["representative"])
    assert "RECOMMENDATION" in rep and "Urgent care" in rep and "$75" in rep and "This is not medical advice." in rep
    assert "Downtown QuickCare" in rep
    assert "Call 911" in cli.format_result(*by_key["chest"])
    assert "?" in cli.format_result(*by_key["vague"])
    gap = cli.format_result(*by_key["gap"])
    assert "No in-network urgent care" in gap and "1-800-555-0103" in gap and "NightOwl Virtual Care" in gap
    assert "99999" in cli.format_result(*by_key["bad_zip"])


def test_main_offline_prints_all_cases_and_passes(capsys):
    code = cli.main(["--offline", "--no-traces"])
    out = capsys.readouterr().out
    assert code == 0
    assert "mode: offline" in out and "synthetic" in out.lower()
    for case in cli.DEMO_CASES:
        assert case.title in out
    assert "6/6 demo cases as expected" in out
