#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/apps/erp_cakra/erp_cakra"
BACKEND="erp_cakra_prod-backend-1"
FRONTEND="erp_cakra_prod-frontend-1"
BENCH="/home/frappe/frappe-bench"

SITES=(
  "app.cakraindo.com"
  "app.oakglobalmaritim.com"
)

APP_DIRS=(
  "frappe"
  "erpnext"
  "hrms"
  "raven"
  "helpdesk"
  "gameplan"
  "crm_cakra"
  "assistant"
  "erpnext_custom"
  "erp"
  "telephony"
)

cd "$PROJECT_DIR"

echo "== build core =="
docker exec "$BACKEND" bash -lc "set -e; cd $BENCH && bench build --apps frappe,erpnext"

echo "== build hrms/raven =="
docker exec "$BACKEND" bash -lc "set -e; cd $BENCH && bench build --apps hrms,raven"

echo "== build helpdesk =="
docker exec "$BACKEND" bash -lc "set -e; cd $BENCH && bench build --apps helpdesk"

echo "== build gameplan =="
docker exec "$BACKEND" bash -lc "set -e; cd $BENCH && bench build --apps gameplan"

echo "== build crm_cakra =="
docker exec "$BACKEND" bash -lc "set -e; cd $BENCH && bench build --apps crm_cakra"

echo "== materialize assets for frontend nginx =="
docker exec "$BACKEND" bash -lc '
  set -euo pipefail
  cd /home/frappe/frappe-bench
  apps=(frappe erpnext hrms raven helpdesk gameplan crm_cakra assistant erpnext_custom erp telephony)
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
'

echo "== clear cache =="
for site in "${SITES[@]}"; do
  echo "clear $site"
  docker exec "$BACKEND" bash -lc "set -e; cd $BENCH && bench --site $site clear-cache && bench --site $site clear-website-cache"
done

echo "== restart frontend =="
docker restart "$FRONTEND" >/dev/null

echo "== current asset hashes =="
docker exec "$BACKEND" bash -lc '
  cd /home/frappe/frappe-bench
  python - <<PY
import json
j=json.load(open("sites/assets/assets.json"))
keys = [
  "desk.bundle.css",
  "report.bundle.css",
  "erpnext.bundle.css",
  "hrms.bundle.css",
  "raven.bundle.css",
  "desk.bundle.js",
  "erpnext.bundle.js",
  "hrms.bundle.js",
  "raven.bundle.js",
]
for k in keys:
  print(k, j.get(k, "MISSING"))
PY
'

echo "== http check =="
for host in "${SITES[@]}"; do
  echo "== $host =="
  for p in \
    /assets/frappe/dist/js/libs.bundle.IGBCIYI5.js \
    /assets/frappe/dist/js/desk.bundle.IFKKWSVC.js \
    /assets/frappe/dist/js/report.bundle.G6IX464W.js \
    /assets/erpnext/dist/js/erpnext.bundle.4LXW4GEH.js \
    /assets/assistant/js/assistant_tabs.js \
    /assets/frappe/icons/lucide/icons.svg \
    /assets/erpnext/icons/pos-icons.svg
  do
    curl -k -sS -o /dev/null -w "%{http_code} $p\n" "https://$host$p" --max-time 20
  done
done

echo "DONE"
