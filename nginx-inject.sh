#!/bin/bash
set -e

export BACKEND=${BACKEND:-0.0.0.0:8000}
export SOCKETIO=${SOCKETIO:-0.0.0.0:9000}
export UPSTREAM_REAL_IP_ADDRESS=${UPSTREAM_REAL_IP_ADDRESS:-127.0.0.1}
export UPSTREAM_REAL_IP_HEADER=${UPSTREAM_REAL_IP_HEADER:-X-Forwarded-For}
export UPSTREAM_REAL_IP_RECURSIVE=${UPSTREAM_REAL_IP_RECURSIVE:-off}
export FRAPPE_SITE_NAME_HEADER=${FRAPPE_SITE_NAME_HEADER:-\$host}
export PROXY_READ_TIMEOUT=${PROXY_READ_TIMEOUT:-120}
export CLIENT_MAX_BODY_SIZE=${CLIENT_MAX_BODY_SIZE:-50m}

echo "[nginx-inject] Generating frappe.conf from template..."
envsubst '${BACKEND} ${SOCKETIO} ${UPSTREAM_REAL_IP_ADDRESS} ${UPSTREAM_REAL_IP_HEADER} ${UPSTREAM_REAL_IP_RECURSIVE} ${FRAPPE_SITE_NAME_HEADER} ${PROXY_READ_TIMEOUT} ${CLIENT_MAX_BODY_SIZE}' \
  </templates/nginx/frappe.conf.template >/etc/nginx/conf.d/frappe.conf

echo "[nginx-inject] Injecting /crm/ route..."
if ! grep -q 'location /crm/' /etc/nginx/conf.d/frappe.conf; then
  python3 - <<'PYEOF'
with open('/etc/nginx/conf.d/frappe.conf', 'r') as f:
    content = f.read()

crm_block = """    location /crm/ {
        try_files $uri $uri/ /assets/crm/frontend/index.html;
    }

"""
content = content.replace('    location /assets {', crm_block + '    location /assets {', 1)

with open('/etc/nginx/conf.d/frappe.conf', 'w') as f:
    f.write(content)
print('[nginx-inject] CRM route injected.')
PYEOF
else
  echo "[nginx-inject] CRM route already exists."
fi

# Cache tile peta. Basemap gratis bisa sewaktu-waktu minta API key atau down
# (CARTO sudah begitu); dengan cache ini tile yang pernah dibuka tetap tersaji
# walau sumbernya bermasalah, dan trafik ke OSM turun drastis sehingga tidak
# melanggar tile usage policy mereka.
#
# Lewat nginx, bukan Frappe: satu layar peta = puluhan tile, kalau tiap tile
# masuk stack Python worker-nya habis.
echo "[nginx-inject] Setting up tile cache..."
TILE_CACHE=/home/frappe/frappe-bench/sites/tile-cache
mkdir -p "$TILE_CACHE"

cat >/etc/nginx/conf.d/00-tiles.conf <<CONFEOF
# Disimpan di volume sites supaya cache selamat dari restart container dan
# tetap milik user frappe (nginx di sini jalan sebagai frappe, bukan root).
# Bukan site: frappe hanya menganggap folder ber-site_config.json sebagai site.
proxy_cache_path $TILE_CACHE levels=1:2 keys_zone=tiles:10m max_size=2g inactive=90d use_temp_path=off;
CONFEOF

if ! grep -q 'location /tiles/' /etc/nginx/conf.d/frappe.conf; then
  python3 - <<'PYEOF2'
import re

with open('/etc/nginx/conf.d/frappe.conf', 'r') as f:
    content = f.read()

tiles_block = """    location /tiles/ {
        proxy_pass https://tile.openstreetmap.org/;
        proxy_set_header Host tile.openstreetmap.org;
        # OSM menolak User-Agent generik; sebutkan identitas aplikasi.
        proxy_set_header User-Agent "ERPCakra Fleet Map (cakraindo.it@gmail.com)";
        proxy_set_header Cookie "";
        proxy_ssl_server_name on;

        proxy_cache tiles;
        # OSM lewat Fastly mengirim Expires yang sudah lewat (umur cache mereka
        # sendiri); nginx menurutinya dan tidak pernah menyimpan apa pun.
        # Umur simpan di sini kebijakan kita, bukan mereka.
        proxy_ignore_headers Cache-Control Expires Set-Cookie Vary X-Accel-Expires;
        proxy_cache_key $uri;
        proxy_cache_valid 200 30d;
        proxy_cache_valid 404 1h;
        # Inti ketahanannya: sumber error/down -> sajikan tile lama, jangan blank.
        proxy_cache_use_stale error timeout updating http_429 http_500 http_502 http_503 http_504;
        proxy_cache_background_update on;
        # Satu tile diminta 10 browser sekaligus = satu permintaan ke luar.
        proxy_cache_lock on;
        proxy_hide_header Set-Cookie;
        add_header X-Tile-Cache $upstream_cache_status;
        expires 30d;
    }

"""
# Anchor dicari dengan regex: frappe.conf memakai tab, bukan spasi -- pencarian
# string polos gagal diam-diam dan blok tidak pernah masuk.
m = re.search(r'^[ 	]*location /assets', content, re.M)
if not m:
    raise SystemExit('[nginx-inject] anchor "location /assets" tidak ketemu')
content = content[: m.start()] + tiles_block + content[m.start() :]

with open('/etc/nginx/conf.d/frappe.conf', 'w') as f:
    f.write(content)
print('[nginx-inject] Tile cache route injected.')
PYEOF2
else
  echo "[nginx-inject] Tile cache route already exists."
fi

echo "[nginx-inject] Starting nginx..."
exec nginx -g 'daemon off;'