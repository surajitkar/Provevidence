# Agent Prompt Autoresearch for Repos

Multivariate testing for AI-generated pull requests.
Discovers which agent instruction packs actually reduce review churn
for your specific codebase — instead of guessing.

---

## The idea in one paragraph

Your AI agent (Copilot, Claude Code, Cursor) writes code based on
instructions you give it. Different instructions produce different PR
quality. This system runs a controlled experiment: half your AI-generated
PRs use instruction set A, half use instruction set B. After enough PRs,
it tells you which set produced fewer review round trips and better CI
pass rates — and recommends promoting the winner.

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
              ├─ reads .repo-autoresearch/variants/compact-diff.md
              ├─ writes instructions to .repo-autoresearch/autoresearch_instructions.md
              └─ prints tag: [autoresearch:task=PROJ-142:variant=compact_diff_v1]
              │
              ▼
Agent writes code following compact_diff_v1 instructions
              │
              ▼
Agent opens PR with tag in body
              │
              ▼
GitHub Action fires → reads tag → posts evidence block on PR
              │
              ▼
Reviewer approves / requests changes → recorded in state.json
              │
              ▼
PR merges → recorded in state.json
              │
              ▼
After 20 PRs per variant → evaluate experiment
              │
              ├─ compact_diff_v1 improved review rounds by 39% ✓
              └─ guardrails passed ✓
              │
              ▼
Report posted on PR + written to reports/latest-summary.md
→ "PROMOTE compact_diff_v1 — replace baseline.md"
```

---

## File structure

```
.github/
  workflows/
    autoresearch.yml          GitHub Action — fires on PR events

  copilot-instructions.md     Permanent agent instruction:
                              "run get_variant.py before writing code"

.repo-autoresearch/
  experiment.yaml             ← EDIT THIS to configure the experiment
  variants/
    baseline.md               Control group instructions (you write this)
    compact-diff.md           Challenger instructions (you write this)
  evidence-templates/
    standard.md               Documents the evidence block fields
  reports/
    state.json                All PR runs + promotion decisions (auto)
    latest-summary.md         Latest experiment report (auto)

scripts/
  get_variant.py              Agent calls this before writing code
  autoresearch.py             GitHub Action engine — do not edit
  setup_test_repo.py          Local simulation + GitHub setup tool

skill/
  SKILL.md                    Claude Code skill — install for automatic use
  scripts/get_variant.py      Bundled script (same as above)
  references/fallback.md      Manual variant assignment instructions
```

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

variants:
  - id: baseline
    instruction_pack: .repo-autoresearch/variants/baseline.md

  - id: compact_diff_v1
    instruction_pack: .repo-autoresearch/variants/compact-diff.md
```

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

**Why no file copying or database?**
Instructions travel with the issue/task thread as a comment. No shared
state, no race conditions, no extra infrastructure. Each task carries
its own variant in its own context.

**Why deterministic hashing?**
Same task ref always gets same variant. The action can re-run on
the same PR 10 times (on retries, new commits, etc.) and always
reads the same variant from the tag. Fully reproducible.
