#!/usr/bin/env bash
#
# ci_mount_output.sh — mount the 'output' branch at <repo>/results (CI).
#
# Code lives on 'main'; generated output lives on the orphan 'output' branch.
# Pipeline scripts read prior output (scoring scans past *-macro.md reports, the
# portfolio reads the prior book) and write new output, all under <repo>/results.
# This mounts 'output' there as a git worktree so those reads/writes work exactly
# as in local dev. Pair with ci_publish_results.sh at the end of the job.
#
# Usage — run from the repo root, after checkout, before the pipeline runs:
#   bash .macro-assist/ci_mount_output.sh
#
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"

git -C "$REPO" config user.name  >/dev/null 2>&1 || git -C "$REPO" config user.name  "macro-assist[bot]"
git -C "$REPO" config user.email >/dev/null 2>&1 || git -C "$REPO" config user.email "macro-assist[bot]@users.noreply.github.com"

# Fetch into an explicit remote-tracking ref — a single-branch CI checkout has no
# origin/output ref otherwise.
git -C "$REPO" fetch --depth=1 origin +refs/heads/output:refs/remotes/origin/output
rm -rf "$REPO/results"                       # ensure a clean mount point (main gitignores it)
git -C "$REPO" worktree add -B output "$REPO/results" origin/output
echo "Mounted 'output' at $REPO/results"
