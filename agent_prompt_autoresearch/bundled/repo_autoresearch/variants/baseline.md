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
