#!/usr/bin/env python3
"""
create_gist.py — run once before your first experiment
-------------------------------------------------------
    export GITHUB_TOKEN=ghp_your_token   (needs "gist" scope)
    python scripts/create_gist.py
"""
import json, os, sys
try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

def main():
    if not GITHUB_TOKEN:
        print("Error: set GITHUB_TOKEN (needs 'gist' scope)")
        sys.exit(1)

    r = requests.post(
        "https://api.github.com/gists",
        headers=HEADERS,
        json={
            "description": "Agent Prompt Autoresearch — experiment state",
            "public": False,
            "files": {
                "autoresearch-state.json": {
                    "content": json.dumps({"pr_runs": {}, "promotion_decisions": []}, indent=2)
                }
            }
        },
        timeout=15,
    )
    if not r.ok:
        print(f"Failed: {r.status_code} {r.text[:200]}"); sys.exit(1)

    gist = r.json()
    print(f"\nGist created: {gist['html_url']}\n")
    print("Add these two secrets to your repo:")
    print("  Settings → Secrets and variables → Actions → New secret\n")
    print(f"  GIST_ID    = {gist['id']}")
    print(f"  GIST_TOKEN = {GITHUB_TOKEN}\n")

if __name__ == "__main__":
    main()
```

---

**`.gitignore`** (new file)
```
__pycache__/
*.pyc
.venv/
venv/
.env
.repo-autoresearch/reports/.gist_id