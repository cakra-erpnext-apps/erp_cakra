#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/apps/erp_cakra/erp_cakra"
BACKEND="erp_cakra_prod-backend-1"
FRONTEND="erp_cakra_prod-frontend-1"
WEBSOCKET="erp_cakra_prod-websocket-1"
QUEUE_SHORT="erp_cakra_prod-queue-short-1"
QUEUE_LONG="erp_cakra_prod-queue-long-1"
SCHEDULER="erp_cakra_prod-scheduler-1"
BENCH="/home/frappe/frappe-bench"
SITES=(
  "app.cakraindo.com"
  "app.oakglobalmaritim.com"
)

log() { echo "== $* =="; }

cd "$PROJECT_DIR"

log "git status before"
git status --short

log "git pull"
git pull --ff-only

log "backup sites"
for site in "${SITES[@]}"; do
  echo "backup $site"
  docker exec "$BACKEND" bash -lc "set -e; cd $BENCH && bench --site $site backup"
done

log "migrate sites"
for site in "${SITES[@]}"; do
  echo "migrate $site"
  docker exec "$BACKEND" bash -lc "set -e; cd $BENCH && bench --site $site migrate"
done

log "build and materialize assets"
./prod-update-assets.sh

log "clear cache sites"
for site in "${SITES[@]}"; do
  echo "clear $site"
  docker exec "$BACKEND" bash -lc "set -e; cd $BENCH && bench --site $site clear-cache && bench --site $site clear-website-cache"
done

log "restart app services"
docker restart \
  "$BACKEND" \
  "$WEBSOCKET" \
  "$QUEUE_SHORT" \
  "$QUEUE_LONG" \
  "$SCHEDULER" \
  "$FRONTEND" >/dev/null

log "verify doctypes"
docker exec "$BACKEND" bash -lc "cd $BENCH && bench --site app.cakraindo.com mariadb -e \"select name,module from tabDocType where name=\\\"CRM Inquiry\\\";\""

log "http check"
for host in "${SITES[@]}"; do
  echo "== $host =="
  curl -k -sS -o /dev/null -w "login=%{http_code}\n" "https://$host/login" --max-time 20
  curl -k -sS -o /dev/null -w "frappe_icon=%{http_code}\n" "https://$host/assets/frappe/icons/timeless/icons.svg" --max-time 20
done

log "git status after"
git status --short

log "DONE"
