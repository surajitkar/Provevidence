"""Unit tests for optional auto-promotion helpers (no network)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("GITHUB_TOKEN", "test-token-for-import")
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import autoresearch as ar  # noqa: E402


SAMPLE_PROGRAM = """# Title

<!-- VARIANT: baseline -->

OLD BASELINE

<!-- VARIANT: compact_diff_v1 -->

WINNER TEXT
LINE2

<!-- VARIANT: other -->

OTHER
"""


def test_replace_baseline_section_in_program_success():
    out = ar.replace_baseline_section_in_program(SAMPLE_PROGRAM, "baseline", "compact_diff_v1")
    assert out is not None
    assert "WINNER TEXT" in out
    assert "LINE2" in out
    assert "OLD BASELINE" not in out
    assert "<!-- VARIANT: other -->" in out
    assert "<!-- VARIANT: baseline -->" in out


def test_replace_baseline_section_in_program_missing_winner():
    assert ar.replace_baseline_section_in_program(SAMPLE_PROGRAM, "baseline", "nope") is None


def test_replace_baseline_section_in_program_missing_baseline():
    text = "<!-- VARIANT: compact_diff_v1 -->\n\nX\n"
    assert ar.replace_baseline_section_in_program(text, "baseline", "compact_diff_v1") is None


def test_compute_promotion_fingerprint_stable():
    d = [{"variant_id": "a", "promote": True}]
    assert ar.compute_promotion_fingerprint(d) == ar.compute_promotion_fingerprint(d)


def test_maybe_auto_promote_pr_skips_without_flag():
    state = {}
    experiment = {"promotion": {"auto_open_pr": False}}
    decisions = [{"promote": True, "baseline_id": "baseline", "variant_id": "x"}]
    ar.maybe_auto_promote_pr(state, experiment, decisions)
    assert "last_auto_promotion_fingerprint" not in state


def test_maybe_auto_promote_pr_skips_duplicate_fingerprint():
    state = {"last_auto_promotion_fingerprint": ar.compute_promotion_fingerprint(
        [{"promote": True, "baseline_id": "b", "variant_id": "v"}]
    )}
    experiment = {"promotion": {"auto_open_pr": True}, "instruction_source": {"use_program": True}}
    decisions = [{"promote": True, "baseline_id": "b", "variant_id": "v"}]
    with mock.patch.object(ar, "open_promotion_pull_request") as m:
        ar.maybe_auto_promote_pr(state, experiment, decisions)
    m.assert_not_called()


def test_maybe_auto_promote_pr_calls_open_pr():
    state = {}
    experiment = {
        "name": "exp",
        "promotion": {"auto_open_pr": True},
        "instruction_source": {"use_program": True, "program_file": ".repo-autoresearch/program.md"},
    }
    decisions = [{"promote": True, "baseline_id": "baseline", "variant_id": "compact_diff_v1"}]
    with mock.patch.object(ar, "REPO", "o/r"):
        with mock.patch.object(ar, "open_promotion_pull_request", return_value="https://x/pr/1") as m:
            ar.maybe_auto_promote_pr(state, experiment, decisions)
    m.assert_called_once()
    assert state.get("last_auto_promotion", {}).get("pull_request_url") == "https://x/pr/1"


def test_merge_gist_state_preserves_fingerprint_from_latest():
    latest = {"pr_runs": {}, "promotion_decisions": [], "last_auto_promotion_fingerprint": "abc"}
    pending = {"pr_runs": {"1": {}}, "promotion_decisions": [{"evaluated_at": "t"}]}
    merged = ar._merge_gist_state(latest, pending)
    assert merged["last_auto_promotion_fingerprint"] == "abc"
    assert "1" in merged["pr_runs"]


def test_main_auto_promotion_only_skips_when_auto_open_pr_false(monkeypatch):
    monkeypatch.setenv("AUTORESEARCH_AUTO_PROMOTION_ONLY", "1")
    monkeypatch.setattr(ar, "PR_NUMBER", "1")
    monkeypatch.setattr(ar, "PR_ACTION", "closed")
    monkeypatch.setattr(ar, "PR_BASE_BRANCH", "main")
    with mock.patch.object(ar, "load_experiment", return_value={
        "promotion": {"auto_open_pr": False},
        "cohort": {"target_branches": ["main"]},
    }):
        with mock.patch.object(ar, "maybe_auto_promote_pr") as m:
            ar.main_auto_promotion_only()
    m.assert_not_called()


def test_main_auto_promotion_only_calls_maybe_when_enabled(monkeypatch):
    monkeypatch.setenv("AUTORESEARCH_AUTO_PROMOTION_ONLY", "1")
    monkeypatch.setattr(ar, "PR_NUMBER", "1")
    monkeypatch.setattr(ar, "PR_ACTION", "closed")
    monkeypatch.setattr(ar, "PR_BASE_BRANCH", "main")
    exp = {
        "promotion": {"auto_open_pr": True},
        "cohort": {"target_branches": ["main"]},
        "instruction_source": {"use_program": True},
    }
    decisions = [{"promote": True, "baseline_id": "baseline", "variant_id": "compact_diff_v1"}]
    with mock.patch.object(ar, "load_experiment", return_value=exp):
        with mock.patch.object(ar, "load_state", return_value={"pr_runs": {}, "promotion_decisions": []}):
            with mock.patch.object(ar, "evaluate_experiment", return_value=decisions):
                with mock.patch.object(ar, "maybe_auto_promote_pr") as m:
                    with mock.patch.object(ar, "save_state"):
                        ar.main_auto_promotion_only()
    m.assert_called_once()


def test_skip_auto_promotion_env(monkeypatch):
    monkeypatch.setenv("AUTORESEARCH_SKIP_AUTO_PROMOTION", "1")
    assert ar._skip_auto_promotion() is True
    monkeypatch.delenv("AUTORESEARCH_SKIP_AUTO_PROMOTION", raising=False)
    assert ar._skip_auto_promotion() is False
