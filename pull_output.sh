#!/usr/bin/env bash
#
# pull_output.sh — fetch & fast-forward the local 'output' worktree.
#
# Code lives on 'main'; generated output (results/) lives on the orphan 'output'
# branch, mounted here as a git worktree at ./results. CI publishes new results
# to origin/output; run this to pull that output into ./results for local review.
#
# It only fast-forwards, so it never clobbers or merges: if ./results has
# uncommitted changes, or has diverged from origin/output, it stops and tells you.
#
# Usage:
#   ./pull_output.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS="$REPO_ROOT/results"

if [ ! -d "$RESULTS/.git" ] && [ ! -f "$RESULTS/.git" ]; then
  echo "error: $RESULTS is not a git worktree. Run: git worktree add results output" >&2
  exit 1
fi

if [ -n "$(git -C "$RESULTS" status --porcelain)" ]; then
  echo "error: $RESULTS has uncommitted changes; refusing to fast-forward." >&2
  echo "       Publish them with ./publish_output.sh or stash/discard first." >&2
  exit 1
fi

git -C "$RESULTS" fetch origin output

LOCAL="$(git -C "$RESULTS" rev-parse output)"
REMOTE="$(git -C "$RESULTS" rev-parse origin/output)"

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "Already up to date with origin/output."
  exit 0
fi

# Only fast-forward: fails if the branches have diverged.
if ! git -C "$RESULTS" merge --ff-only origin/output; then
  echo "error: local output has diverged from origin/output; not fast-forwarding." >&2
  echo "       Reconcile manually (e.g. git -C results log --oneline output ^origin/output)." >&2
  exit 1
fi

echo "Pulled latest output into $RESULTS."
