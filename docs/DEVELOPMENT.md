# Development notes

This document is for **people changing this repository** (the `agent-prompt-autoresearch` package and scripts). End users integrating autoresearch into their own repos should start with [README.md](../README.md) and [AGENT.md](../AGENT.md).

## Setup

```bash
pip install -r requirements-dev.txt
pytest
```

Editable install (CLI entry points):

```bash
pip install -e .
```

See also [CLAUDE.md](../CLAUDE.md) for a short command and architecture overview aimed at coding agents.

## Layout

| Path | Role |
|------|------|
| `scripts/` | `get_variant.py`, `autoresearch.py` (Actions engine), `setup_test_repo.py`, `draft_challenger.py` |
| `tests/` | `pytest` suite |
| `agent_prompt_autoresearch/` | Package + `autoresearch-init` bundled templates |
| `.repo-autoresearch/` | Example experiment config used by this repo’s own workflows |

## `experiment.yaml` vs evaluation code

`evaluate_experiment()` in `scripts/autoresearch.py` reads:

- **`variants`**, **`evaluation_window`**, **`primary_metric`**, **`promotion_threshold_pct`**
- **`baseline` PR count** before evaluating challengers

Promotion decisions use:

- Average **primary metric** per variant (field name on each `pr_run` record)
- **Improvement** vs baseline vs `promotion_threshold_pct`
- A **CI pass-rate guardrail**: challenger must not trail baseline by more than **3 percentage points** (hardcoded in code)

The **`guardrails:`** list in `experiment.yaml` documents intent and future direction; it is **not** parsed as a full expression engine today. If you change promotion rules, update `scripts/autoresearch.py` and keep comments in `experiment.yaml` in sync.

**`primary_metric`:** The engine populates `review_round_trips` and `first_pass_ci_success` on PR runs. Using another field name (e.g. `time_to_merge`) only works if something **writes** that field on each run.

## GitHub Actions

- **Secrets:** `GIST_ID` and `GIST_TOKEN` (PAT with `gist` scope) for state in a private Gist.
- **Permissions:** The default workflow job uses **`contents: read`** (evidence, Gist state, comments). A **second job** runs only on **`pull_request` `closed`**, after the main job, with **`contents: write`** so optional auto-promotion can create a branch and open a PR. That way elevated permission is not granted for every event type.
- **Triggers:** `pull_request`, `pull_request_review`, `check_suite` (CI completion updates first-pass CI accurately).

## State storage

- **Default:** JSON in a **GitHub Gist** (no experiment state in the repo).
- **Fallback:** `.repo-autoresearch/reports/state.json` when Gist is not configured (e.g. local runs).

## Optional tools

- **`draft-challenger`** — see `scripts/draft_challenger.py` and [CLAUDE.md](../CLAUDE.md).

## Documentation map

| Doc | Audience |
|-----|----------|
| [README.md](../README.md) | Users of the framework |
| [AGENT.md](../AGENT.md) | Coding agents (PR workflow) |
| [CLAUDE.md](../CLAUDE.md) | Maintainers + AI assistants in this repo |
| [.repo-autoresearch/PROMOTION.md](../.repo-autoresearch/PROMOTION.md) | Operators promoting a winning variant |
| This file | Contributors and internals |
