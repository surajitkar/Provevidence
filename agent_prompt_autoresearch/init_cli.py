"""
Scaffold .repo-autoresearch/ and scripts/ for Agent Prompt Autoresearch (M1).

Run: autoresearch-init  or  python -m agent_prompt_autoresearch.init_cli
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def _repo_root_from_package() -> Path:
    """Directory containing agent_prompt_autoresearch/ (editable install) or site-packages."""
    return Path(__file__).resolve().parent.parent


def _copy_tree(src: Path, dst: Path, force: bool) -> None:
    if dst.exists() and not force:
        return
    if src.is_dir():
        if dst.exists() and force:
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    elif src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialize Agent Prompt Autoresearch in the current repository."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing .repo-autoresearch and scripts/ (destructive).",
    )
    parser.add_argument(
        "--with-workflow",
        action="store_true",
        help="Also install .github/workflows/autoresearch.yml",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current directory).",
    )
    args = parser.parse_args()

    target: Path = args.target.resolve()
    pkg_root = _repo_root_from_package()
    bundled = _package_dir() / "bundled"

    dev_dot = pkg_root / ".repo-autoresearch"
    bundle_dot = bundled / "repo_autoresearch"
    source_dot = dev_dot if dev_dot.is_dir() else bundle_dot

    dev_scripts = pkg_root / "scripts"
    bundle_scripts = bundled / "scripts"
    source_scripts = (
        dev_scripts if (dev_scripts / "autoresearch.py").is_file() else bundle_scripts
    )

    dev_workflow = pkg_root / ".github" / "workflows" / "autoresearch.yml"
    bundle_workflow = bundled / "github" / "workflows" / "autoresearch.yml"
    source_workflow = (
        dev_workflow if dev_workflow.is_file() else bundle_workflow
    )

    if not source_dot.is_dir():
        print(
            "Error: could not find template .repo-autoresearch (bundled data missing).",
            file=sys.stderr,
        )
        sys.exit(1)

    out_dot = target / ".repo-autoresearch"
    out_scripts = target / "scripts"
    out_reports = out_dot / "reports"
    out_reports.mkdir(parents=True, exist_ok=True)

    if out_dot.exists() and not args.force:
        print(f"  Exists: {out_dot} (use --force to replace)")
    else:
        _copy_tree(source_dot, out_dot, args.force)
        print(f"  Wrote {out_dot}")

    if source_scripts.is_dir() and (source_scripts / "autoresearch.py").is_file():
        if out_scripts.exists() and not args.force:
            print(f"  Exists: {out_scripts} (use --force to replace scripts)")
        else:
            out_scripts.mkdir(parents=True, exist_ok=True)
            for name in (
                "autoresearch.py",
                "get_variant.py",
                "draft_challenger.py",
                "experiment_metrics.py",
                "record_metric.py",
                "validate_autoresearch.py",
            ):
                src = source_scripts / name
                if src.is_file():
                    shutil.copy2(src, out_scripts / name)
            print(
                f"  Wrote {out_scripts}/ "
                "("
                "autoresearch, get_variant, draft_challenger, experiment_metrics, "
                "record_metric, validate_autoresearch"
                ")"
            )

    if args.with_workflow and source_workflow.is_file():
        wf = target / ".github" / "workflows" / "autoresearch.yml"
        if wf.exists() and not args.force:
            print(f"  Exists: {wf} (use --force to replace)")
        else:
            wf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_workflow, wf)
            print(f"  Wrote {wf}")

    print()
    print("Next steps:")
    print("  1. Add GitHub Actions secrets: GIST_ID, GIST_TOKEN (gist scope).")
    print("  2. Commit .repo-autoresearch/ and scripts/ (and workflow if used).")
    print("  3. Before each PR, run: python scripts/get_variant.py --task \"<ref>\"")
    print("  4. Read AGENT.md in the framework repo (or copy it here) for the short workflow.")


if __name__ == "__main__":
    main()
