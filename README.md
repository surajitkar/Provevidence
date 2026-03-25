# Agent Prompt Autoresearch for Repos

Multivariate testing for AI-generated pull requests.
Discovers which agent instruction packs actually reduce review churn
for your specific codebase — instead of guessing.

---

## The idea in one paragraph

Your AI agent (Copilot, Claude Code, Cursor) writes code based on
instructions you give it. Different instructions produce different PR
quality. This system runs a controlled experiment: each task is assigned
one of your configured variants (deterministically from the task ref). After enough PRs,
it tells you which set produced fewer review round trips and better CI
pass rates — and recommends promoting the winner.

---

## Install in your own repository (pip)

```bash
pip install agent-prompt-autoresearch
cd /path/to/your/repo
autoresearch-init --with-workflow
```

Add GitHub Actions secrets `GIST_ID` and `GIST_TOKEN` (a PAT with `gist` scope), then commit `.repo-autoresearch/`, `scripts/`, and `.github/workflows/`. Agent workflow: see [AGENT.md](AGENT.md).

This project is **not** the same as [karpathy/autoresearch](https://github.com/karpathy/autoresearch) (autonomous LLM **training**). Here you test **PR instruction** variants and promotion.

**Developing this repository:** see [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

---

## Quickstart — local simulation (no GitHub needed)

```bash
git clone https://github.com/YOUR_USERNAME/agent-prompt-autoresearch
cd agent-prompt-autoresearch
pip install PyYAML requests
python scripts/setup_test_repo.py --simulate
```

---

## Quickstart — real GitHub repo

```bash
export GITHUB_TOKEN=ghp_your_token
python scripts/setup_test_repo.py --repo yourname/test-autoresearch
```

This creates the repo, pushes all files, and opens 3 test PRs.
The GitHub Action fires automatically and posts evidence blocks.

---

## How it works

```
Dev types: "implement PROJ-142"
              │
              ▼
Agent runs: python scripts/get_variant.py --task "PROJ-142"
              │
              ├─ hash("PROJ-142") % 2 = 1 → compact_diff_v1
              ├─ reads variant text from program.md (<!-- VARIANT: … -->) or fallback packs
              ├─ writes instructions to .repo-autoresearch/autoresearch_instructions.md
              └─ prints tag: [autoresearch:task=PROJ-142:variant=compact_diff_v1]
              │
              ▼
Between assignment and PR — per AGENT.md step 2:
  • Read .repo-autoresearch/autoresearch_instructions.md
    (the active slice from program.md or variants/ per experiment.yaml)
  • Implement the task following that file while coding
              │
              ▼
Agent opens PR with tag in body (AGENT.md step 3)
              │
              ▼
GitHub Action fires → reads tag → posts evidence block on PR
              │
              ▼
Reviewer approves / requests changes → recorded in experiment state (Gist or local file)
              │
              ▼
PR merges → same state; CI completion (check_suite) updates first-pass CI accurately
              │
              ▼
After 20 PRs per variant → evaluate experiment
              │
              ├─ compact_diff_v1 improved review rounds by 39% ✓
              └─ guardrails passed ✓
              │
              ▼
Report posted on PR + written to reports/latest-summary.md
→ "PROMOTE compact_diff_v1 — replace baseline" (see PROMOTION.md)
              │
              ├─ promotion.auto_open_pr: false (default)
              │    Same as before — evaluation only posts the report; you apply
              │    PROMOTION.md by hand.
              │
              └─ promotion.auto_open_pr: true
                   When an evaluation recommends PROMOTE for a challenger, the
                   workflow tries to open a PR that copies the winner’s program.md
                   section over the baseline section (same edit as the manual flow).
```

The gap between **variant assigned** and **PR opened** is intentional: the agent must **read** `autoresearch_instructions.md` and **follow it for the whole implementation**, as described in [AGENT.md](AGENT.md) steps 2–3.

---

## File structure

```
.github/
  workflows/
    autoresearch.yml          GitHub Action — PR events, reviews, check_suite (CI)

  copilot-instructions.md     Permanent agent instruction:
                              "run get_variant.py before writing code"

.repo-autoresearch/
  experiment.yaml             ← EDIT THIS to configure the experiment
  program.md                  Optional single file with <!-- VARIANT: id --> sections
                              (see instruction_source in experiment.yaml)
  variants/
    baseline.md               Fallback packs if program.md has no matching section
    compact-diff.md
  evidence-templates/
    standard.md               Per-variant evidence intent (referenced from experiment.yaml)
  reports/
    latest-summary.md         Latest experiment report (written when a run evaluates)
    state.json                Only used if Gist secrets are not configured (local fallback)

scripts/
  get_variant.py              Agent calls this before writing code (--quiet = tag only)
  autoresearch.py             GitHub Action engine — do not edit
  setup_test_repo.py          Local simulation + GitHub setup tool
  draft_challenger.py         Optional: draft a new challenger from learnings (see CLAUDE.md)

skill/
  SKILL.md                    Claude Code skill — install for automatic use
  scripts/get_variant.py      Bundled script (same as above)
  references/fallback.md      Manual variant assignment instructions
```

**Where state actually lives:** In production, PR runs and promotion history are stored in a **private GitHub Gist** (`GIST_ID` + `GIST_TOKEN`), not in the repo. The diagram above says “state.json” in spirit; locally or without Gist, data can live under `.repo-autoresearch/reports/state.json`.

---

## Additional capabilities (see `experiment.yaml` for knobs)

| Area | What it does |
|------|----------------|
| **`instruction_source`** | Use **`program.md`** with `<!-- VARIANT: id -->` sections (default in this repo), or turn off and rely on per-variant files under `variants/`. |
| **`primary_metric`** | Which numeric field on each PR run to optimize (default `review_round_trips`). The engine fills `review_round_trips` and `first_pass_ci_success`; using another name (e.g. `time_to_merge`) only works if your state records that field on each run. |
| **`compliance`** | Optional PR-body **heuristics** (length, checklist hints) surfaced in the evidence comment — not a guarantee. |
| **`ci_tracking`** | Optionally filter which GitHub **Check Runs** are stored on each PR (empty = record all). |
| **CI accuracy** | The workflow listens for **`check_suite: completed`** so **first-pass CI** reflects the real suite result, not the initial open. |
| **`evidence_template`** | Per-variant template path referenced when building the evidence block. |
| **`guardrails` / threshold** | `experiment.yaml` lists guardrail ideas; **promotion** in code uses **`promotion_threshold_pct`** on the primary metric plus a **CI pass-rate** check (challenger must not trail baseline by more than a few percentage points). |
| **`draft-challenger`** | Optional CLI (`draft-challenger`) to help draft a new challenger variant; see [CLAUDE.md](CLAUDE.md). |
| **Editor integration** | [`.github/copilot-instructions.md`](.github/copilot-instructions.md) and Cursor rules point agents at [AGENT.md](AGENT.md) so the workflow is not duplicated. |

---

## Configuration

Edit `.repo-autoresearch/experiment.yaml`:

```yaml
name: review-churn-reduction-v1

cohort:
  target_branches: [main]

primary_metric: review_round_trips
promotion_threshold_pct: 15

evaluation_window:
  type: pr_count
  value: 20          # PRs per variant before evaluating

# promotion:
#   auto_open_pr: false   # set true to open a baseline-update PR when evaluation recommends PROMOTE

variants:
  - id: baseline
    instruction_pack: .repo-autoresearch/variants/baseline.md

  - id: compact_diff_v1
    instruction_pack: .repo-autoresearch/variants/compact-diff.md
```

Add `promotion.auto_open_pr` in this file if you use automatic promotion PRs (default `false`). Behavior is summarized in the **How it works** diagram above; details are in `.repo-autoresearch/PROMOTION.md`.

---

## Installing the Claude Code skill

The `skill/` directory contains a Claude Code skill that makes the agent
call `get_variant.py` automatically whenever it raises a PR.

Install by copying `skill/` into your Claude Code skills directory,
or by importing `skill/SKILL.md` as a custom skill.

Once installed, the agent runs `get_variant.py` automatically —
no human needs to remember to ask.

---

## The experiment lifecycle

| Round | Who writes the variants | What the system does |
|-------|------------------------|---------------------|
| 1 | You write baseline + compact_diff_v1 | Runs the experiment, recommends winner |
| 2 | You promote winner, write v2 | Runs again with new challenger |
| 3+ | Optionally: LLM drafts challengers | System evaluates, you approve promotions |

---

## Key design decisions

**Why hash the task ref, not the PR number?**
The task ref exists before the agent writes code. The PR number only
exists after. Hashing the task ref ensures the agent receives the correct
instructions before starting — not after.

**Why is the variant tag in the PR body?**
The GitHub Action needs to know which variant was active for this PR.
The tag in the PR body is the explicit, auditable link between the
instructions the agent received and the outcomes recorded.

**Why no database for experiment state?**
Outcomes are stored in a **Gist** (or a local JSON file), not a database — minimal infrastructure. Variant **assignment** does not copy files: `get_variant.py` writes one small generated file (`autoresearch_instructions.md`). Optional **`promotion.auto_open_pr`** can open a PR that updates `program.md` after an evaluation; that is separate from assignment.

**Why deterministic hashing?**
Same task ref always gets same variant. The action can re-run on
the same PR 10 times (on retries, new commits, etc.) and always
reads the same variant from the tag. Fully reproducible.
