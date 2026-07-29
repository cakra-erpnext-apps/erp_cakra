#!/usr/bin/env bash
set -euo pipefail

# Generated after stack split. Do not use old multi-site updater for split stacks.
PROJECT_DIR="/home/apps/erp_oakglobal/erp_oakglobal"
BACKEND="erp_oakglobal_prod-backend-1"
FRONTEND="erp_oakglobal_prod-frontend-1"
WEBSOCKET="erp_oakglobal_prod-websocket-1"
QUEUE_SHORT="erp_oakglobal_prod-queue-short-1"
QUEUE_DEFAULT="erp_oakglobal_prod-queue-default-1"
QUEUE_LONG="erp_oakglobal_prod-queue-long-1"
SCHEDULER="erp_oakglobal_prod-scheduler-1"
SITE="app.oakglobalmaritim.com"
PUBLIC_URL="https://app.oakglobalmaritim.com"
BENCH="/home/frappe/frappe-bench"

log() { echo "== $* =="; }
run_bench() { docker exec "$BACKEND" bash -lc "set -e; cd $BENCH && $*"; }

cd "$PROJECT_DIR"

log "precheck"
docker ps --format '{{.Names}}' | grep -qx "$BACKEND"
docker ps --format '{{.Names}}' | grep -qx "$FRONTEND"
run_bench "bench --site $SITE list-apps >/tmp/${SITE}.apps && tail -20 /tmp/${SITE}.apps"

log "git status before"
git status --short

log "backup $SITE"
run_bench "bench --site $SITE backup"

log "git pull"
git pull --ff-only

log "migrate $SITE"
run_bench "bench --site $SITE migrate"

log "fix assets ownership"
docker exec -u root "$BACKEND" bash -lc "chown -R frappe:frappe /home/frappe/frappe-bench/sites/assets"

log "build assets"
# Keep build sequential; bench build has a global lock.
# Oakglobal has 11 installed apps; build all so hashes/routes stay consistent after updates.
BUILD_APPS=(
  frappe
  erpnext
  hrms
  telephony
  helpdesk
  raven
  gameplan
  erpnext_custom
  erp
  assistant
  crm_cakra
)
run_bench "bench build --apps frappe,erpnext"
run_bench "bench build --apps hrms"
run_bench "bench build --apps helpdesk,raven"
run_bench "bench build --apps gameplan"
# erpnext_custom/erp/assistant/telephony have no root package.json; do not pass them to bench build.
# Their public js/css is handled by materialization below.
# ensure crm_cakra frontend deps (vite) exist; copy from cakra stack if missing
docker exec "$BACKEND" bash -lc "test -x /home/frappe/frappe-bench/apps/crm_cakra/frontend/node_modules/.bin/vite" || {
  echo "crm_cakra frontend deps missing; copying from cakra stack"
  rm -rf /tmp/crm_fe_nm
  docker cp erp_cakra_prod-backend-1:/home/frappe/frappe-bench/apps/crm_cakra/frontend/node_modules /tmp/crm_fe_nm
  docker exec "$BACKEND" bash -lc "rm -rf /home/frappe/frappe-bench/apps/crm_cakra/frontend/node_modules"
  docker cp /tmp/crm_fe_nm "$BACKEND":/home/frappe/frappe-bench/apps/crm_cakra/frontend/node_modules
  docker exec -u root "$BACKEND" bash -lc "chown -R frappe:frappe /home/frappe/frappe-bench/apps/crm_cakra/frontend/node_modules"
  rm -rf /tmp/crm_fe_nm
}
run_bench "bench build --apps crm_cakra"

log "materialize public assets for frontend nginx"
docker exec "$BACKEND" bash -lc '
  set -euo pipefail
  cd /home/frappe/frappe-bench
  apps=(frappe erpnext hrms telephony helpdesk raven gameplan erpnext_custom erp assistant crm_cakra)
  for app in "${apps[@]}"; do
    src="apps/$app/$app/public"
    [ -d "$src" ] || src="apps/$app/public"
    if [ -d "$src" ]; then
      echo "materialize $app <- $src"
      rm -rf "sites/assets/$app"
      mkdir -p "sites/assets/$app"
      cp -a "$src/." "sites/assets/$app/"
    else
      echo "skip $app: no public dir"
    fi
  done
  test -f sites/assets/assets.json
'

log "clear cache $SITE"
run_bench "bench --site $SITE clear-cache && bench --site $SITE clear-website-cache"

log "restart app services"
docker restart \
  "$BACKEND" \
  "$WEBSOCKET" \
  "$QUEUE_SHORT" \
  "$QUEUE_DEFAULT" \
  "$QUEUE_LONG" \
  "$SCHEDULER" \
  "$FRONTEND" >/dev/null

log "wait backend"
sleep 20

docker ps --filter name="$BACKEND" --format '{{.Status}}'

log "verify HTTP"
curl -k -sS -o /dev/null -w "login=%{http_code}\n" "$PUBLIC_URL/login" --max-time 20
curl -k -sS -o /dev/null -w "ping=%{http_code}\n" "$PUBLIC_URL/api/method/ping" --max-time 20
curl -k -sS -o /dev/null -w "frappe_icon=%{http_code}\n" "$PUBLIC_URL/assets/frappe/icons/timeless/icons.svg" --max-time 20

log "git status after"
git status --short

log "DONE $SITE"
