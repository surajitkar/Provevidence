#!/usr/bin/env python3
"""
record_metric.py — set an external metric on a PR run in autoresearch state.

Use when a metric is declared in experiment.yaml with source: external (e.g. revert_rate_7d).
Requires the PR to exist in state (autoresearch has recorded an open/close cycle).

Usage:
  python scripts/record_metric.py --pr 42 --metric revert_rate_7d --value 0.02
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.autoresearch import load_experiment, load_state, save_state  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record an external numeric metric on a PR in autoresearch state."
    )
    parser.add_argument("--pr", type=int, required=True, help="Pull request number")
    parser.add_argument("--metric", required=True, help="Field name (must match YAML metrics key)")
    parser.add_argument("--value", type=float, required=True)
    args = parser.parse_args()

    experiment = load_experiment()
    state = load_state(experiment)
    metrics = experiment.get("metrics") or {}
    mdef = metrics.get(args.metric)
    if not mdef:
        print(
            f"Unknown metric '{args.metric}'. Define it under metrics: in experiment.yaml first.",
            file=sys.stderr,
        )
        sys.exit(1)
    if mdef.get("source") != "external":
        print(
            f"Metric '{args.metric}' is not source: external and should not be set via record-metric.",
            file=sys.stderr,
        )
        sys.exit(1)

    key = str(args.pr)
    if key not in state.get("pr_runs", {}):
        print(f"PR #{args.pr} not in state — autoresearch has no run for it yet.", file=sys.stderr)
        sys.exit(1)

    state["pr_runs"][key][args.metric] = args.value
    save_state(state, experiment)
    print(f"Recorded {args.metric}={args.value} for PR #{args.pr}")


if __name__ == "__main__":
    main()
