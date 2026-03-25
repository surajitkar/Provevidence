"""Unit tests for core logic in scripts/autoresearch.py (no network)."""

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import autoresearch as ar  # noqa: E402


def test_parse_autoresearch_tag_valid():
    body = "desc\n\n[autoresearch:task=PROJ-142:variant=compact_diff_v1]\n"
    task, vid = ar.parse_autoresearch_tag(body)
    assert task == "PROJ-142"
    assert vid == "compact_diff_v1"


def test_parse_autoresearch_tag_empty():
    assert ar.parse_autoresearch_tag("") == (None, None)
    assert ar.parse_autoresearch_tag(None) == (None, None)


def test_parse_autoresearch_tag_not_found():
    assert ar.parse_autoresearch_tag("no tag here") == (None, None)


def test_get_variant_by_id():
    exp = {"variants": [{"id": "baseline"}, {"id": "x"}]}
    assert ar.get_variant_by_id("baseline", exp)["id"] == "baseline"
    assert ar.get_variant_by_id("missing", exp) is None


def test_compute_risk_indicators_payment():
    files = [{"filename": "src/checkout/payment.py"}]
    r = ar.compute_risk_indicators(files)
    assert "money/payment" in r


def test_compute_risk_indicators_default_when_none():
    files = [{"filename": "README.md"}]
    assert ar.compute_risk_indicators(files) == ["no high-risk areas detected"]


def test_score_ci_status_empty():
    s, ok = ar.score_ci_status([])
    assert "no ci checks found" in s.lower()
    assert ok is False


def test_score_ci_status_in_progress():
    runs = [{"name": "t", "conclusion": None}]
    s, ok = ar.score_ci_status(runs)
    assert "progress" in s.lower()
    assert ok is False


def test_score_ci_status_failed():
    runs = [{"name": "lint", "conclusion": "failure"}]
    s, ok = ar.score_ci_status(runs)
    assert "FAILING" in s
    assert ok is False


def test_score_ci_status_all_pass():
    runs = [
        {"name": "a", "conclusion": "success"},
        {"name": "b", "conclusion": "success"},
    ]
    s, ok = ar.score_ci_status(runs)
    assert "all 2 checks passed" in s
    assert ok is True


def test_score_compliance_heuristics_disabled():
    summary, rows = ar.score_compliance_heuristics("hello", {})
    assert summary == ""
    assert rows == []


def test_score_compliance_heuristics_passes(monkeypatch):
    exp = {"compliance": {"pr_body_min_length": 10}}
    body = "x" * 50 + "\n[autoresearch:task=t:variant=v]\npytest verify"
    summary, rows = ar.score_compliance_heuristics(body, exp)
    assert "3/3" in summary
    assert all(ok for _, ok, _ in rows)


def test_generate_evidence_block_contains_variant(monkeypatch):
    monkeypatch.setattr(ar, "REPO", "o/r")
    pr = {"title": "feat: x", "body": "y" * 60}
    files = [{"filename": "tests/test_x.py", "additions": 10, "deletions": 2}]
    checks = [{"name": "ci", "conclusion": "success"}]
    variant = {"id": "baseline"}
    exp = {}
    out = ar.generate_evidence_block(pr, files, checks, variant, "instr", "T-1", exp)
    assert "AUTORESEARCH_EVIDENCE_BLOCK" in out
    assert "baseline" in out
    assert "test_x.py" in out


def test_generate_evidence_block_includes_compliance(monkeypatch):
    monkeypatch.setattr(ar, "REPO", "o/r")
    pr = {"title": "t", "body": "x" * 60 + "[autoresearch:task=a:variant=b] verify pytest"}
    files = [{"filename": "a.py", "additions": 1, "deletions": 0}]
    exp = {"compliance": {"pr_body_min_length": 10}}
    out = ar.generate_evidence_block(pr, files, [], {"id": "v"}, "", "task", exp)
    assert "Instruction compliance" in out


def test_record_outcome_creates_run():
    state = {"pr_runs": {}}
    ar.record_outcome(state, 5, "opened", {"variant_id": "baseline", "task_ref": "x"})
    assert "5" in state["pr_runs"]
    assert state["pr_runs"]["5"]["variant_id"] == "baseline"
    assert len(state["pr_runs"]["5"]["events"]) == 1


def test_record_outcome_increments_review_rounds():
    state = {"pr_runs": {}}
    ar.record_outcome(state, 1, "opened", {"variant_id": "b"})
    ar.record_outcome(state, 1, "review_submitted", {"review_state": "changes_requested"})
    assert state["pr_runs"]["1"]["review_round_trips"] == 1


def test_evaluate_experiment_insufficient_baseline():
    state = {"pr_runs": {"1": {"variant_id": "baseline", "review_round_trips": 1}}}
    exp = {
        "variants": [{"id": "baseline"}, {"id": "c"}],
        "evaluation_window": {"value": 20},
        "primary_metric": "review_round_trips",
    }
    assert ar.evaluate_experiment(state, exp) is None


def test_evaluate_experiment_promotion_decision():
    """Challenger improves review_round_trips enough and passes CI guardrail."""
    state = {"pr_runs": {}}
    for i in range(20):
        state["pr_runs"][str(i)] = {
            "variant_id": "baseline",
            "review_round_trips": 4,
            "first_pass_ci_success": True,
        }
    for i in range(20, 40):
        state["pr_runs"][str(i)] = {
            "variant_id": "compact_diff_v1",
            "review_round_trips": 1,
            "first_pass_ci_success": True,
        }
    exp = {
        "name": "e",
        "variants": [{"id": "baseline"}, {"id": "compact_diff_v1"}],
        "evaluation_window": {"value": 20},
        "primary_metric": "review_round_trips",
        "promotion_threshold_pct": 15,
    }
    decisions = ar.evaluate_experiment(state, exp)
    assert decisions is not None
    assert decisions[0]["variant_id"] == "compact_diff_v1"
    assert decisions[0]["promote"] is True


def test_evaluate_experiment_single_variant_returns_none():
    exp = {"variants": [{"id": "only"}]}
    assert ar.evaluate_experiment({"pr_runs": {}}, exp) is None


def test_generate_report_smoke():
    decisions = [
        {
            "variant_id": "c",
            "baseline_id": "b",
            "improvement_pct": 20.0,
            "promote": True,
            "guardrail_ok": True,
            "guardrail_notes": [],
            "baseline_stats": {"count": 20, "avg_metric": 2.0, "ci_pass_rate": 0.9},
            "challenger_stats": {"count": 20, "avg_metric": 1.0, "ci_pass_rate": 0.88},
        }
    ]
    text = ar.generate_report(decisions, {"name": "n", "promotion_threshold_pct": 15})
    assert "Autoresearch Experiment Report" in text
    assert "PROMOTE" in text


def test_is_ai_pr_detects_tag(monkeypatch):
    monkeypatch.setattr(ar, "PR_AUTHOR", "human")
    monkeypatch.setattr(ar, "PR_TITLE", "fix")
    monkeypatch.setattr(ar, "PR_BODY", "[autoresearch:task=x:variant=baseline]")
    assert ar.is_ai_pr() is True


def test_is_ai_pr_detects_bot_author(monkeypatch):
    monkeypatch.setattr(ar, "PR_AUTHOR", "copilot")
    monkeypatch.setattr(ar, "PR_TITLE", "x")
    monkeypatch.setattr(ar, "PR_BODY", "")
    assert ar.is_ai_pr() is True


def test_resolve_variant_uses_tag(monkeypatch):
    monkeypatch.setattr(ar, "PR_NUMBER", "99")
    monkeypatch.setattr(ar, "PR_AUTHOR", "human")
    monkeypatch.setattr(ar, "PR_TITLE", "t")
    exp = {"variants": [{"id": "baseline"}, {"id": "compact_diff_v1"}]}
    body = "[autoresearch:task=z:variant=compact_diff_v1]"
    v, task = ar.resolve_variant(body, exp)
    assert v["id"] == "compact_diff_v1"
    assert task == "z"
