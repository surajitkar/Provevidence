#!/usr/bin/env python3
"""
setup_test_repo.py
------------------
Two modes:

  --simulate   Run a local simulation with fake PR data.
               No GitHub token needed. Good for understanding
               the scoring logic before using a real repo.

  --repo X/Y   Create (or push into) a real GitHub repo.
               Pushes all project files and opens 3 test PRs
               so the Action fires automatically.

Usage:
    python scripts/setup_test_repo.py --simulate
    python scripts/setup_test_repo.py --repo yourname/test-autoresearch
"""

import argparse
import base64
import datetime
import hashlib
import os
import random
import sys
from pathlib import Path

try:
    import requests
    import yaml
except ImportError:
    print("Install dependencies first: pip install requests PyYAML")
    sys.exit(1)

ROOT            = Path(__file__).parent.parent
EXPERIMENT_FILE = ROOT / ".repo-autoresearch" / "experiment.yaml"
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API      = "https://api.github.com"
HEADERS         = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept":        "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------

def gh(method, path, **kwargs):
    r = getattr(requests, method)(f"{GITHUB_API}{path}",
                                  headers=HEADERS, timeout=15, **kwargs)
    if not r.ok:
        print(f"  GitHub {r.status_code}: {r.text[:200]}")
    return r

def repo_exists(repo):
    return gh("get", f"/repos/{repo}").status_code == 200

def create_repo(name):
    return gh("post", "/user/repos", json={
        "name": name, "description": "Agent Prompt Autoresearch test repo",
        "private": False, "auto_init": True,
    }).json()

def get_default_branch(repo):
    return gh("get", f"/repos/{repo}").json().get("default_branch", "main")

def get_ref_sha(repo, branch):
    return gh("get", f"/repos/{repo}/git/ref/heads/{branch}").json()["object"]["sha"]

def create_blob(repo, content):
    r = gh("post", f"/repos/{repo}/git/blobs", json={
        "content": base64.b64encode(content.encode()).decode(),
        "encoding": "base64",
    })
    return r.json()["sha"]

def create_tree(repo, base_tree, files):
    items = [{"path": p, "mode": "100644", "type": "blob",
              "sha": create_blob(repo, c)} for p, c in files.items()]
    return gh("post", f"/repos/{repo}/git/trees",
              json={"base_tree": base_tree, "tree": items}).json()["sha"]

def create_commit(repo, parent, tree, message):
    return gh("post", f"/repos/{repo}/git/commits",
              json={"message": message, "tree": tree,
                    "parents": [parent]}).json()["sha"]

def update_ref(repo, branch, sha):
    gh("patch", f"/repos/{repo}/git/refs/heads/{branch}", json={"sha": sha})

def create_branch(repo, branch, from_sha):
    gh("post", f"/repos/{repo}/git/refs",
       json={"ref": f"refs/heads/{branch}", "sha": from_sha})

def create_pr(repo, title, head, base, body):
    return gh("post", f"/repos/{repo}/pulls",
              json={"title": title, "head": head,
                    "base": base, "body": body}).json()

# ---------------------------------------------------------------------------
# Collect all project files to push
# ---------------------------------------------------------------------------

def collect_project_files(repo):
    files = {}
    skip = {"__pycache__", ".pyc", "state.json"}
    for path in ROOT.rglob("*"):
        if path.is_file() and not any(s in str(path) for s in skip):
            rel = str(path.relative_to(ROOT))
            try:
                files[rel] = path.read_text()
            except Exception:
                pass
    # Add a README pointing to the repo
    files["README.md"] = generate_readme(repo)
    return files

def generate_readme(repo):
    return f"""# Agent Prompt Autoresearch

Multivariate testing for AI-generated pull requests.

## How it works

1. Agent calls `python scripts/get_variant.py --task "TICKET-123"` before writing code
2. Agent follows the returned instructions and includes the tracking tag in the PR body
3. GitHub Action scores CI result, review rounds, and merge outcomes
4. After {20} PRs per variant, the system evaluates and recommends a winner

## Quick start

```bash
# Local simulation (no token needed)
python scripts/setup_test_repo.py --simulate

# Real repo
export GITHUB_TOKEN=ghp_your_token
python scripts/setup_test_repo.py --repo yourname/test-autoresearch
```

## Files

```
.github/
  workflows/autoresearch.yml     GitHub Action trigger
  copilot-instructions.md        Permanent agent instructions

.repo-autoresearch/
  experiment.yaml                Edit this to configure the experiment
  variants/
    baseline.md                  Control group instructions
    compact-diff.md              Challenger instructions
  evidence-templates/
    standard.md                  Evidence block field reference
  reports/
    state.json                   Accumulated PR run data (auto-generated)
    latest-summary.md            Latest experiment report (auto-generated)

scripts/
  get_variant.py                 Agent calls this before writing code
  autoresearch.py                GitHub Action engine
  setup_test_repo.py             This file

skill/
  SKILL.md                       Claude Code skill for automatic integration
  scripts/get_variant.py         Bundled script for the skill
  references/fallback.md         Manual variant assignment instructions
```

https://github.com/{repo}
"""

# ---------------------------------------------------------------------------
# Local simulation
# ---------------------------------------------------------------------------

def simulate_locally():
    print("\n" + "=" * 60)
    print("LOCAL SIMULATION MODE")
    print("=" * 60)

    if not EXPERIMENT_FILE.exists():
        print(f"Expected: {EXPERIMENT_FILE}")
        print("Run from the project root directory.")
        return

    with open(EXPERIMENT_FILE) as f:
        experiment = yaml.safe_load(f)

    variants  = experiment.get("variants", [])
    min_prs   = experiment.get("evaluation_window", {}).get("value", 20)
    threshold = experiment.get("promotion_threshold_pct", 15)

    print(f"\nExperiment  : {experiment['name']}")
    print(f"Variants    : {[v['id'] for v in variants]}")
    print(f"Window      : {min_prs} PRs per variant")
    print(f"Threshold   : {threshold}%")

    random.seed(42)
    pr_runs = {}

    for i in range(1, min_prs * len(variants) + 10):
        pr_num     = str(i)
        idx        = int(hashlib.md5(pr_num.encode()).hexdigest(), 16) % len(variants)
        variant_id = variants[idx]["id"]

        if variant_id == "baseline":
            rounds = random.choices([0, 1, 2, 3], weights=[20, 40, 30, 10])[0]
            ci_ok  = random.random() > 0.18
        else:
            rounds = random.choices([0, 1, 2, 3], weights=[35, 45, 15, 5])[0]
            ci_ok  = random.random() > 0.15

        pr_runs[pr_num] = {
            "variant_id":            variant_id,
            "review_round_trips":    rounds,
            "first_pass_ci_success": ci_ok,
        }

    by_variant = {}
    for run in pr_runs.values():
        by_variant.setdefault(run["variant_id"], []).append(run)

    print("\n--- Simulated PR distribution ---")
    for vid, runs in by_variant.items():
        rounds   = [r["review_round_trips"] for r in runs]
        ci_rates = [r["first_pass_ci_success"] for r in runs]
        print(f"  {vid:20s} {len(runs):3d} PRs | "
              f"avg rounds: {sum(rounds)/len(rounds):.2f} | "
              f"CI pass: {sum(ci_rates)/len(ci_rates):.1%}")

    baseline_id   = variants[0]["id"]
    baseline_runs = by_variant.get(baseline_id, [])
    base_rounds   = [r["review_round_trips"] for r in baseline_runs]
    base_ci       = [r["first_pass_ci_success"] for r in baseline_runs]
    base_avg      = sum(base_rounds) / len(base_rounds)
    base_ci_rate  = sum(base_ci) / len(base_ci)

    print("\n--- Experiment Evaluation ---")
    for v in variants[1:]:
        vid  = v["id"]
        runs = by_variant.get(vid, [])
        if not runs:
            continue
        rounds   = [r["review_round_trips"] for r in runs]
        ci_rates = [r["first_pass_ci_success"] for r in runs]
        avg      = sum(rounds) / len(rounds)
        ci_rate  = sum(ci_rates) / len(ci_rates)
        improv   = (base_avg - avg) / base_avg * 100 if base_avg > 0 else 0
        ci_drop  = base_ci_rate - ci_rate
        guardrail_ok = ci_drop <= 0.03
        promote  = improv >= threshold and guardrail_ok

        icon = "PROMOTE" if promote else "REJECT"
        print(f"\n  {icon}: {vid}")
        print(f"    Review round improvement : {improv:+.1f}%  (need ≥{threshold}%)")
        print(f"    CI pass rate change      : {ci_drop:+.1%}  (limit: +3%)")
        print(f"    Guardrails               : {'PASS' if guardrail_ok else 'FAIL'}")
        if promote:
            print(f"    → Replace '{baseline_id}' with '{vid}' as new baseline")
        else:
            print(f"    → Keep '{baseline_id}'")

    print("\n✅ Simulation complete.")
    print("\nTo test with a real repo:")
    print("    export GITHUB_TOKEN=ghp_your_token")
    print("    python scripts/setup_test_repo.py --repo yourname/test-autoresearch")

# ---------------------------------------------------------------------------
# Real GitHub repo setup
# ---------------------------------------------------------------------------

def setup_real_repo(repo):
    repo_name = repo.split("/")[-1]
    print(f"\nSetting up: https://github.com/{repo}")

    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN not set")
        print("  export GITHUB_TOKEN=ghp_your_token")
        sys.exit(1)

    if not repo_exists(repo):
        print(f"  Creating repo '{repo_name}'...")
        create_repo(repo_name)
        print(f"  Created: https://github.com/{repo}")
    else:
        print(f"  Repo exists: https://github.com/{repo}")

    branch   = get_default_branch(repo)
    base_sha = get_ref_sha(repo, branch)

    print(f"  Pushing project files to {branch}...")
    files    = collect_project_files(repo)
    tree_sha = create_tree(repo, base_sha, files)
    commit   = create_commit(repo, base_sha, tree_sha,
                             "chore: add agent-prompt-autoresearch")
    update_ref(repo, branch, commit)
    print(f"  Pushed {len(files)} files")

    base_sha = get_ref_sha(repo, branch)
    print("\n  Creating test PRs...")

    test_prs = [
        {
            "branch":  "ai/fix-checkout-validation",
            "title":   "fix(checkout): reject expired discount codes [autoresearch:task=PROJ-100:variant=baseline]",
            "file":    "src/checkout/validation.py",
            "content": "def validate_discount(code, expiry):\n    if expiry < today():\n        raise ValueError('Expired')\n    return True\n",
            "body":    "Fixes discount code validation.\n\n[autoresearch:task=PROJ-100:variant=baseline]",
        },
        {
            "branch":  "ai/add-auth-token-refresh",
            "title":   "feat(auth): add OAuth token refresh",
            "file":    "src/auth/tokens.py",
            "content": "def refresh_token(token):\n    if token.is_expired():\n        return generate_new_token()\n    return token\n",
            "body":    "Adds token refresh on expiry.\n\n[autoresearch:task=PROJ-101:variant=compact_diff_v1]",
        },
        {
            "branch":  "ai/add-health-endpoint",
            "title":   "feat(api): add /health endpoint",
            "file":    "src/api/health.py",
            "content": "from flask import Flask\napp = Flask(__name__)\n\n@app.route('/health')\ndef health():\n    return {'status': 'ok'}\n",
            "body":    "Adds health check endpoint.\n\n[autoresearch:task=PROJ-102:variant=baseline]",
        },
    ]

    for pr_data in test_prs:
        try:
            create_branch(repo, pr_data["branch"], base_sha)
            new_tree   = create_tree(repo, base_sha, {pr_data["file"]: pr_data["content"]})
            new_commit = create_commit(repo, base_sha, new_tree,
                                       f"add {pr_data['file']}")
            update_ref(repo, pr_data["branch"], new_commit)
            pr = create_pr(repo, pr_data["title"],
                           pr_data["branch"], branch, pr_data["body"])
            pr_num = pr.get("number")
            if pr_num:
                print(f"  ✅ PR #{pr_num}: {pr_data['title'][:60]}")
                print(f"     {pr.get('html_url', '')}")
        except Exception as e:
            print(f"  ⚠️  Skipped {pr_data['branch']}: {e}")

    print(f"\n✅ Setup complete!")
    print(f"\nNext steps:")
    print(f"  1. Visit https://github.com/{repo}/actions to see the workflow")
    print(f"  2. Evidence blocks will appear on the test PRs above")
    print(f"  3. Edit .repo-autoresearch/experiment.yaml to customise")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo",     help="GitHub repo: owner/name")
    parser.add_argument("--simulate", action="store_true",
                        help="Run local simulation (no token needed)")
    args = parser.parse_args()

    if args.simulate or not args.repo:
        simulate_locally()
    else:
        setup_real_repo(args.repo)

if __name__ == "__main__":
    main()
