#!/usr/bin/env bash
#
# ci_publish_results.sh — commit & push the results/ worktree to 'output' (CI).
#
# Pairs with ci_mount_output.sh: after the pipeline has written new output into
# the mounted <repo>/results worktree, this commits and pushes it to origin/output.
# Genuinely code-tracked files (data/, .macro-assist/data/ models) are committed
# to 'main' by the workflow separately, not here.
#
# Usage — run from the repo root, after the pipeline has written into results/:
#   bash .macro-assist/ci_publish_results.sh "portfolio: 2026-08-24 weekly rebalance"
#
set -euo pipefail

MSG="${1:-output: update $(date -u +%Y-%m-%d)}"
REPO="$(git rev-parse --show-toplevel)"
RES="$REPO/results"

if [ ! -e "$RES/.git" ]; then
  echo "error: $RES is not a git worktree — run ci_mount_output.sh first." >&2
  exit 1
fi

git -C "$RES" config user.name  >/dev/null 2>&1 || git -C "$RES" config user.name  "macro-assist[bot]"
git -C "$RES" config user.email >/dev/null 2>&1 || git -C "$RES" config user.email "macro-assist[bot]@users.noreply.github.com"

git -C "$RES" add -A
if git -C "$RES" diff --cached --quiet; then
  echo "No output changes to publish."
  exit 0
fi

git -C "$RES" commit -m "$MSG"

# Rebase onto whatever is on 'output' and push. The rebase alone is not enough:
# another job can land a commit between our fetch and our push, and the push is
# then rejected. Retry the whole fetch/rebase/push cycle rather than failing the
# stage over a lost race.
ATTEMPTS=5
for attempt in $(seq 1 "$ATTEMPTS"); do
  # Both halves are guarded: under `set -e` an unguarded failure here would
  # abort the script instead of retrying, which would turn a transient network
  # blip into a failed pipeline stage.
  if git -C "$RES" pull --rebase --autostash origin output \
     && git -C "$RES" push origin output; then
    echo "Published output to origin/output."
    exit 0
  fi
  git -C "$RES" rebase --abort 2>/dev/null || true   # leave no half-finished rebase behind
  if [ "$attempt" -lt "$ATTEMPTS" ]; then
    echo "publish to 'output' failed (attempt ${attempt}/${ATTEMPTS}) — retrying." >&2
    sleep $(( attempt * 3 ))
  fi
done

echo "error: could not publish to origin/output after 5 attempts." >&2
exit 1
