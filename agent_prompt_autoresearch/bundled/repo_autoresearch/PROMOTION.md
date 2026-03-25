# Promoting a winning variant

## Automatic promotion (optional)

In `experiment.yaml`, set `promotion.auto_open_pr: true`. When an evaluation run recommends **PROMOTE** for a challenger, a **dedicated GitHub Actions job** (runs on PR close, after the main autoresearch job) opens a pull request that copies the winner’s `program.md` section over the baseline section (same manual steps below, but scripted). The Gist state stores a fingerprint so the same evaluation outcome does not open duplicate PRs. Leave `auto_open_pr: false` (default) to review and merge instruction changes yourself.

## Manual promotion

After the autoresearch evaluation recommends promoting a challenger:

1. Open `.repo-autoresearch/program.md`.
2. Copy the full markdown under the winner's `<!-- VARIANT: ... -->` section up to the next variant marker or end of file.
3. Replace the content under the baseline variant marker with that text (keep the `<!-- VARIANT: baseline -->` line).
4. Optionally rename or archive the old challenger section and add a new challenger variant in `experiment.yaml` + new `<!-- VARIANT: ... -->` block.
5. Merge a PR with these edits so future `get_variant.py` assignments use the new baseline text for the control group.

If you still use per-file packs (`instruction_pack` in `experiment.yaml`) instead of `program.md`, copy the winning file over `variants/baseline.md` instead.
