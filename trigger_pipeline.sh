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
#   ./trigger_pipeline.sh --check                            # verify the setup, start no run
#
# --check answers "will tomorrow's cron work?" without burning a run:
#   1. GET the workflow — proves the token reaches the repo and the workflow is
#      registered and dispatchable (a 404 here is the "not on the default branch
#      yet" case).
#   2. POST a dispatch carrying one deliberately invalid input name. GitHub
#      authorizes the request before it validates the body, so a 422 proves the
#      token is allowed to dispatch while no run is created.
# Run it after any token change; nothing else in the setup expires.
#
# --source '' (empty) reproduces what the `schedule:` backstop sends, which is no
# inputs at all: the run should come out labelled `schedule-backstop`.
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
CHECK=0
INPUTS=()

# Print the header comment block above as the help text (stops at the first
# non-comment line, so it cannot drift out of sync as that block grows).
usage() { awk 'NR>1 { if (!/^#/) exit; sub(/^# ?/, ""); print }' "$0"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --workflow) WORKFLOW="${2:?--workflow needs a value}"; shift 2 ;;
    --ref)      REF="${2:?--ref needs a value}";           shift 2 ;;
    # Not `${2:?}`: an empty --source is meaningful, see the header.
    --source)   SOURCE="${2?--source needs a value}";      shift 2 ;;
    --input)    INPUTS+=("${2:?--input needs key=value}"); shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    --check)    CHECK=1;   shift ;;
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

BASE="https://api.github.com/repos/$REPO"
URL="$BASE/actions/workflows/$WORKFLOW/dispatches"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "POST $URL"
  echo "$BODY"
  exit 0
fi

TMP_BODY="$(mktemp)"; TMP_ERR="$(mktemp)"
trap 'rm -f "$TMP_BODY" "$TMP_ERR"' EXIT

# Sets CODE (HTTP status; empty when curl itself failed) and CURL_RC.
github_api() {
  local method="$1" url="$2" data="${3:-}"
  local args=(--silent --show-error --output "$TMP_BODY" --write-out '%{http_code}'
              --max-time 30 --request "$method" "$url"
              --header "Authorization: Bearer $TOKEN"
              --header "Accept: application/vnd.github+json"
              --header "X-GitHub-Api-Version: 2022-11-28")
  if [ -n "$data" ]; then
    args+=(--header "Content-Type: application/json" --data "$data")
  fi
  set +e
  CODE="$(curl "${args[@]}" 2>"$TMP_ERR")"
  CURL_RC=$?
  set -e
}

# Why a request failed, in one line, from whichever half of it broke.
reason() {
  if [ "$CURL_RC" -ne 0 ]; then
    echo "curl failed (exit $CURL_RC): $(cat "$TMP_ERR" 2>/dev/null)"
  else
    echo "HTTP $CODE: $(tr -d '\n' < "$TMP_BODY" 2>/dev/null)"
  fi
}

explain_code() {
  case "$1" in
    401) echo "       401: the token is invalid or expired. Fine-grained PATs expire; issue a new one." >&2 ;;
    403) echo "       403: the token lacks 'Actions: read and write' on $REPO." >&2 ;;
    404) echo "       404: no workflow '$WORKFLOW' with a workflow_dispatch trigger on ref '$REF'," >&2
         echo "            or the token cannot see $REPO. The trigger must exist on the default branch." >&2 ;;
    422) echo "       422: GitHub rejected the inputs (unknown input name, or a bad value)." >&2 ;;
  esac
}

if [ "$CHECK" -eq 1 ]; then
  echo "Checking $REPO — workflow $WORKFLOW, ref $REF. No run will be started."

  github_api GET "$BASE/actions/workflows/$WORKFLOW"
  if [ "$CURL_RC" -ne 0 ] || [ "$CODE" != "200" ]; then
    echo "error: cannot read the workflow — $(reason)" >&2
    explain_code "$CODE"
    exit 1
  fi
  STATE="$(sed -n 's/.*"state"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$TMP_BODY" | head -1)"
  echo "  ✓ workflow found, state: ${STATE:-unknown}"
  if [ -n "$STATE" ] && [ "$STATE" != "active" ]; then
    echo "error: the workflow is not active (state: $STATE) — GitHub will accept the" >&2
    echo "       dispatch but run nothing. Re-enable it in the Actions tab." >&2
    exit 1
  fi

  # Deliberately invalid input name: authorization is checked before the body, so
  # 422 means "allowed to dispatch, and nothing was started".
  github_api POST "$URL" "{\"ref\":\"$(json_escape "$REF")\",\"inputs\":{\"__trigger_pipeline_check__\":\"1\"}}"
  case "$CODE" in
    422) echo "  ✓ token may dispatch (rejected the probe's bogus input, as intended)"
         echo "Setup looks good. A real call would be: POST $URL" ;;
    204) echo "warning: GitHub accepted the probe instead of rejecting it, so a real run" >&2
         echo "         HAS started — check the Actions tab. The token works; this script's" >&2
         echo "         no-run assumption does not hold on this API version." >&2
         exit 1 ;;
    *)   echo "error: dispatch probe failed — $(reason)" >&2
         explain_code "$CODE"
         exit 1 ;;
  esac
  exit 0
fi

# Retry only what is worth retrying: a transport failure, a GitHub 5xx, or a
# rate-limit 429. An auth or not-found error will not fix itself on attempt two.
ATTEMPTS=4
DELAY=5
for attempt in $(seq 1 "$ATTEMPTS"); do
  github_api POST "$URL" "$BODY"

  if [ "$CURL_RC" -eq 0 ] && [ "$CODE" = "204" ]; then
    echo "Dispatched $WORKFLOW (ref $REF, source ${SOURCE:-<empty, backstop-style>}) on $REPO."
    echo "Run: https://github.com/$REPO/actions/workflows/$WORKFLOW"
    exit 0
  fi

  RETRYABLE=0
  if [ "$CURL_RC" -ne 0 ] || [ "$CODE" = "429" ] || [ "${CODE:0:1}" = "5" ]; then
    RETRYABLE=1
  fi

  if [ "$RETRYABLE" -eq 0 ] || [ "$attempt" -eq "$ATTEMPTS" ]; then
    echo "error: dispatch failed — $(reason)" >&2
    explain_code "$CODE"
    exit 1
  fi

  echo "attempt $attempt/$ATTEMPTS failed — $(reason); retrying in ${DELAY}s" >&2
  sleep "$DELAY"
  DELAY=$((DELAY * 2))
done
