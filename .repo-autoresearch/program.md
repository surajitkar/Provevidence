# Agent instruction program (all variants)

Edit variant sections below. When a task is assigned, `get_variant.py` extracts **one** section matching the variant id and writes `.repo-autoresearch/autoresearch_instructions.md`.

Promotion: after an experiment, copy the winning section over the baseline section (see `PROMOTION.md`).

<!-- VARIANT: baseline -->

# Baseline Instructions for AI-Generated Pull Requests

You are an AI coding agent contributing to this repository.
These are the current standard instructions — the control group.

## Pull Request Requirements

- Write a clear title describing the change (not the task).
- Include a description explaining what changed and why.
- Keep diffs focused on one concern per PR.
- Add or update tests for any logic you change.
- Do not include debug logs, commented-out code, or TODO comments
  unless they are tracked issues.

## Code Quality

- Follow existing patterns in the file you are modifying.
- Prefer small, reviewable changes over large rewrites.
- If you are unsure about a design decision, note it explicitly
  in the PR description.

## Evidence Required

Your PR will receive an autoresearch evidence block automatically.
Make sure CI passes before requesting review.

<!-- VARIANT: compact_diff_v1 -->

# Compact Diff Instructions — Challenger Variant v1

You are an AI coding agent contributing to this repository.
This variant tests whether stricter diff-size and description rules
reduce review round trips.

## Hard Rules (no exceptions)

1. **Diff limit: under 200 lines changed.** If your task requires more,
   split it into multiple PRs — one logical concern per PR.

2. **Title format:** `<type>(<scope>): <what changed>`
   Examples:
   - `fix(checkout): reject expired discount codes before payment`
   - `feat(auth): add OAuth token refresh on expiry`
   - `refactor(api): centralise error response format`

3. **Description must include all three:**
   - **What changed** — 1–2 sentences describing the change
   - **Why** — 1 sentence explaining the reason
   - **How to verify** — specific test names or exact steps a reviewer
     can follow to confirm it works

4. **Tests are mandatory.** If you have not modified or added a test
   file, do not open the PR. Add the tests first.

## Code Quality

- Match the style of the surrounding code exactly.
  No style migrations bundled into logic PRs.
- Remove all debug/temporary code before opening the PR.
- If the evidence block flags missing tests or a large diff,
  fix those issues before requesting review.

## Reviewer Expectation

A reviewer should be able to understand the full change in under
5 minutes. If that is not possible with your current diff, split it.
