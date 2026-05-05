#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/catering-be}"
VENV_PATH="${VENV_PATH:-$APP_DIR/.venv/bin/activate}"
CRON_TIME="${CRON_TIME:-0 1 * * *}"
RUNNER="$APP_DIR/scripts/update_subscription_statuses.sh"
JOB_MARKER="# radha-subscription-status-update"
JOB="$CRON_TIME APP_DIR=$APP_DIR VENV_PATH=$VENV_PATH /usr/bin/env bash $RUNNER $JOB_MARKER"

if ! command -v crontab >/dev/null 2>&1; then
  echo "crontab is not installed on this server." >&2
  exit 1
fi

if [ ! -f "$RUNNER" ]; then
  echo "Runner script not found: $RUNNER" >&2
  exit 1
fi

chmod +x "$RUNNER"

TMP_CRON="$(mktemp)"
trap 'rm -f "$TMP_CRON"' EXIT

crontab -l 2>/dev/null | grep -v "$JOB_MARKER" > "$TMP_CRON" || true
echo "$JOB" >> "$TMP_CRON"
crontab "$TMP_CRON"

echo "Installed cron job:"
echo "$JOB"
