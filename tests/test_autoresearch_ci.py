"""Unit tests for CI check serialization in scripts/autoresearch.py."""

import os
import sys
from pathlib import Path

# autoresearch.py requires GITHUB_TOKEN at import time
os.environ.setdefault("GITHUB_TOKEN", "test-token-for-import")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import autoresearch as ar  # noqa: E402


def test_filter_check_runs_empty_config_keeps_all():
    runs = [{"name": "lint", "conclusion": "success"}, {"name": "pytest", "conclusion": "success"}]
    exp = {"ci_tracking": {"include_name_substrings": []}}
    assert ar.filter_check_runs_for_experiment(runs, exp) == runs


def test_filter_check_runs_missing_ci_tracking_keeps_all():
    runs = [{"name": "lint"}]
    assert ar.filter_check_runs_for_experiment(runs, {}) == runs


def test_filter_check_runs_filters_by_substring():
    runs = [
        {"name": "Autoresearch"},
        {"name": "pytest"},
        {"name": "lint"},
    ]
    exp = {"ci_tracking": {"include_name_substrings": ["pytest", "lint"]}}
    out = ar.filter_check_runs_for_experiment(runs, exp)
    assert [c["name"] for c in out] == ["pytest", "lint"]


def test_serialize_check_runs_for_gist_shape():
    runs = [
        {"name": "CI", "status": "completed", "conclusion": "success", "extra": "ignored"},
    ]
    assert ar.serialize_check_runs_for_gist(runs) == [
        {"name": "CI", "status": "completed", "conclusion": "success"},
    ]
