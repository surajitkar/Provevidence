# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Agent PR workflow (same as Copilot & Cursor)

For the step-by-step flow, **[AGENT.md](AGENT.md)** is the short source of truth. In summary:

1. From the **repo root**, run `python scripts/get_variant.py --task "<ticket-or-description>"` **before** writing code.
2. Follow what it prints; it writes **`.repo-autoresearch/autoresearch_instructions.md`** (active slice from **`.repo-autoresearch/program.md`** variant sections, or fallback files under `variants/`).
3. Put the printed **`[autoresearch:task=…:variant=…]`** tag at the end of the **PR body** (required for experiment tracking).

Copilot and Cursor load [`.github/copilot-instructions.md`](.github/copilot-instructions.md) and [`.cursor/rules/autoresearch.mdc`](.cursor/rules/autoresearch.mdc); those files **only reference** `AGENT.md` so the workflow is not duplicated.

---

## What This Project Does

**Agent Prompt Autoresearch** is a multivariate testing framework for AI-generated pull requests. It determines which agent instruction packs reduce review churn on a specific codebase through controlled A/B experiments — baseline vs challenger variants, then measures review round trips and CI outcomes.

This repo is **not** [karpathy/autoresearch](https://github.com/karpathy/autoresearch) (LLM training). Same name pattern; different purpose (PR instruction experiments).

## Commands

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Assign a variant before writing code (required first step for PR work)
python scripts/get_variant.py --task "PROJ-142"
python scripts/get_variant.py --task "PROJ-142" --quiet   # tag only

# Scaffold autoresearch into another repo (after pip install)
# autoresearch-init --with-workflow

# Optional: draft a new challenger from evaluation summary (OPENAI_API_KEY optional)
# draft-challenger

# Local simulation (no GitHub token needed)
python scripts/setup_test_repo.py --simulate
python scripts/validate_autoresearch.py

# Real GitHub repo setup
export GITHUB_TOKEN=ghp_your_token
python scripts/setup_test_repo.py --repo yourname/test-autoresearch
```

CLI entry points (after `pip install -e .`): `get-variant`, `autoresearch`, `record-metric`, `validate-autoresearch`, `setup-test-repo`, `autoresearch-init`, `draft-challenger`.

## Architecture

### Three-Script Core

**`scripts/get_variant.py`** — Called by AI agents *before* writing code. Hashes the task reference, selects a variant deterministically, writes instructions to **`.repo-autoresearch/autoresearch_instructions.md`**, and emits a tracking tag. The same task always gets the same variant.

**`scripts/autoresearch.py`** — GitHub Actions engine triggered on PR open/update/close, review events, and `check_suite` completion. Reads the autoresearch tag from the PR body, posts an evidence block, and records outcomes (typically in a **GitHub Gist** when configured, else local state file).

**`scripts/setup_test_repo.py`** — Two modes: `--simulate` creates fake PR data locally; `--repo X/Y` creates a real GitHub repo and opens test PRs.

### Experiment Configuration

**`.repo-autoresearch/experiment.yaml`** — Configure variants, metrics, `instruction_source` (default: sections in **`program.md`**), optional `compliance` and `ci_tracking`.

Variant text: **`program.md`** (`<!-- VARIANT: id -->` sections) with **`variants/*.md`** as fallback when a section is missing. Promotion workflow: **`PROMOTION.md`**.

### State & Reporting

Outcomes are stored in configured backend (Gist JSON or local `state.json`). **`latest-summary.md`** is generated when evaluations run.

### Skill Integration

**`skill/SKILL.md`** defines a Claude Code skill (`autoresearch-pr`). Fallback when the script is unavailable: **`skill/references/fallback.md`**.

### GitHub Actions Workflow

**`.github/workflows/autoresearch.yml`** — triggers on PR events, reviews, and `check_suite: completed`. Requires secrets **`GIST_ID`** and **`GIST_TOKEN`** for Gist-backed state.

The workflow uses **two jobs**: the main job has **`contents: read`** (evidence, state, comments). If **`promotion.auto_open_pr`** is enabled, a **second job** runs only when a PR **closes** (after the first job) with **`contents: write`** so it can open an optional promotion PR—narrower permission than granting write on every event.

### Key Design Constraints

- **Hash the task ref, not PR number** — task ref exists before the agent writes code.
- **Variant tag in PR body** — explicit link for attribution.
- **Instructions path** — `.repo-autoresearch/autoresearch_instructions.md` at repo root.
- **Python ≥3.10** (see `.python-version`).
