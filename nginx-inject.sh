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

echo "[nginx-inject] Starting nginx..."
exec nginx -g 'daemon off;'