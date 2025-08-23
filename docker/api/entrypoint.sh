#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
until pg_isready -h db -p 5432 -U postgres; do
  echo "PostgreSQL not ready, waiting..."
  sleep 2
done

# Run Alembic migrations
echo "Running Alembic migrations..."
python3 -m alembic upgrade head

# Start Sanic service
echo "Starting Sanic service..."
exec python3 -OO /opt/wrolpi/main.py -v api --host 0.0.0.0
