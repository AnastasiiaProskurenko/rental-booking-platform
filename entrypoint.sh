#!/bin/sh
set -e

echo "Apply migrations..."
python manage.py migrate --noinput

echo "Collect static..."
python manage.py collectstatic --noinput || true

echo "Start gunicorn..."
exec gunicorn rental_projekt_final.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 120
