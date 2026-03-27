#!/usr/bin/env python3
"""
get_variant.py
--------------
Called by the agent (or human) BEFORE writing any code for a task.

Usage:
    python scripts/get_variant.py --task "PROJ-142"
    python scripts/get_variant.py --task "LIN-55"
    python scripts/get_variant.py --task "add discount code to checkout"
    python scripts/get_variant.py --task "PROJ-142" --quiet   # tag only

What it does:
    1. Hashes the task reference to deterministically pick a variant
    2. Prints the variant ID and full instructions for the agent to follow
    3. Writes the instructions to .repo-autoresearch/autoresearch_instructions.md
    4. Prints the tracking tag the agent must include in the PR body

Instructions load from instruction_source.program_file (variant sections) when
use_program is true; otherwise from each variant's instruction_pack file.

Same task ref always gets the same variant — no randomness.
Works offline. No GitHub token needed.
"""

import argparse
import hashlib
import re
import sys
import yaml
from pathlib import Path


def find_repo_root() -> Path:
    """Walk up from cwd looking for .repo-autoresearch/experiment.yaml."""
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / ".repo-autoresearch" / "experiment.yaml").is_file():
            return p
    return cwd


def slugify(text):
    """Normalise task text into a stable, hashable key."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\-]", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:80]


def assign_variant(task_key, experiment):
    variants = experiment.get("variants", [])
    if not variants:
        return None
    idx = int(hashlib.md5(task_key.encode()).hexdigest(), 16) % len(variants)
    return variants[idx]


def extract_variant_from_program(program_text: str, variant_id: str) -> str | None:
    """Return markdown body for one VARIANT section in program.md."""
    pattern = re.compile(
        rf"<!--\s*VARIANT:\s*{re.escape(variant_id)}\s*-->\s*(.*?)(?=<!--\s*VARIANT:|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(program_text)
    if not m:
        return None
    return m.group(1).strip()


def merge_instruction_source(experiment: dict) -> dict:
    """Merge optional `instructions:` over `instruction_source:` (same keys)."""
    base = dict(experiment.get("instruction_source") or {})
    overlay = experiment.get("instructions")
    if isinstance(overlay, dict):
        base.update(overlay)
    return base


def load_variant_instructions(variant: dict, experiment: dict, root: Path) -> str:
    src = merge_instruction_source(experiment)
    use_program = src.get("use_program", True)
    rel = src.get("program_file") or ".repo-autoresearch/program.md"
    program_path = root / rel
    if use_program and program_path.is_file():
        text = program_path.read_text(encoding="utf-8")
        block = extract_variant_from_program(text, variant["id"])
        if block:
            return block
    pack = variant.get("instruction_pack") or ""
    if pack:
        p = root / pack
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return ""


def main():
    parser = argparse.ArgumentParser(
        description="Assign an autoresearch variant before raising a PR."
    )
    parser.add_argument(
        "--task", required=True,
        help="Task identifier: Jira ref (PROJ-142), Linear ref (LIN-55), "
             "GitHub issue number, or a short description of the work."
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Only print the tracking tag (for scripted use)."
    )
    args = parser.parse_args()

    root = find_repo_root()
    experiment_file = root / ".repo-autoresearch" / "experiment.yaml"
    out_file = root / ".repo-autoresearch" / "autoresearch_instructions.md"

    if not experiment_file.is_file():
        if args.quiet:
            print("[autoresearch:unavailable]")
        else:
            print("No experiment.yaml found — autoresearch not set up in this repo.")
            print("Run from the repository root (or run: autoresearch-init).")
            print("Raise the PR normally without a tag.")
        sys.exit(0)

    with open(experiment_file, encoding="utf-8") as f:
        experiment = yaml.safe_load(f)

    task_key = slugify(args.task)
    variant = assign_variant(task_key, experiment)

    if not variant:
        print("No variants configured in experiment.yaml")
        sys.exit(1)

    instructions = load_variant_instructions(variant, experiment, root)
    tag = f"[autoresearch:task={args.task}:variant={variant['id']}]"

    out_file.write_text(
        f"# Autoresearch — active instructions\n"
        f"# Variant : {variant['id']}\n"
        f"# Task    : {args.task}\n\n"
        f"{instructions}\n\n"
        f"---\n"
        f"Include this tag in your PR body:\n{tag}\n",
        encoding="utf-8",
    )

    if args.quiet:
        print(tag)
        return

    width = 62
    print("=" * width)
    print("  Autoresearch — variant assigned")
    print("=" * width)
    print(f"  Task        : {args.task}")
    print(f"  Hash key    : {task_key}")
    print(f"  Variant     : {variant['id']}")
    print(f"  Experiment  : {experiment.get('name', 'unnamed')}")
    print()
    print(f"  Instructions written to: {out_file}")
    print()
    print("  REQUIRED — include this tag in your PR body:")
    print(f"  {tag}")
    print()
    print("-" * width)
    print("  Active instructions:")
    print("-" * width)
    for line in instructions.splitlines():
        print(f"  {line}")
    print("=" * width)


if __name__ == "__main__":
    main()
