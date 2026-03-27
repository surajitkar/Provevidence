#!/usr/bin/env python3
"""
validate_autoresearch.py — automated validation checklist for autoresearch setup.

Default mode runs local validations:
  - scaffold copy check via autoresearch-init
  - setup_test_repo local simulation smoke
  - v2 guardrail missing-sample behavior
  - record_metric CLI validations (success + expected failures)

Optional live mode:
  - run setup_test_repo against a real GitHub repo (--repo owner/name)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True, env=env)


def _ok(name: str, detail: str = "") -> dict:
    return {"name": name, "ok": True, "detail": detail}


def _fail(name: str, detail: str = "") -> dict:
    return {"name": name, "ok": False, "detail": detail}


def check_scaffold() -> dict:
    name = "scaffold scripts copied"
    with tempfile.TemporaryDirectory(prefix="autoresearch-validate-") as td:
        target = Path(td)
        cp = _run(
            [
                sys.executable,
                "-m",
                "agent_prompt_autoresearch.init_cli",
                "--target",
                str(target),
                "--force",
            ]
        )
        if cp.returncode != 0:
            return _fail(name, cp.stderr.strip() or cp.stdout.strip())
        required = [
            target / "scripts" / "autoresearch.py",
            target / "scripts" / "get_variant.py",
            target / "scripts" / "experiment_metrics.py",
            target / "scripts" / "record_metric.py",
            target / "scripts" / "validate_autoresearch.py",
        ]
        missing = [str(p) for p in required if not p.is_file()]
        if missing:
            return _fail(name, f"missing files: {', '.join(missing)}")
        return _ok(name)


def check_local_simulation() -> dict:
    name = "local simulation smoke"
    cp = _run([sys.executable, "scripts/setup_test_repo.py", "--simulate"])
    if cp.returncode != 0:
        return _fail(name, cp.stderr.strip() or cp.stdout[-400:])
    return _ok(name)


def check_guardrail_missing_samples() -> dict:
    name = "guardrail blocks on missing samples"
    from scripts.experiment_metrics import evaluate_experiment_v2

    state = {"pr_runs": {}}
    for i in range(20):
        state["pr_runs"][str(i)] = {
            "variant_id": "baseline",
            "review_round_trips": 3,
            "first_pass_ci_success": True,
        }
    for i in range(20, 40):
        state["pr_runs"][str(i)] = {
            "variant_id": "compact_diff_v1",
            "review_round_trips": 1,
            "first_pass_ci_success": True,
        }
    exp = {
        "variants": [{"id": "baseline"}, {"id": "compact_diff_v1"}],
        "metrics": {
            "review_round_trips": {"direction": "lower_is_better"},
            "first_pass_ci_success": {"direction": "higher_is_better"},
            "revert_rate_7d": {"direction": "lower_is_better", "source": "external"},
        },
        "evaluation": {
            "metric": "review_round_trips",
            "min_improvement_pct": 15,
            "min_prs": 20,
            "guardrails": ["revert_rate_7d <= baseline + 0.01"],
        },
    }
    decisions = evaluate_experiment_v2(state, exp)
    if not decisions:
        return _fail(name, "no decisions produced")
    d = decisions[0]
    if d.get("promote") is True:
        return _fail(name, "promotion unexpectedly allowed")
    if d.get("guardrail_ok") is True:
        return _fail(name, "guardrail unexpectedly passed")
    if not any("insufficient samples" in n for n in d.get("guardrail_notes", [])):
        return _fail(name, "insufficient-samples note missing")
    return _ok(name)


def check_record_metric_cli() -> dict:
    name = "record_metric validations"
    with tempfile.TemporaryDirectory(prefix="autoresearch-validate-") as td:
        repo = Path(td)
        cp_init = _run(
            [
                sys.executable,
                "-m",
                "agent_prompt_autoresearch.init_cli",
                "--target",
                str(repo),
                "--force",
            ]
        )
        if cp_init.returncode != 0:
            return _fail(name, cp_init.stderr.strip() or cp_init.stdout.strip())

        exp_file = repo / ".repo-autoresearch" / "experiment.yaml"
        exp = yaml.safe_load(exp_file.read_text(encoding="utf-8"))
        exp.setdefault("state", {})["backend"] = "local"
        exp_file.write_text(yaml.safe_dump(exp, sort_keys=False), encoding="utf-8")

        reports = repo / ".repo-autoresearch" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        state_file = reports / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "pr_runs": {"1": {"variant_id": "baseline", "review_round_trips": 1}},
                    "promotion_decisions": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        ok = _run(
            [
                sys.executable,
                "scripts/record_metric.py",
                "--pr",
                "1",
                "--metric",
                "revert_rate_7d",
                "--value",
                "0.02",
            ],
            cwd=repo,
        )
        if ok.returncode != 0:
            return _fail(name, f"expected success failed: {ok.stderr.strip() or ok.stdout.strip()}")

        bad_unknown = _run(
            [
                sys.executable,
                "scripts/record_metric.py",
                "--pr",
                "1",
                "--metric",
                "does_not_exist",
                "--value",
                "0.1",
            ],
            cwd=repo,
        )
        if bad_unknown.returncode == 0:
            return _fail(name, "unknown metric unexpectedly succeeded")

        bad_non_external = _run(
            [
                sys.executable,
                "scripts/record_metric.py",
                "--pr",
                "1",
                "--metric",
                "review_round_trips",
                "--value",
                "1",
            ],
            cwd=repo,
        )
        if bad_non_external.returncode == 0:
            return _fail(name, "non-external metric unexpectedly succeeded")
    return _ok(name)


def check_live_repo(repo: str) -> dict:
    name = "live GitHub setup smoke"
    if not os.environ.get("GITHUB_TOKEN"):
        return _fail(name, "GITHUB_TOKEN not set")
    cp = _run([sys.executable, "scripts/setup_test_repo.py", "--repo", repo])
    if cp.returncode != 0:
        return _fail(name, cp.stderr.strip() or cp.stdout[-400:])
    return _ok(name, f"repo={repo}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run automated validation checks for autoresearch functionality."
    )
    parser.add_argument(
        "--repo",
        help="Optional live GitHub repo owner/name for setup smoke check.",
    )
    args = parser.parse_args()

    checks = [
        check_scaffold,
        check_local_simulation,
        check_guardrail_missing_samples,
        check_record_metric_cli,
    ]
    results = [fn() for fn in checks]
    if args.repo:
        results.append(check_live_repo(args.repo))

    print("\nAutoresearch validation report")
    print("=" * 40)
    for r in results:
        icon = "PASS" if r["ok"] else "FAIL"
        detail = f" — {r['detail']}" if r.get("detail") else ""
        print(f"[{icon}] {r['name']}{detail}")

    failed = [r for r in results if not r["ok"]]
    print("=" * 40)
    print(f"Passed: {len(results) - len(failed)}/{len(results)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

