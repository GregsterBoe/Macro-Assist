#!/usr/bin/env bash
#
# trigger_pipeline.sh — start a workflow from outside GitHub.
#
# The pipeline is no longer driven by GitHub's `schedule:` — only backstopped by
# one late slot (see the header of .github/workflows/pipeline.yml for why). An
# external cron service calls the workflow-dispatch API instead; this script is
# that call, and the reference for services that only speak raw HTTP:
#
#   POST https://api.github.com/repos/<owner>/<repo>/actions/workflows/<file>/dispatches
#   Authorization: Bearer <token>
#   Accept: application/vnd.github+json
#   {"ref":"main","inputs":{"source":"cron-primary"}}
#
# A 204 means GitHub accepted the request — not that the run succeeded. The run
# itself is then visible in the Actions tab like any other.
#
# Usage:
#   ./trigger_pipeline.sh                                   # daily pipeline, source=cron
#   ./trigger_pipeline.sh --source cron-catchup
#   ./trigger_pipeline.sh --workflow macro_weekly_refit.yml --source cron-refit
#   ./trigger_pipeline.sh --input asof=2026-08-31 --input force=true
#   ./trigger_pipeline.sh --dry-run                          # print the request, send nothing
#
# Environment:
#   MACRO_ASSIST_TOKEN  (or GH_TOKEN)   required — fine-grained PAT for this repo
#                                       with Actions: read and write.
#   MACRO_ASSIST_REPO                   optional — owner/repo, default below.
#
# Every input is sent as a JSON string; GitHub coerces it to the type the
# workflow declares, so `--input force=true` reaches a `type: boolean` input
# correctly.
#
set -euo pipefail

REPO="${MACRO_ASSIST_REPO:-GregsterBoe/Macro-Assist}"
TOKEN="${MACRO_ASSIST_TOKEN:-${GH_TOKEN:-}}"
WORKFLOW="pipeline.yml"
REF="main"
SOURCE="cron"
DRY_RUN=0
INPUTS=()

# Print the header comment block above as the help text (stops at the first
# non-comment line, so it cannot drift out of sync as that block grows).
usage() { awk 'NR>1 { if (!/^#/) exit; sub(/^# ?/, ""); print }' "$0"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --workflow) WORKFLOW="${2:?--workflow needs a value}"; shift 2 ;;
    --ref)      REF="${2:?--ref needs a value}";           shift 2 ;;
    --source)   SOURCE="${2:?--source needs a value}";     shift 2 ;;
    --input)    INPUTS+=("${2:?--input needs key=value}"); shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)  usage; exit 0 ;;
    *) echo "error: unknown argument '$1' (try --help)" >&2; exit 2 ;;
  esac
done

if [ -z "$TOKEN" ] && [ "$DRY_RUN" -eq 0 ]; then
  echo "error: no token. Set MACRO_ASSIST_TOKEN (or GH_TOKEN) to a fine-grained PAT" >&2
  echo "       for $REPO with 'Actions: read and write'." >&2
  exit 1
fi

# JSON-escape a value. Inputs here are dates, booleans and small integers, so
# backslash/quote/control handling is enough — no general JSON encoder needed.
json_escape() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/\t/\\t/g' | tr -d '\n\r'
}

BODY="{\"ref\":\"$(json_escape "$REF")\",\"inputs\":{\"source\":\"$(json_escape "$SOURCE")\""
for kv in ${INPUTS+"${INPUTS[@]}"}; do
  case "$kv" in
    *=*) : ;;
    *) echo "error: --input expects key=value, got '$kv'" >&2; exit 2 ;;
  esac
  KEY="${kv%%=*}"
  VAL="${kv#*=}"
  [ -n "$KEY" ] || { echo "error: --input has an empty key: '$kv'" >&2; exit 2; }
  BODY="$BODY,\"$(json_escape "$KEY")\":\"$(json_escape "$VAL")\""
done
BODY="$BODY}}"

URL="https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW/dispatches"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "POST $URL"
  echo "$BODY"
  exit 0
fi

# Retry only what is worth retrying: a transport failure, a GitHub 5xx, or a
# rate-limit 429. An auth or not-found error will not fix itself on attempt two.
ATTEMPTS=4
DELAY=5
for attempt in $(seq 1 "$ATTEMPTS"); do
  set +e
  CODE="$(curl --silent --show-error --output /tmp/trigger_pipeline.$$ --write-out '%{http_code}' \
    --max-time 30 \
    --request POST "$URL" \
    --header "Authorization: Bearer $TOKEN" \
    --header "Accept: application/vnd.github+json" \
    --header "X-GitHub-Api-Version: 2022-11-28" \
    --header "Content-Type: application/json" \
    --data "$BODY" 2>/tmp/trigger_pipeline.err.$$)"
  CURL_RC=$?
  set -e

  if [ "$CURL_RC" -eq 0 ] && [ "$CODE" = "204" ]; then
    rm -f "/tmp/trigger_pipeline.$$" "/tmp/trigger_pipeline.err.$$"
    echo "Dispatched $WORKFLOW (ref $REF, source $SOURCE) on $REPO."
    echo "Run: https://github.com/$REPO/actions/workflows/$WORKFLOW"
    exit 0
  fi

  if [ "$CURL_RC" -ne 0 ]; then
    REASON="curl failed (exit $CURL_RC): $(cat "/tmp/trigger_pipeline.err.$$" 2>/dev/null)"
  else
    REASON="HTTP $CODE: $(cat "/tmp/trigger_pipeline.$$" 2>/dev/null)"
  fi

  RETRYABLE=0
  if [ "$CURL_RC" -ne 0 ] || [ "$CODE" = "429" ] || [ "${CODE:0:1}" = "5" ]; then
    RETRYABLE=1
  fi

  if [ "$RETRYABLE" -eq 0 ] || [ "$attempt" -eq "$ATTEMPTS" ]; then
    echo "error: dispatch failed — $REASON" >&2
    case "$CODE" in
      401) echo "       401: the token is invalid or expired. Fine-grained PATs expire; issue a new one." >&2 ;;
      403) echo "       403: the token lacks 'Actions: read and write' on $REPO." >&2 ;;
      404) echo "       404: no workflow '$WORKFLOW' with a workflow_dispatch trigger on ref '$REF'," >&2
           echo "            or the token cannot see $REPO. The trigger must exist on the default branch." >&2 ;;
      422) echo "       422: GitHub rejected the inputs (unknown input name, or a bad value)." >&2 ;;
    esac
    rm -f "/tmp/trigger_pipeline.$$" "/tmp/trigger_pipeline.err.$$"
    exit 1
  fi

  echo "attempt $attempt/$ATTEMPTS failed — $REASON; retrying in ${DELAY}s" >&2
  sleep "$DELAY"
  DELAY=$((DELAY * 2))
done
