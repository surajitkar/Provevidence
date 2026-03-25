"""Tests for Gist state merge and 409 retry in scripts/autoresearch.py."""

import os
import sys
from pathlib import Path
from unittest import mock

os.environ.setdefault("GITHUB_TOKEN", "test-token-for-import")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import autoresearch as ar  # noqa: E402


def test_merge_gist_state_overlays_pr_runs():
    latest = {"pr_runs": {"1": {"x": 1}}, "promotion_decisions": []}
    pending = {"pr_runs": {"2": {"y": 2}}, "promotion_decisions": []}
    m = ar._merge_gist_state(latest, pending)
    assert m["pr_runs"]["1"]["x"] == 1
    assert m["pr_runs"]["2"]["y"] == 2


def test_merge_gist_state_appends_new_promotion_decisions():
    latest = {
        "pr_runs": {},
        "promotion_decisions": [{"evaluated_at": "a", "decisions": []}],
    }
    pending = {
        "pr_runs": {},
        "promotion_decisions": [{"evaluated_at": "b", "decisions": []}],
    }
    m = ar._merge_gist_state(latest, pending)
    assert len(m["promotion_decisions"]) == 2


def test_save_state_gist_retries_on_409(monkeypatch):
    monkeypatch.setattr(ar, "GIST_ID", "gist-id")
    monkeypatch.setattr(ar, "GIST_TOKEN", "gist-token")
    monkeypatch.setattr(ar.time, "sleep", lambda _s: None)

    gist_json = '{"pr_runs": {}, "promotion_decisions": []}'
    g_body = {"files": {ar.GIST_FILE: {"content": gist_json}}}

    def get_ok(*_a, **_k):
        m = mock.Mock()
        m.raise_for_status.return_value = None
        m.json.return_value = g_body
        return m

    patch_calls = []

    def patch_seq(*_a, **_k):
        patch_calls.append(1)
        r = mock.Mock()
        r.status_code = 409 if len(patch_calls) == 1 else 200
        r.raise_for_status = mock.Mock()
        return r

    monkeypatch.setattr(ar.requests, "get", get_ok)
    monkeypatch.setattr(ar.requests, "patch", patch_seq)

    ar._save_state_gist({"pr_runs": {"9": {}}, "promotion_decisions": []})

    assert len(patch_calls) == 2
