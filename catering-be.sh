#!/bin/bash
set -e

APP_DIR="${APP_DIR:-/root/catering-be}"
VENV_PATH="${VENV_PATH:-.venv/bin/activate}"
GUNICORN_BIND="${GUNICORN_BIND:-127.0.0.1:8009}"
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

# Run Django migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Optional (recommended): collect static
# echo "Collecting static files..."
# python manage.py collectstatic --noinput

# Start Gunicorn
echo "Starting Gunicorn..."
exec gunicorn radha.wsgi:application --bind "$GUNICORN_BIND"
