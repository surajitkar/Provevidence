#!/usr/bin/env python3
"""
autoresearch.py — Agent Prompt Autoresearch Engine
---------------------------------------------------
Triggered by GitHub Actions on every PR event.

Responsibilities:
  1. PR opened/updated  → read autoresearch tag from PR body
                        → look up which variant was assigned to this task
                        → call GitHub API to get diff, files, CI status
                        → generate evidence block, post as PR comment
                        → record pr_run in state.json

  2. Review submitted   → record review_round_trips in state.json

  3. PR closed          → record merge/close in state.json
                        → if enough PRs collected → evaluate experiment
                        → post experiment report as PR comment
                        → optionally open a promotion PR (experiment.yaml promotion.auto_open_pr)
                        → write latest-summary.md

The variant is assigned BEFORE the PR is created, by the agent calling
scripts/get_variant.py. The tag [autoresearch:task=X:variant=Y] in the
PR body links the PR back to its variant assignment.
"""

import os
import re
import sys
import json
import time
import base64
import hashlib
import datetime
import urllib.parse
import requests
import yaml
from pathlib import Path

from scripts.experiment_metrics import (
    evaluate_experiment,
    primary_metric_label,
    promotion_threshold_pct,
    report_metric_section,
)
from scripts.get_variant import (
    extract_variant_from_program,
    load_variant_instructions,
    merge_instruction_source,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT             = Path(__file__).parent.parent
AUTORESEARCH_DIR = ROOT / ".repo-autoresearch"
EXPERIMENT_FILE  = AUTORESEARCH_DIR / "experiment.yaml"
STATE_FILE       = AUTORESEARCH_DIR / "reports" / "state.json"
SUMMARY_FILE     = AUTORESEARCH_DIR / "reports" / "latest-summary.md"

# ---------------------------------------------------------------------------
# Environment variables (injected by GitHub Actions)
# ---------------------------------------------------------------------------

GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
REPO           = os.environ.get("REPO_FULL_NAME", "")
PR_NUMBER      = os.environ.get("PR_NUMBER", "")
PR_ACTION      = os.environ.get("PR_ACTION", "")
PR_AUTHOR      = os.environ.get("PR_AUTHOR", "")
PR_TITLE       = os.environ.get("PR_TITLE", "")
PR_BASE_BRANCH = os.environ.get("PR_BASE_BRANCH", "main")
PR_MERGED      = os.environ.get("PR_MERGED", "false").lower() == "true"
PR_BODY        = os.environ.get("PR_BODY", "")
REVIEW_STATE   = os.environ.get("REVIEW_STATE", "")

# CI context — populated on check_suite:completed events
CHECK_SHA        = os.environ.get("CHECK_SHA", "")
CHECK_CONCLUSION = os.environ.get("CHECK_CONCLUSION", "")
CHECK_PR_NUMBERS = os.environ.get("CHECK_PR_NUMBERS", "[]")


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def _skip_auto_promotion() -> bool:
    """Main CI job sets this so contents:write is only used by the promotion job."""
    return _env_truthy("AUTORESEARCH_SKIP_AUTO_PROMOTION")


def _auto_promotion_only() -> bool:
    """Dedicated job: contents:write; runs main_auto_promotion_only()."""
    return _env_truthy("AUTORESEARCH_AUTO_PROMOTION_ONLY")

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
GITHUB_API = "https://api.github.com"

# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def gh_get(path):
    r = requests.get(f"{GITHUB_API}{path}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

def gh_post(path, body):
    r = requests.post(f"{GITHUB_API}{path}", headers=HEADERS, json=body, timeout=15)
    r.raise_for_status()
    return r.json()

def gh_patch(path, body):
    r = requests.patch(f"{GITHUB_API}{path}", headers=HEADERS, json=body, timeout=15)
    r.raise_for_status()
    return r.json()

def gh_put(path, body):
    r = requests.put(f"{GITHUB_API}{path}", headers=HEADERS, json=body, timeout=15)
    r.raise_for_status()
    return r.json()

def post_pr_comment(body):
    gh_post(f"/repos/{REPO}/issues/{PR_NUMBER}/comments", {"body": body})
    print(f"  Posted comment on PR #{PR_NUMBER}")

def update_or_create_pr_comment(marker, body):
    """Update existing bot comment if found, otherwise create new."""
    comments = gh_get(f"/repos/{REPO}/issues/{PR_NUMBER}/comments")
    for c in comments:
        if marker in c.get("body", "") and "bot" in c["user"]["login"].lower():
            gh_patch(f"/repos/{REPO}/issues/comments/{c['id']}", {"body": body})
            print(f"  Updated PR comment {c['id']}")
            return
    post_pr_comment(body)

def get_pr_details():
    return gh_get(f"/repos/{REPO}/pulls/{PR_NUMBER}")

def get_pr_files():
    return gh_get(f"/repos/{REPO}/pulls/{PR_NUMBER}/files")

def get_check_runs_for_sha(sha):
    """Return check runs for a commit SHA (same jobs GitHub shows on the PR checks UI)."""
    if not sha or not REPO:
        return []
    data = gh_get(f"/repos/{REPO}/commits/{sha}/check-runs?per_page=100")
    return data.get("check_runs", [])


def get_check_runs():
    pr = get_pr_details()
    sha = pr.get("head", {}).get("sha", "")
    return get_check_runs_for_sha(sha)


def filter_check_runs_for_experiment(check_runs, experiment):
    """
    Apply optional ci_tracking.include_name_substrings from experiment.yaml.
    Empty or missing list means: keep all check runs (match configured repo CI).
    """
    ci_tracking = experiment.get("ci_tracking") or {}
    substrings = ci_tracking.get("include_name_substrings") or []
    if not substrings:
        return list(check_runs)
    lowered = [s.lower() for s in substrings]
    return [
        c for c in check_runs
        if any(s in (c.get("name") or "").lower() for s in lowered)
    ]


def serialize_check_runs_for_gist(check_runs):
    """Stable, JSON-friendly rows for Gist pr_runs.ci_checks."""
    return [
        {
            "name": c.get("name"),
            "status": c.get("status"),
            "conclusion": c.get("conclusion"),
        }
        for c in check_runs
    ]

# ---------------------------------------------------------------------------
# State management — GitHub Gist backend
#
# state.json lives in a private GitHub Gist, not in the repo.
# This keeps git history clean — no bot commits on every PR.
#
# Required secrets (add to repo → Settings → Secrets → Actions):
#   GIST_ID    — the Gist ID (run scripts/create_gist.py once to get it)
#   GIST_TOKEN — a PAT with the "gist" scope
#
# When GIST_ID is not set (e.g. local --simulate), falls back to local file.
# ---------------------------------------------------------------------------

GIST_ID    = os.environ.get("GIST_ID", "")
GIST_TOKEN = os.environ.get("GIST_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
GIST_FILE  = "autoresearch-state.json"

GIST_HEADERS = {
    "Authorization": f"Bearer {GIST_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

def _gist_available():
    return bool(GIST_ID and GIST_TOKEN)


def _use_gist_backend(experiment):
    """Respect experiment.yaml state.backend: auto | gist | local."""
    if experiment is None:
        return _gist_available()
    backend = (experiment.get("state") or {}).get("backend", "auto")
    if backend == "local":
        return False
    if backend == "gist":
        return bool(GIST_ID and GIST_TOKEN)
    return _gist_available()


def load_state(experiment=None):
    if _use_gist_backend(experiment):
        state = _load_state_gist()
    else:
        state = _load_state_file()
    state.setdefault("pr_runs", {})
    state.setdefault("promotion_decisions", [])
    return state


def save_state(state, experiment=None):
    if _use_gist_backend(experiment):
        _save_state_gist(state)
    else:
        _save_state_file(state)

def _load_state_gist():
    try:
        r = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers=GIST_HEADERS, timeout=15
        )
        r.raise_for_status()
        content = r.json()["files"][GIST_FILE]["content"]
        state = json.loads(content)
        print(f"  State loaded from Gist {GIST_ID[:8]}… ({len(state.get('pr_runs', {}))} PR runs)")
        return state
    except Exception as e:
        print(f"  Could not load Gist state: {e} — starting fresh")
        return {"pr_runs": {}, "promotion_decisions": []}

def _merge_gist_state(latest, pending):
    """Merge pending in-memory state with latest Gist JSON (concurrent-run safe)."""
    merged_runs = {**latest.get("pr_runs", {}), **pending.get("pr_runs", {})}
    existing_ts = {d.get("evaluated_at") for d in latest.get("promotion_decisions", [])}
    merged_decisions = list(latest.get("promotion_decisions", []))
    for d in pending.get("promotion_decisions", []):
        if d.get("evaluated_at") not in existing_ts:
            merged_decisions.append(d)
    # Preserve keys from latest when pending omits them (e.g. last_auto_promotion_fingerprint).
    merged = {**latest, **pending}
    merged["pr_runs"] = merged_runs
    merged["promotion_decisions"] = merged_decisions
    return merged


def _save_state_gist(state):
    """
    Re-read Gist immediately before writing to merge any changes
    made by a concurrent Action run since we loaded state at job start.

    Retries on HTTP 409 Conflict when two Actions patch the Gist concurrently.
    """
    max_attempts = 5
    base_delay_s = 0.5
    pending = state

    for attempt in range(max_attempts):
        merged = pending
        try:
            r = requests.get(
                f"https://api.github.com/gists/{GIST_ID}",
                headers=GIST_HEADERS, timeout=15
            )
            r.raise_for_status()
            latest = json.loads(r.json()["files"][GIST_FILE]["content"])
            merged = _merge_gist_state(latest, pending)
        except Exception as e:
            print(f"  Warning: could not re-read Gist before save: {e}")

        r = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers=GIST_HEADERS,
            json={"files": {GIST_FILE: {"content": json.dumps(merged, indent=2, default=str)}}},
            timeout=15
        )
        if r.status_code == 409:
            if attempt < max_attempts - 1:
                delay = base_delay_s * (2**attempt)
                print(f"  Gist save conflict (409), retrying in {delay:.1f}s ({attempt + 1}/{max_attempts})…")
                time.sleep(delay)
                continue
        r.raise_for_status()
        print(f"  State saved to Gist {GIST_ID[:8]}… ({len(merged.get('pr_runs', {}))} PR runs)")
        return

def _load_state_file():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"pr_runs": {}, "promotion_decisions": []}

def _save_state_file(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)
    print(f"  State saved → {STATE_FILE}")

# ---------------------------------------------------------------------------
# Experiment config
# ---------------------------------------------------------------------------

def load_experiment():
    if not EXPERIMENT_FILE.exists():
        print("No experiment.yaml — skipping.")
        sys.exit(0)
    with open(EXPERIMENT_FILE) as f:
        return yaml.safe_load(f)

def get_variant_by_id(variant_id, experiment):
    for v in experiment.get("variants", []):
        if v["id"] == variant_id:
            return v
    return None

# ---------------------------------------------------------------------------
# Variant resolution
# ---------------------------------------------------------------------------

def parse_autoresearch_tag(pr_body):
    if not pr_body:
        return None, None
    m = re.search(r"\[autoresearch:task=([^:]+):variant=([^\]]+)\]", pr_body)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None

def resolve_variant(pr_body, experiment):
    task_ref, variant_id = parse_autoresearch_tag(pr_body)
    if variant_id:
        variant = get_variant_by_id(variant_id, experiment)
        if variant:
            print(f"  Tag found → task={task_ref} variant={variant_id}")
            return variant, task_ref
        print(f"  Warning: variant '{variant_id}' not in experiment.yaml — falling back")
    if not is_ai_pr():
        return None, None
    variants = experiment.get("variants", [])
    if not variants:
        return None, None
    idx = int(hashlib.md5(str(PR_NUMBER).encode()).hexdigest(), 16) % len(variants)
    print(f"  No tag — fallback hash variant: {variants[idx]['id']}")
    return variants[idx], None

# ---------------------------------------------------------------------------
# AI-generated PR detection
# ---------------------------------------------------------------------------

AI_AGENT_LOGINS = {
    "copilot", "github-copilot", "copilot[bot]",
    "cursor", "cursor-ai",
    "claude", "claude-code", "anthropic-claude",
    "devin-ai", "devin",
}

def is_ai_pr():
    author = PR_AUTHOR.lower()
    if any(a in author for a in AI_AGENT_LOGINS):
        return True
    if any(s in PR_TITLE.lower() for s in ["[ai]", "[copilot]", "[cursor]", "[claude]", "[bot]"]):
        return True
    _, variant_id = parse_autoresearch_tag(PR_BODY)
    return variant_id is not None

# ---------------------------------------------------------------------------
# Evidence block
# ---------------------------------------------------------------------------

def compute_risk_indicators(files):
    touched = [f["filename"] for f in files]
    patterns = {
        "money/payment":  ["payment", "checkout", "billing", "pricing", "stripe", "invoice"],
        "auth/security":  ["auth", "login", "password", "token", "secret", "oauth"],
        "config/env":     [".env", "config", "settings", "secrets"],
        "database":       ["migration", "schema", "sql", "db", "database"],
        "API contract":   ["openapi", "swagger", "routes", "api/v"],
    }
    found = [label for label, kws in patterns.items()
             if any(kw in p.lower() for p in touched for kw in kws)]
    return found or ["no high-risk areas detected"]

def score_ci_status(check_runs):
    if not check_runs:
        return "no CI checks found", False
    conclusions = [c.get("conclusion") for c in check_runs if c.get("conclusion")]
    if not conclusions:
        return f"{len(check_runs)} checks in progress", False
    failed = [c["name"] for c in check_runs if c.get("conclusion") in ("failure", "timed_out")]
    passed = [c for c in check_runs if c.get("conclusion") == "success"]
    if failed:
        return f"FAILING: {', '.join(failed[:3])}", False
    return f"all {len(passed)} checks passed", True

def score_compliance_heuristics(pr_body, experiment):
    """
    Lightweight PR-body checks (M3). Not a substitute for human review.
    Returns (summary_line, checklist_rows) for markdown.
    """
    comp = experiment.get("compliance") or {}
    if not comp:
        return "", []
    body = pr_body or ""
    body_l = body.lower()
    min_len = int(comp.get("pr_body_min_length") or 0)
    checks = []

    len_ok = len(body.strip()) >= min_len if min_len else True
    checks.append(("PR body length", len_ok, f">= {min_len} chars" if min_len else "n/a"))

    tag_ok = "[autoresearch:task=" in body
    checks.append(("Autoresearch tag in body", tag_ok, "contains [autoresearch:task=…]"))

    verify_ok = any(
        k in body_l for k in ("test", "verify", "pytest", "how to verify", "how to test")
    )
    checks.append(("Verification cue", verify_ok, "mentions tests or verification"))

    passed = sum(1 for _, ok, _ in checks if ok)
    summary = f"{passed}/{len(checks)} heuristic checks passed"
    return summary, checks


def generate_evidence_block(pr, files, check_runs, variant, instructions, task_ref, experiment):
    touched   = [f["filename"] for f in files]
    additions = sum(f.get("additions", 0) for f in files)
    deletions = sum(f.get("deletions", 0) for f in files)
    risk      = compute_risk_indicators(files)
    ci_summary, ci_ok = score_ci_status(check_runs)
    ci_icon   = "✅" if ci_ok else "⚠️"
    test_files = [f for f in touched if "test" in f.lower() or "spec" in f.lower()]

    ev_cfg = experiment.get("evidence") or {}
    large_diff = int(ev_cfg.get("large_diff_additions", 300))
    thin_body = int(ev_cfg.get("thin_body_chars", 50))

    missing = []
    if not test_files:
        missing.append("no test files modified")
    if additions > large_diff:
        missing.append("large diff — consider splitting")
    if not pr.get("body") or len(pr.get("body", "")) < thin_body:
        missing.append("PR description is thin")

    comp_summary, comp_rows = score_compliance_heuristics(pr.get("body"), experiment)
    comp_section = ""
    if comp_summary:
        rows_md = "\n".join(
            f"| {name} | {'✅' if ok else '⚠️'} | {note} |"
            for name, ok, note in comp_rows
        )
        comp_section = f"""

### Instruction compliance (heuristic)

**Summary:** {comp_summary}

| Check | Pass | Notes |
|-------|------|-------|
{rows_md}
"""

    task_row = f"\n| **Task** | `{task_ref}` |" if task_ref else ""
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!-- AUTORESEARCH_EVIDENCE_BLOCK -->
## Change Evidence

| Field | Value |
|-------|-------|
| **Variant** | `{variant.get('id', 'unknown')}` |{task_row}
| **Intent** | {pr.get('title', '')} |
| **Files changed** | {len(touched)} (+{additions} / -{deletions} lines) |
| **Touched areas** | `{"`, `".join(touched[:5])}{"..." if len(touched) > 5 else ""}` |
| **Risk indicators** | {', '.join(risk)} |
| **CI status** | {ci_icon} {ci_summary} |
| **Test coverage** | {"✅ " + str(len(test_files)) + " test file(s) touched" if test_files else "⚠️ no test files found"} |
| **Missing evidence** | {', '.join(missing) if missing else 'none'} |
{comp_section}
<details>
<summary>Active instructions: <code>{variant.get('id', 'unknown')}</code></summary>

{instructions or "_No instructions loaded._"}

</details>

---
*[Agent Prompt Autoresearch](https://github.com/{REPO}) · variant `{variant.get('id', '')}` · {ts}*
"""

# ---------------------------------------------------------------------------
# Outcome recording
# ---------------------------------------------------------------------------

def record_outcome(state, pr_number, event, data):
    key = str(pr_number)
    if key not in state["pr_runs"]:
        state["pr_runs"][key] = {
            "pr_number":             pr_number,
            "variant_id":            data.get("variant_id"),
            "task_ref":              data.get("task_ref"),
            "author":                data.get("author"),
            "base_branch":           data.get("base_branch"),
            "opened_at":             data.get("opened_at"),
            "events":                [],
            "review_round_trips":    0,
            "first_pass_ci_success": None,
            "merged_at":             None,
        }
    run = state["pr_runs"][key]
    run["events"].append({
        "event": event,
        "ts": datetime.datetime.utcnow().isoformat(),
        **{k: v for k, v in data.items() if k != "opened_at"},
    })
    if event == "ci_result" and run["first_pass_ci_success"] is None:
        run["first_pass_ci_success"] = data.get("ci_ok", False)
    if event == "review_submitted" and data.get("review_state") == "changes_requested":
        run["review_round_trips"] = run.get("review_round_trips", 0) + 1
    if event == "merged":
        run["merged_at"] = datetime.datetime.utcnow().isoformat()
        oa = run.get("opened_at")
        if oa:
            try:
                oa_s = str(oa).replace("Z", "+00:00")
                me_s = str(run["merged_at"]).replace("Z", "+00:00")
                opened = datetime.datetime.fromisoformat(oa_s)
                merged = datetime.datetime.fromisoformat(me_s)
                run["time_to_merge_hours"] = round(
                    (merged - opened).total_seconds() / 3600.0, 2
                )
            except Exception:
                run["time_to_merge_hours"] = None

# ---------------------------------------------------------------------------
# Experiment evaluation (see scripts/experiment_metrics.py)
# ---------------------------------------------------------------------------

def generate_report(decisions, experiment):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Autoresearch Experiment Report",
        f"**Experiment:** `{experiment.get('name', 'unnamed')}`  ",
        f"**Generated:** {ts}", "",
    ]
    pm = primary_metric_label(experiment)
    th = promotion_threshold_pct(experiment)
    for d in decisions:
        icon = "PROMOTE" if d["promote"] else "REJECT"
        lines += [
            f"## {icon}: `{d['variant_id']}` vs `{d['baseline_id']}`", "",
            f"- **Primary metric:** `{pm}` — improvement {d['improvement_pct']:+.1f}% (need ≥{th}%)",
            f"- **Guardrails:** {'passed' if d['guardrail_ok'] else 'FAILED — ' + '; '.join(d['guardrail_notes'])}",
            f"- **Baseline:** {d['baseline_stats']['count']} PRs, avg {d['baseline_stats']['avg_metric']:.4f} ({pm}), {d['baseline_stats']['ci_pass_rate']:.1%} CI pass rate",
            f"- **Challenger:** {d['challenger_stats']['count']} PRs, avg {d['challenger_stats']['avg_metric']:.4f} ({pm}), {d['challenger_stats']['ci_pass_rate']:.1%} CI pass rate",
        ]
        extra = report_metric_section(d, experiment)
        if extra:
            lines.append("")
            lines.extend(extra)
        lines.append("")
        if d["promote"]:
            lines.append(f"> **Recommendation:** replace `{d['baseline_id']}` with `{d['variant_id']}` as the new baseline.")
        else:
            lines.append(f"> **Recommendation:** keep `{d['baseline_id']}`. `{d['variant_id']}` did not meet the threshold.")
        lines.append("")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Optional auto-promotion (opens a PR updating program.md baseline)
# ---------------------------------------------------------------------------

def replace_baseline_section_in_program(program_text: str, baseline_id: str, winner_id: str) -> str | None:
    """
    Copy the winner variant section body under the baseline marker (same as PROMOTION.md).
    Returns None if sections are missing or baseline could not be replaced.
    """
    winner_body = extract_variant_from_program(program_text, winner_id)
    if not winner_body:
        return None
    pattern = re.compile(
        rf"(<!--\s*VARIANT:\s*{re.escape(baseline_id)}\s*-->)\s*(.*?)(?=<!--\s*VARIANT:|\Z)",
        re.DOTALL | re.IGNORECASE,
    )

    def repl(m):
        return f"{m.group(1)}\n\n{winner_body}\n\n"

    new_text, n = pattern.subn(repl, program_text, count=1)
    if n != 1:
        return None
    return new_text


def compute_promotion_fingerprint(decisions) -> str:
    """Stable hash so we only open one PR per identical evaluation outcome."""
    payload = json.dumps(decisions, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _gh_contents_path(rel_path: str) -> str:
    return "/".join(urllib.parse.quote(seg, safe="") for seg in rel_path.split("/"))


def open_promotion_pull_request(
    program_path: str,
    baseline_id: str,
    winner_id: str,
    experiment_name: str,
) -> str:
    """
    Fetch program.md from the default branch, replace baseline with winner, commit on a new branch, open PR.
    Returns the PR html_url.
    """
    repo_info = gh_get(f"/repos/{REPO}")
    default_branch = repo_info["default_branch"]
    base_ref = gh_get(f"/repos/{REPO}/git/ref/heads/{default_branch}")
    base_sha = base_ref["object"]["sha"]

    encoded = _gh_contents_path(program_path)
    file_meta = gh_get(f"/repos/{REPO}/contents/{encoded}?ref={default_branch}")
    if not isinstance(file_meta, dict) or file_meta.get("type") != "file":
        raise RuntimeError(f"Could not read {program_path} on {default_branch}")
    raw = file_meta.get("content", "")
    current = base64.b64decode(raw.replace("\n", "")).decode("utf-8")
    file_sha = file_meta["sha"]

    new_text = replace_baseline_section_in_program(current, baseline_id, winner_id)
    if not new_text:
        raise RuntimeError(f"Could not merge {winner_id} into baseline section {baseline_id}")

    branch_name = f"autoresearch/promote-{winner_id}-{int(time.time())}"
    gh_post(f"/repos/{REPO}/git/refs", {"ref": f"refs/heads/{branch_name}", "sha": base_sha})

    b64 = base64.b64encode(new_text.encode("utf-8")).decode("ascii")
    gh_put(
        f"/repos/{REPO}/contents/{encoded}",
        {
            "message": f"autoresearch: promote {winner_id} to baseline ({baseline_id})",
            "content": b64,
            "branch": branch_name,
            "sha": file_sha,
        },
    )

    title = f"Autoresearch: promote `{winner_id}` as new baseline"
    body_lines = [
        "This pull request was opened automatically because the experiment evaluation recommended **promoting**",
        f"the `{winner_id}` variant over `{baseline_id}`.",
        "",
        f"Experiment: `{experiment_name}`",
        "",
        "Review the diff, then merge to apply the new baseline instructions in `program.md`.",
        "",
        "---",
        f"*[Agent Prompt Autoresearch](https://github.com/{REPO}) · auto-promotion*",
    ]
    pr = gh_post(
        f"/repos/{REPO}/pulls",
        {
            "title": title,
            "head": branch_name,
            "base": default_branch,
            "body": "\n".join(body_lines),
        },
    )
    return pr.get("html_url", "")


def maybe_auto_promote_pr(state, experiment, decisions):
    """
    If experiment.yaml has promotion.auto_open_pr: true and a variant is recommended,
    open a PR that updates the baseline section in program.md (idempotent via fingerprint).
    """
    if not decisions or not REPO:
        return
    promo = experiment.get("promotion") or {}
    if not promo.get("auto_open_pr", False):
        return
    winner = next((d for d in decisions if d.get("promote")), None)
    if not winner:
        return
    fp = compute_promotion_fingerprint(decisions)
    if state.get("last_auto_promotion_fingerprint") == fp:
        print("  Auto-promotion: same decision fingerprint as last run — skipping.")
        return
    src = merge_instruction_source(experiment)
    if not src.get("use_program", True):
        print("  Auto-promotion: instruction_source.use_program is false — skipping.")
        return
    program_path = src.get("program_file") or ".repo-autoresearch/program.md"
    baseline_id = winner["baseline_id"]
    winner_id = winner["variant_id"]
    try:
        pr_url = open_promotion_pull_request(
            program_path=program_path,
            baseline_id=baseline_id,
            winner_id=winner_id,
            experiment_name=experiment.get("name", ""),
        )
    except Exception as e:
        print(f"  Auto-promotion failed: {e}")
        return
    state["last_auto_promotion_fingerprint"] = fp
    state["last_auto_promotion"] = {
        "opened_at":           datetime.datetime.utcnow().isoformat(),
        "winner_variant_id":   winner_id,
        "baseline_variant_id": baseline_id,
        "pull_request_url":    pr_url,
    }
    print(f"  Auto-promotion: opened {pr_url}")

# ---------------------------------------------------------------------------
# Check suite handling
# ---------------------------------------------------------------------------

def handle_check_suite():
    """
    Fired when GitHub check_suite completes — i.e. when CI finishes.
    Finds the PR run(s) associated with this commit SHA and writes
    the real first_pass_ci_success value into the Gist.

    Also writes ci_checks: one row per configured GitHub Check Run (filtered by
    experiment ci_tracking), so the Gist mirrors the PR checks UI.

    This fires AFTER the PR-open event, so it overwrites the
    speculative False that was recorded when the PR first opened.
    """
    if not CHECK_SHA or not CHECK_CONCLUSION:
        return

    ci_passed = CHECK_CONCLUSION == "success"

    # Parse the PR numbers GitHub attached to this check_suite
    try:
        pr_list = json.loads(CHECK_PR_NUMBERS)
        pr_numbers = [str(pr["number"]) for pr in pr_list if pr.get("number")]
    except Exception:
        pr_numbers = []

    if not pr_numbers:
        print(f"  check_suite completed ({CHECK_CONCLUSION}) but no linked PRs — skipping")
        return

    experiment = load_experiment()
    try:
        raw_runs = get_check_runs_for_sha(CHECK_SHA)
    except Exception as e:
        print(f"  Warning: could not load check runs for {CHECK_SHA[:8]}…: {e}")
        raw_runs = []
    filtered = filter_check_runs_for_experiment(raw_runs, experiment)
    ci_rows = serialize_check_runs_for_gist(filtered)
    recorded_at = datetime.datetime.utcnow().isoformat()

    state = load_state(experiment)
    updated_first_pass = []
    matched_pr = []

    for pr_num in pr_numbers:
        if pr_num not in state["pr_runs"]:
            continue
        run = state["pr_runs"][pr_num]
        matched_pr.append(pr_num)
        run["ci_checks"] = ci_rows
        run["ci_checks_sha"] = CHECK_SHA
        run["ci_checks_recorded_at"] = recorded_at

        # First full suite result for experiment metrics (unchanged semantics)
        if run.get("first_pass_ci_success") is None or not run.get("ci_finalised"):
            run["first_pass_ci_success"] = ci_passed
            run["ci_finalised"] = True
            run["ci_conclusion"] = CHECK_CONCLUSION
            updated_first_pass.append(pr_num)

    if matched_pr:
        save_state(state, experiment)
        n = len(ci_rows)
        print(
            f"  CI checks ({n}) + conclusion '{CHECK_CONCLUSION}' for PR(s): {matched_pr} "
            f"(first_pass updated: {updated_first_pass})"
        )
    else:
        print(f"  check_suite completed but no matching PR runs in state")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main_auto_promotion_only():
    """
    Invoked by a dedicated workflow job with contents:write.
    Runs after the main autoresearch job on PR close; opens a promotion PR only if
    experiment.yaml has promotion.auto_open_pr and evaluation recommends PROMOTE.
    Does not duplicate record_outcome / report (main job already did that).
    """
    print(f"\nAutoresearch auto-promotion job — PR #{PR_NUMBER} action={PR_ACTION}")
    if not PR_NUMBER:
        print("No PR context — skipping.")
        return
    if PR_ACTION != "closed":
        print("  Not a closed PR — skipping.")
        return
    experiment = load_experiment()
    promo = experiment.get("promotion") or {}
    if not promo.get("auto_open_pr", False):
        print("  promotion.auto_open_pr is false — skipping auto-promotion job.")
        return
    state = load_state(experiment)
    target_branches = experiment.get("cohort", {}).get("target_branches", ["main"])
    if PR_BASE_BRANCH not in target_branches:
        print(f"  Branch '{PR_BASE_BRANCH}' not in scope — skipping.")
        return
    decisions = evaluate_experiment(state, experiment)
    if not decisions:
        print("  No evaluation decisions — skipping auto-promotion.")
        return
    maybe_auto_promote_pr(state, experiment, decisions)
    save_state(state, experiment)
    print("  Auto-promotion job done.\n")


def main():
    if _auto_promotion_only():
        main_auto_promotion_only()
        return

    print(f"\nAutoresearch — PR #{PR_NUMBER} action={PR_ACTION} author={PR_AUTHOR}")

    # check_suite event — CI finished, record the real result
    if CHECK_SHA:
        handle_check_suite()
        return

    if not PR_NUMBER:
        print("No PR context — skipping.")
        return

    experiment = load_experiment()
    state      = load_state(experiment)

    target_branches = experiment.get("cohort", {}).get("target_branches", ["main"])
    if PR_BASE_BRANCH not in target_branches:
        print(f"  Branch '{PR_BASE_BRANCH}' not in scope — skipping.")
        return

    if PR_ACTION in ("opened", "synchronize", "reopened"):
        variant, task_ref = resolve_variant(PR_BODY, experiment)
        if not variant:
            print("  Not an autoresearch PR — skipping.")
            return
        instructions = load_variant_instructions(variant, experiment, ROOT)
        pr           = get_pr_details()
        files        = get_pr_files()
        check_runs   = get_check_runs()
        evidence = generate_evidence_block(pr, files, check_runs, variant, instructions, task_ref, experiment)
        update_or_create_pr_comment("AUTORESEARCH_EVIDENCE_BLOCK", evidence)

        # Record the PR run — ci_pass left as None until check_suite fires
        record_outcome(state, PR_NUMBER, "opened", {
            "variant_id":    variant["id"],
            "task_ref":      task_ref,
            "author":        PR_AUTHOR,
            "base_branch":   PR_BASE_BRANCH,
            "opened_at":     datetime.datetime.utcnow().isoformat(),
            "files_changed": len(files),
        })
        # Note: first_pass_ci_success is NOT set here anymore.
        # It will be set accurately when check_suite:completed fires.

    elif PR_ACTION == "submitted" and REVIEW_STATE:
        record_outcome(state, PR_NUMBER, "review_submitted",
                       {"review_state": REVIEW_STATE})
        print(f"  Recorded review: {REVIEW_STATE}")

    elif PR_ACTION == "closed":
        event = "merged" if PR_MERGED else "closed_unmerged"
        record_outcome(state, PR_NUMBER, event, {})
        print(f"  PR #{PR_NUMBER} {event}")
        decisions = evaluate_experiment(state, experiment)
        if decisions:
            report = generate_report(decisions, experiment)
            SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
            SUMMARY_FILE.write_text(report)
            post_pr_comment(f"## Autoresearch Experiment Report\n\n{report}")
            state["promotion_decisions"].append({
                "decisions":       decisions,
                "evaluated_at":    datetime.datetime.utcnow().isoformat(),
                "experiment_name": experiment.get("name"),
            })
            print("  Experiment evaluated — report posted.")
            if not _skip_auto_promotion():
                maybe_auto_promote_pr(state, experiment, decisions)

    save_state(state, experiment)
    print("  Done.\n")

if __name__ == "__main__":
    main()