# Standard Evidence Template

This file documents the fields that appear in the autoresearch
evidence block posted on every eligible PR.

The evidence block is generated automatically by autoresearch.py
from GitHub API data — no manual input required.

## Fields included

| Field | Source | Purpose |
|-------|--------|---------|
| Variant | experiment.yaml + hash | Shows which instruction pack was active |
| Task | PR body tag | Traces PR back to the originating ticket |
| Intent | PR title | One-line summary of what the PR does |
| Files changed | GitHub files API | Diff size — lines added and deleted |
| Touched areas | Filename scan | Which files were modified |
| Risk indicators | Filename keyword scan | Flags payment, auth, config, DB paths |
| CI status | GitHub check runs API | Pass/fail on first full run |
| Test coverage | Filename scan | Whether test files were included |
| Missing evidence | Computed | Gaps that may cause review friction |

## Risk keyword patterns

The following filename patterns trigger risk flags:

- **money/payment** — payment, checkout, billing, pricing, stripe, invoice
- **auth/security** — auth, login, password, token, secret, oauth
- **config/env** — .env, config, settings, secrets
- **database** — migration, schema, sql, db, database
- **API contract** — openapi, swagger, routes, api/v

## Adding fields

To add a field, update the `generate_evidence_block()` function
in `scripts/autoresearch.py`. The template file documents intent
but is not parsed at runtime in the current MVP.
