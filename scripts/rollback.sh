#!/bin/bash
set -e

echo "=== ВашСад Rollback Script ==="
echo "Started at: $(date)"

echo ">>> Recent commits:"
git log --oneline -5

echo ""
read -p "Enter commit hash to rollback to: " COMMIT_HASH

if [ -z "$COMMIT_HASH" ]; then
    echo "No commit hash provided. Aborting."
    exit 1
fi

echo ">>> Rolling back to commit: $COMMIT_HASH"
git checkout "$COMMIT_HASH"

echo ">>> Restarting containers..."
docker compose up -d

echo ">>> Container status:"
docker compose ps

echo "=== Rollback completed at: $(date) ==="
echo "NOTE: You are now in detached HEAD state. To return to main: git checkout main"
