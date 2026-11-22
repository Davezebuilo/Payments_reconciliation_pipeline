#!/usr/bin/env bash
# Prepare Superset's own database, make sure the admin user exists, then start the web server.
# Every step is safe to repeat, so this runs on every start.
set -e

superset db upgrade
superset fab create-admin \
    --username admin --firstname Admin --lastname User --email admin@localhost \
    --password "$SUPERSET_ADMIN_PASSWORD" || true   # fails harmlessly if admin already exists
superset init

exec /usr/bin/run-server.sh