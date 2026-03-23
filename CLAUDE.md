# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

**Agent Prompt Autoresearch** is a multivariate testing framework for AI-generated pull requests. It determines which agent instruction packs reduce review churn on a specific codebase through controlled A/B experiments — half of AI-generated PRs use instruction set A (baseline), half use instruction set B (challenger), then it measures which produced fewer review round trips and better CI pass rates.

## Commands

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Assign a variant before writing code (agents must call this first)
python scripts/get_variant.py --task "PROJ-142"
python scripts/get_variant.py --task "PROJ-142" --quiet   # tag only

# Local simulation (no GitHub token needed)
python scripts/setup_test_repo.py --simulate

# Real GitHub repo setup
export GITHUB_TOKEN=ghp_your_token
python scripts/setup_test_repo.py --repo yourname/test-autoresearch
```

CLI entry points (after `pip install -e .`): `get-variant`, `autoresearch`, `setup-test-repo`.

## Architecture

### Three-Script Core

**`scripts/get_variant.py`** — Called by AI agents *before* writing code. MD5-hashes the task reference, selects a variant via `hash % variant_count`, writes instructions to `/tmp/autoresearch_instructions.md`, and emits a tracking tag: `[autoresearch:task=PROJ-142:variant=compact_diff_v1]`. The same task always gets the same variant (deterministic, no randomness).

**`scripts/autoresearch.py`** — GitHub Actions engine triggered on PR open/update/close and review events. It reads the autoresearch tag from the PR body to identify the variant, posts an auto-generated evidence block as a PR comment, and records outcomes in `.repo-autoresearch/reports/state.json`. When a PR closes and enough data is collected (default: 20 PRs per variant), it runs the experiment evaluation and posts a promotion recommendation.

**`scripts/setup_test_repo.py`** — Two modes: `--simulate` creates fake PR data locally; `--repo X/Y` creates a real GitHub repo and opens test PRs.

### Experiment Configuration

`.repo-autoresearch/experiment.yaml` — **Edit this to configure experiments.** Key fields:
- `variants` — array of instruction packs (first = baseline/control)
- `primary_metric` — what to optimize (default: `review_round_trips`)
- `evaluation_window.value` — PRs per variant before evaluating (default: 20)
- `promotion_threshold_pct` — improvement % needed to promote (default: 15%)

Variant instruction files live in `.repo-autoresearch/variants/` (e.g., `baseline.md`, `compact-diff.md`).

### State & Reporting

`.repo-autoresearch/reports/state.json` tracks every PR run: variant, task ref, review round trips, first-pass CI success, merge time. `latest-summary.md` is auto-generated after each evaluation.

### Skill Integration

`skill/SKILL.md` defines a Claude Code skill (`autoresearch-pr`) that agents invoke for any PR task. The 6-step workflow: extract task ref → run `get_variant.py` → read instructions → write code following them → open PR with tracking tag → confirm to user. Fallback instructions for when the script is unavailable: `skill/references/fallback.md`.

### GitHub Actions Workflow

`.github/workflows/autoresearch.yml` — triggers on `pull_request` (opened, synchronize, reopened, closed) and `pull_request_review`. Requires `pull-requests: write`, `contents: read`, `issues: write` permissions. Calls `scripts/autoresearch.py` with PR metadata from GitHub context env vars.

`.github/copilot-instructions.md` — permanent instructions directing AI agents to run `get_variant.py` before writing any code.

### Key Design Constraints

- **Hash the task ref, not PR number** — task ref exists before the agent writes code; PR number only exists after.
- **Variant tag in PR body** — explicit, auditable link; no shared state, no race conditions.
- **Instructions output path** — written to `.repo-autoresearch/autoresearch_instructions.md` (relative to project root, works cross-platform).
- **Python ≥3.10 required** (`.python-version` specifies 3.11).
- **No test files exist yet** — `pytest` is configured in `pyproject.toml` but the test suite is not yet written.
