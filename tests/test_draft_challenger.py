"""Tests for scripts/draft_challenger.py (no OpenAI calls)."""

import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_draft_challenger_writes_stub_without_api(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".repo-autoresearch").mkdir()
    (tmp_path / ".repo-autoresearch" / "reports").mkdir(parents=True)
    (tmp_path / ".repo-autoresearch" / "experiment.yaml").write_text(
        """
name: e
variants:
  - id: baseline
  - id: compact_diff_v1
""",
        encoding="utf-8",
    )
    (tmp_path / ".repo-autoresearch" / "program.md").write_text(
        "<!-- VARIANT: baseline -->\nB\n<!-- VARIANT: compact_diff_v1 -->\nC\n",
        encoding="utf-8",
    )

    import draft_challenger as dc

    monkeypatch.setattr(dc, "ROOT", tmp_path)
    monkeypatch.setattr(dc, "EXPERIMENT", tmp_path / ".repo-autoresearch" / "experiment.yaml")
    monkeypatch.setattr(dc, "SUMMARY", tmp_path / ".repo-autoresearch" / "reports" / "latest-summary.md")
    monkeypatch.setattr(dc, "PROGRAM", tmp_path / ".repo-autoresearch" / "program.md")
    out = tmp_path / "out.md"
    monkeypatch.setattr(sys, "argv", ["draft_challenger", "--output", str(out)])
    dc.main()
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert "Challenger draft (manual)" in body
