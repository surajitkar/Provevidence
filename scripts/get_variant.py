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

Same task ref always gets the same variant — no randomness.
Works offline. No GitHub token needed.
"""

import argparse
import hashlib
import re
import sys
import yaml
from pathlib import Path

ROOT            = Path(__file__).parent.parent
EXPERIMENT_FILE = ROOT / ".repo-autoresearch" / "experiment.yaml"
OUT_FILE        = ROOT / ".repo-autoresearch" / "autoresearch_instructions.md"

# ---------------------------------------------------------------------------

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

def load_instructions(instruction_pack_ref):
    path = ROOT / instruction_pack_ref
    return path.read_text() if path.exists() else ""

# ---------------------------------------------------------------------------

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

    if not EXPERIMENT_FILE.exists():
        if args.quiet:
            print("[autoresearch:unavailable]")
        else:
            print("No experiment.yaml found — autoresearch not set up in this repo.")
            print("Raise the PR normally without a tag.")
        sys.exit(0)

    with open(EXPERIMENT_FILE) as f:
        experiment = yaml.safe_load(f)

    task_key = slugify(args.task)
    variant  = assign_variant(task_key, experiment)

    if not variant:
        print("No variants configured in experiment.yaml")
        sys.exit(1)

    instructions = load_instructions(variant.get("instruction_pack", ""))
    tag = f"[autoresearch:task={args.task}:variant={variant['id']}]"

    # Write instructions to temp file for the agent to read
    OUT_FILE.write_text(
        f"# Autoresearch — active instructions\n"
        f"# Variant : {variant['id']}\n"
        f"# Task    : {args.task}\n\n"
        f"{instructions}\n\n"
        f"---\n"
        f"Include this tag in your PR body:\n{tag}\n"
    )

    if args.quiet:
        print(tag)
        return

    # Human/agent-readable output
    width = 62
    print("=" * width)
    print(f"  Autoresearch — variant assigned")
    print("=" * width)
    print(f"  Task        : {args.task}")
    print(f"  Hash key    : {task_key}")
    print(f"  Variant     : {variant['id']}")
    print(f"  Experiment  : {experiment.get('name', 'unnamed')}")
    print()
    print(f"  Instructions written to: {OUT_FILE}")
    print()
    print(f"  REQUIRED — include this tag in your PR body:")
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
