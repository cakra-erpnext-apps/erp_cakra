#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/apps/erp_cakra/erp_cakra"

cd "$PROJECT_DIR"

echo "== git status before =="
git status --short

echo "== git pull =="
git pull --ff-only

echo "== run prod-update-assets =="
./prod-update-assets.sh

echo "== git status after =="
git status --short

echo "DONE"
