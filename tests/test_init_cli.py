"""Smoke tests for autoresearch-init."""

import sys
from pathlib import Path


def test_init_cli_copies_into_target(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)
    from agent_prompt_autoresearch.init_cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        ["autoresearch-init", "--target", str(tmp_path), "--force"],
    )
    main()
    assert (tmp_path / ".repo-autoresearch" / "experiment.yaml").is_file()
    assert (tmp_path / "scripts" / "autoresearch.py").is_file()
    assert (tmp_path / "scripts" / "get_variant.py").is_file()
    assert (tmp_path / "scripts" / "experiment_metrics.py").is_file()
    assert (tmp_path / "scripts" / "record_metric.py").is_file()
    assert (tmp_path / "scripts" / "validate_autoresearch.py").is_file()
