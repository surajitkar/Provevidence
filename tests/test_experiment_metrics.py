"""Unit tests for scripts/experiment_metrics.py (no network)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import experiment_metrics as em


def test_parse_guardrail_expr():
    assert em.parse_guardrail_expr("first_pass_ci_success >= baseline - 0.03") == (
        "first_pass_ci_success",
        ">=",
        -0.03,
    )
    assert em.parse_guardrail_expr("  revert_rate_7d  <=  baseline  +  0.01  ") == (
        "revert_rate_7d",
        "<=",
        0.01,
    )
    assert em.parse_guardrail_expr("not a guardrail") is None


def test_improvement_pct_directions():
    assert em.improvement_pct(10.0, 5.0, "lower_is_better") == 50.0
    assert em.improvement_pct(0.8, 0.9, "higher_is_better") == pytest.approx(12.5)


def test_evaluate_experiment_v2_promotion():
    state = {"pr_runs": {}}
    for i in range(20):
        state["pr_runs"][str(i)] = {
            "variant_id": "baseline",
            "review_round_trips": 4,
            "first_pass_ci_success": True,
            "revert_rate_7d": 0.0,
        }
    for i in range(20, 40):
        state["pr_runs"][str(i)] = {
            "variant_id": "compact_diff_v1",
            "review_round_trips": 1,
            "first_pass_ci_success": True,
            "revert_rate_7d": 0.0,
        }
    exp = {
        "variants": [{"id": "baseline"}, {"id": "compact_diff_v1"}],
        "metrics": {
            "review_round_trips": {"direction": "lower_is_better"},
            "first_pass_ci_success": {"direction": "higher_is_better"},
            "revert_rate_7d": {"direction": "lower_is_better", "source": "external"},
        },
        "evaluation": {
            "metric": "review_round_trips",
            "min_improvement_pct": 15,
            "min_prs": 20,
            "guardrails": [
                "first_pass_ci_success >= baseline - 0.03",
                "revert_rate_7d <= baseline + 0.01",
            ],
        },
    }
    decisions = em.evaluate_experiment_v2(state, exp)
    assert decisions is not None
    assert decisions[0]["promote"] is True
    assert decisions[0]["guardrail_ok"] is True


def test_report_metric_section_v2_only():
    exp = {
        "evaluation": {"metric": "review_round_trips"},
        "metrics": {"review_round_trips": {"direction": "lower_is_better"}},
    }
    d = {
        "baseline_stats": {"avg_review_round_trips": 2.0},
        "challenger_stats": {"avg_review_round_trips": 1.0},
    }
    lines = em.report_metric_section(d, exp)
    assert any("review_round_trips" in ln for ln in lines)


def test_report_metric_section_legacy_empty():
    exp = {"primary_metric": "review_round_trips"}
    d = {"baseline_stats": {}, "challenger_stats": {}}
    assert em.report_metric_section(d, exp) == []


def test_guardrail_fails_when_external_metric_missing_samples():
    state = {"pr_runs": {}}
    for i in range(20):
        state["pr_runs"][str(i)] = {
            "variant_id": "baseline",
            "review_round_trips": 3,
            "first_pass_ci_success": True,
        }
    for i in range(20, 40):
        state["pr_runs"][str(i)] = {
            "variant_id": "compact_diff_v1",
            "review_round_trips": 1,
            "first_pass_ci_success": True,
        }
    exp = {
        "variants": [{"id": "baseline"}, {"id": "compact_diff_v1"}],
        "metrics": {
            "review_round_trips": {"direction": "lower_is_better"},
            "first_pass_ci_success": {"direction": "higher_is_better"},
            "revert_rate_7d": {"direction": "lower_is_better", "source": "external"},
        },
        "evaluation": {
            "metric": "review_round_trips",
            "min_improvement_pct": 15,
            "min_prs": 20,
            "guardrails": [
                "revert_rate_7d <= baseline + 0.01",
            ],
        },
    }
    decisions = em.evaluate_experiment_v2(state, exp)
    assert decisions is not None
    assert decisions[0]["promote"] is False
    assert decisions[0]["guardrail_ok"] is False
    assert any("insufficient samples" in n for n in decisions[0]["guardrail_notes"])
