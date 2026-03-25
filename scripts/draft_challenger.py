#!/usr/bin/env python3
"""
Draft a new challenger variant using experiment learnings (M4).

- Without OPENAI_API_KEY: writes a markdown scaffold you edit by hand.
- With OPENAI_API_KEY: calls the OpenAI Chat Completions API to propose text.

Human must review and merge; nothing is auto-applied to program.md.
"""

import argparse
import os
import sys
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT = ROOT / ".repo-autoresearch" / "experiment.yaml"
SUMMARY = ROOT / ".repo-autoresearch" / "reports" / "latest-summary.md"
PROGRAM = ROOT / ".repo-autoresearch" / "program.md"


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def load_variant_bodies(experiment: dict) -> dict[str, str]:
    from scripts.get_variant import extract_variant_from_program, load_variant_instructions

    out = {}
    program_txt = load_text(PROGRAM)
    for v in experiment.get("variants", []):
        vid = v["id"]
        if program_txt:
            block = extract_variant_from_program(program_txt, vid)
            if block:
                out[vid] = block
                continue
        out[vid] = load_variant_instructions(v, experiment, ROOT)
    return out


def draft_with_openai(prompt: str, model: str) -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return ""
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You write concise agent instruction markdown for software PRs. Output markdown only, no preamble.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
        },
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft a new challenger variant from experiment learnings.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".repo-autoresearch" / "variants" / "challenger-draft.md",
        help="Where to write the draft markdown.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_DRAFT_MODEL", "gpt-4o-mini"),
        help="OpenAI model when API key is set.",
    )
    args = parser.parse_args()

    if not EXPERIMENT.is_file():
        print("No .repo-autoresearch/experiment.yaml — run autoresearch-init first.", file=sys.stderr)
        sys.exit(1)

    with open(EXPERIMENT, encoding="utf-8") as f:
        experiment = yaml.safe_load(f)

    summary = load_text(SUMMARY)
    bodies = load_variant_bodies(experiment)
    baseline_id = experiment["variants"][0]["id"] if experiment.get("variants") else "baseline"
    baseline_txt = bodies.get(baseline_id, "")
    challenger_ids = [v["id"] for v in experiment.get("variants", [])[1:]]
    challenger_txt = "\n\n---\n\n".join(
        f"### {cid}\n{bodies.get(cid, '')}" for cid in challenger_ids
    )

    prompt = f"""Experiment summary (from latest evaluation if present):

{summary[:12000]}

---

Current baseline instructions ({baseline_id}):

{baseline_txt[:8000]}

---

Previous challenger instruction sets:

{challenger_txt[:8000]}

---

Draft a NEW challenger variant (markdown) that could beat the baseline on review efficiency and CI pass rate.
Include clear hard rules, PR title/description expectations, and test requirements.
Do not repeat the baseline verbatim; propose concrete improvements based on the summary.
"""

    text = draft_with_openai(prompt, args.model)
    if not text:
        text = f"""# Challenger draft (manual)

Fill in after reading `{SUMMARY.relative_to(ROOT) if SUMMARY.is_file() else 'latest-summary.md'}`.

## Goals
- (what to improve vs baseline)

## Hard rules
- 

## PR requirements
- 

Then add a `<!-- VARIANT: your_id -->` section to `program.md` or register a new variant in experiment.yaml.
"""

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"Wrote {args.output}")
    if not os.environ.get("OPENAI_API_KEY"):
        print("Tip: set OPENAI_API_KEY for an LLM-generated draft next time.")


if __name__ == "__main__":
    main()
