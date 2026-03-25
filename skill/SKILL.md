---
name: autoresearch-pr
description: >
  Use this skill whenever the user asks to raise a PR, open a pull request,
  implement a ticket, create a branch for any task, or write code that will
  result in a PR — regardless of where the ticket lives (Jira, Linear,
  GitHub Issues, verbal instruction, or no ticket at all). This skill MUST
  run before writing any code. It assigns the correct experiment variant via
  get_variant.py, loads the active instruction set, and ensures the PR body
  contains the autoresearch tracking tag so outcomes are attributed to the
  correct variant. Without this skill, multivariate PR experiments cannot
  measure which instructions produce better pull requests. Trigger on any
  of: "raise a PR", "open a pull request", "implement this ticket",
  "make a PR for", "can you PR this", "write the code for PROJ-X",
  "create a branch and PR", "implement LIN-55", or any request implying
  a PR will be opened.
compatibility: "Claude Code, GitHub Copilot — any agent that opens GitHub PRs"
---

# Autoresearch PR Skill

Wraps the standard PR workflow with variant assignment at the front
and a tracking tag at the end. **Canonical steps** live in **`AGENT.md`** at the repository root — follow that file to avoid drift; this skill expands with examples and edge cases.

## Workflow — follow these steps in order

### Step 1 — Extract the task reference

From the user's message, identify the best available identifier:

1. Ticket ref if provided: `PROJ-142`, `LIN-55`, `ENG-7`
2. GitHub issue number: `#89`
3. Short description if no ref: `"add discount code to checkout"`

### Step 2 — Run get_variant.py BEFORE writing any code

```bash
python scripts/get_variant.py --task "<ref-or-description>"
```

Examples:
```bash
python scripts/get_variant.py --task "PROJ-142"
python scripts/get_variant.py --task "LIN-55"
python scripts/get_variant.py --task "add discount code to checkout"
```

Read the full output. It prints:
- Which variant is assigned (`baseline`, `compact_diff_v1`, etc.)
- The full instructions to follow when writing code
- The exact tag to include in the PR body
- Confirms instructions written to `.repo-autoresearch/autoresearch_instructions.md`

If `get_variant.py` is not found, read `references/fallback.md`.

### Step 3 — Read and follow the instructions

Read `.repo-autoresearch/autoresearch_instructions.md` before writing any code (generated from `.repo-autoresearch/program.md` or variant files). Follow every rule in it — do not duplicate variant text here.

If instructions conflict with an explicit user request, follow
the user and note the deviation in the PR description.

### Step 4 — Write the code

Implement the task following the variant instructions exactly.

### Step 5 — Open the PR with the tracking tag

Include the tag printed by `get_variant.py` at the end of the PR body:

```
## What changed
<description>

## Why
<reason>

## How to verify
<steps or test names>

Closes #<issue-number-if-applicable>
[autoresearch:task=PROJ-142:variant=compact_diff_v1]
```

The tag is mandatory. Without it the PR cannot be attributed to
the correct variant and the experiment data is lost.

### Step 6 — Confirm to the user

After opening the PR tell the user:
- PR URL
- Which variant was active
- That the tracking tag is included

Example:
> PR opened: https://github.com/org/repo/pull/47
> Variant: `compact_diff_v1`
> Tracking tag included in PR body.

---

## Edge cases

| Situation | Action |
|-----------|--------|
| No experiment.yaml | Raise PR normally, no tag needed |
| get_variant.py not found | See `references/fallback.md` |
| User overrides instructions | Follow user, note override in PR description |
| No ticket ref at all | Use task description as hash key — still works |

---

## Files in this skill

- `SKILL.md` — this file
- `references/fallback.md` — manual variant assignment if script unavailable

Repo root (not under `skill/`): `scripts/get_variant.py`, `AGENT.md`.
