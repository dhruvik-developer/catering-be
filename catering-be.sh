#!/bin/bash
# Single PM2 entry that supervises BOTH server processes:
#   - Gunicorn on $GUNICORN_BIND  → handles /api/*  (sync WSGI)
#   - Daphne   on $DAPHNE_BIND:$DAPHNE_PORT → handles /ws/* (async ASGI)
#
# Both run as children of this script. If either dies the script exits and
# PM2 restarts everything together. SIGTERM from PM2 is propagated to both
# children via the trap below so shutdowns are clean.
#
# Nginx still routes by path:
#   location /ws/  →  proxy_pass http://127.0.0.1:8010;
#   location /     →  proxy_pass http://127.0.0.1:8009;

set -e

APP_DIR="${APP_DIR:-/root/catering-be}"
VENV_PATH="${VENV_PATH:-.venv/bin/activate}"

# Gunicorn (REST)
GUNICORN_BIND="${GUNICORN_BIND:-127.0.0.1:8009}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-800}"
GUNICORN_GRACEFUL_TIMEOUT="${GUNICORN_GRACEFUL_TIMEOUT:-80}"

# Daphne (WebSockets)
DAPHNE_BIND="${DAPHNE_BIND:-127.0.0.1}"
DAPHNE_PORT="${DAPHNE_PORT:-8010}"
DAPHNE_PROXY_HEADERS="${DAPHNE_PROXY_HEADERS:-true}"

AUTO_INSTALL_SUBSCRIPTION_CRON="${AUTO_INSTALL_SUBSCRIPTION_CRON:-true}"

cd "$APP_DIR"

# Activate virtual environment
if [ -f "$VENV_PATH" ]; then
  source "$VENV_PATH"
fi

# Ensure the daily subscription status job exists whenever PM2 starts/restarts
# this app. The installer is idempotent and replaces only its own cron line.
if [ "$AUTO_INSTALL_SUBSCRIPTION_CRON" = "true" ]; then
  if [ -f "$APP_DIR/scripts/install_subscription_status_cron.sh" ]; then
    echo "Installing subscription status cron..."
    if ! APP_DIR="$APP_DIR" VENV_PATH="$VENV_PATH" bash "$APP_DIR/scripts/install_subscription_status_cron.sh"; then
      echo "WARNING: Subscription status cron could not be installed. App startup will continue."
    fi
  else
    echo "WARNING: Subscription cron installer not found at $APP_DIR/scripts/install_subscription_status_cron.sh"
  fi
fi

# Run Django tenant-aware migrations. This keeps shared/public tables and all
# tenant schemas in sync when PM2 restarts after a deploy.
echo "Running shared schema migrations..."
python manage.py migrate_schemas --shared --noinput

echo "Running tenant schema migrations..."
python manage.py migrate_schemas --tenant --noinput

echo "Repairing tenant JWT blacklist tables..."
python manage.py repair_token_blacklist_tables

# Optional (recommended): collect static
# echo "Collecting static files..."
# python manage.py collectstatic --noinput

# ───────────────────── Process supervision ─────────────────────

GUNICORN_PID=""
DAPHNE_PID=""

cleanup() {
  # Forward shutdown to both children. `|| true` so we don't blow up if one
  # already exited and the kill returns non-zero.
  echo "Shutting down child processes..."
  if [ -n "$DAPHNE_PID" ]; then
    kill -TERM "$DAPHNE_PID" 2>/dev/null || true
  fi
  if [ -n "$GUNICORN_PID" ]; then
    kill -TERM "$GUNICORN_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}
trap cleanup SIGTERM SIGINT

# Daphne first so the channel layer is ready before any client lands.
PROXY_FLAG=""
if [ "$DAPHNE_PROXY_HEADERS" = "true" ]; then
  PROXY_FLAG="--proxy-headers"
fi

echo "Starting Daphne on ${DAPHNE_BIND}:${DAPHNE_PORT}..."
daphne \
  -b "$DAPHNE_BIND" \
  -p "$DAPHNE_PORT" \
  $PROXY_FLAG \
  radha.asgi:application &
DAPHNE_PID=$!

echo "Starting Gunicorn on ${GUNICORN_BIND}..."
gunicorn radha.wsgi:application \
  --bind "$GUNICORN_BIND" \
  --timeout "$GUNICORN_TIMEOUT" \
  --graceful-timeout "$GUNICORN_GRACEFUL_TIMEOUT" &
GUNICORN_PID=$!

echo "catering-be supervisor running. gunicorn=$GUNICORN_PID daphne=$DAPHNE_PID"

# Block until ANY child exits, then bring the other one down too and let PM2
# restart the whole thing together. `wait -n` requires bash >= 4.3 (fine on
# every modern Ubuntu).
set +e
wait -n
EXIT_CODE=$?
echo "A child process exited (status=$EXIT_CODE). Stopping the other..."
cleanup
exit "$EXIT_CODE"
