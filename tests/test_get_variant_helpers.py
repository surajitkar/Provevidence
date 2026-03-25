"""Tests for scripts/get_variant.py helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import get_variant as gv  # noqa: E402


def test_slugify_normalizes():
    assert gv.slugify("PROJ-142") == "proj-142"
    assert gv.slugify("  Hello World!  ") == "hello-world"


def test_assign_variant_stable_per_task():
    exp = {
        "variants": [
            {"id": "baseline"},
            {"id": "compact_diff_v1"},
        ]
    }
    a = gv.assign_variant(gv.slugify("same-task"), exp)
    b = gv.assign_variant(gv.slugify("same-task"), exp)
    assert a["id"] == b["id"]


def test_assign_variant_different_tasks_can_differ():
    exp = {
        "variants": [
            {"id": "baseline"},
            {"id": "compact_diff_v1"},
        ]
    }
    # Many tasks will land on both variants over time; just ensure function returns one of them
    v = gv.assign_variant(gv.slugify("task-a"), exp)
    assert v["id"] in ("baseline", "compact_diff_v1")


def test_extract_variant_from_program_unknown_id():
    text = "<!-- VARIANT: baseline -->\nX"
    assert gv.extract_variant_from_program(text, "nope") is None


def test_load_variant_instructions_prefers_program(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".repo-autoresearch").mkdir()
    program = tmp_path / ".repo-autoresearch" / "program.md"
    program.write_text(
        "<!-- VARIANT: v1 -->\nONLY_V1\n<!-- VARIANT: v2 -->\nONLY_V2\n",
        encoding="utf-8",
    )
    exp = {
        "instruction_source": {"use_program": True, "program_file": ".repo-autoresearch/program.md"},
        "variants": [{"id": "v1", "instruction_pack": ""}],
    }
    text = gv.load_variant_instructions({"id": "v1"}, exp, tmp_path)
    assert "ONLY_V1" in text
    assert "ONLY_V2" not in text
