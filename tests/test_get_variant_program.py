"""Tests for program.md variant sections in scripts/get_variant.py."""

import os
import sys
from pathlib import Path

os.environ.setdefault("GITHUB_TOKEN", "test-token-for-import")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import get_variant as gv  # noqa: E402


def test_extract_variant_from_program_baseline():
    text = """
<!-- VARIANT: baseline -->
Hello BASE
<!-- VARIANT: compact_diff_v1 -->
Other
"""
    assert "Hello BASE" in gv.extract_variant_from_program(text, "baseline")


def test_extract_variant_from_program_challenger():
    text = """
<!-- VARIANT: baseline -->
A
<!-- VARIANT: compact_diff_v1 -->
CHALLENGER **text**
"""
    out = gv.extract_variant_from_program(text, "compact_diff_v1")
    assert "CHALLENGER" in out
    assert "baseline" not in out.lower() or "challenger" in out.lower()
