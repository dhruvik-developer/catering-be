#!/bin/bash
set -e

APP_DIR="${APP_DIR:-/root/radha-be}"
VENV_PATH="${VENV_PATH:-.venv/bin/activate}"
GUNICORN_BIND="${GUNICORN_BIND:-127.0.0.1:8006}"

cd "$APP_DIR"

# Activate virtual environment
if [ -f "$VENV_PATH" ]; then
  source "$VENV_PATH"
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