#!/bin/bash
set -e

echo "=== ВашСад Deploy Script ==="
echo "Started at: $(date)"

# 1. Pull latest code
echo ">>> Pulling latest code..."
git pull origin main

# 2. Run pre-deploy check
echo ">>> Running pre-deploy checks..."
python scripts/pre_deploy_check.py || { echo "Pre-deploy check failed!"; exit 1; }

# 3. Run DB migrations
echo ">>> Running database migrations..."
python scripts/migrate.py

# 4. Build and restart docker containers
echo ">>> Building Docker images..."
docker compose build --no-cache

echo ">>> Stopping old containers..."
docker compose down

echo ">>> Starting new containers..."
docker compose up -d

# 5. Wait and health check
echo ">>> Waiting for bot to start..."
sleep 5
docker compose ps

echo ">>> Checking health..."
curl -sf http://localhost:3000/api/health && echo "Health check OK" || echo "Health check failed (miniapp may not be running here)"

echo "=== Deploy completed at: $(date) ==="
