#!/usr/bin/env bash
#
# publish_output.sh — commit & push generated output to the 'output' branch.
#
# Code lives on 'main'; generated output (results/) lives on the orphan 'output'
# branch, mounted here as a git worktree at ./results. Scripts write to results/
# exactly as before; run this after a pipeline run to publish that output.
#
# Usage:
#   ./publish_output.sh                 # message: "output: update <date>"
#   ./publish_output.sh "portfolio: 2026-08-24 weekly rebalance"
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS="$REPO_ROOT/results"
MSG="${1:-output: update $(date +%Y-%m-%d)}"

if [ ! -d "$RESULTS/.git" ] && [ ! -f "$RESULTS/.git" ]; then
  echo "error: $RESULTS is not a git worktree. Run: git worktree add results output" >&2
  exit 1
fi

if [ -z "$(git -C "$RESULTS" status --porcelain)" ]; then
  echo "No output changes to publish."
  exit 0
fi

git -C "$RESULTS" add -A
git -C "$RESULTS" commit -m "$MSG"
git -C "$RESULTS" push origin output
echo "Published output to origin/output."
