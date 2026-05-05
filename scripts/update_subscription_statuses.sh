#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/catering-be}"
VENV_PATH="${VENV_PATH:-$APP_DIR/.venv/bin/activate}"
LOG_DIR="${LOG_DIR:-$APP_DIR/logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/update_subscription_statuses.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/radha-update-subscription-statuses.lock}"

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

exec >> "$LOG_FILE" 2>&1

echo "[$(date -Is)] Starting subscription status update"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
  echo "[$(date -Is)] Previous subscription status update is still running; skipping."
  exit 0
fi

if [ -f "$VENV_PATH" ]; then
  # shellcheck disable=SC1090
  source "$VENV_PATH"
fi

python manage.py update_subscription_statuses "$@"

echo "[$(date -Is)] Finished subscription status update"
