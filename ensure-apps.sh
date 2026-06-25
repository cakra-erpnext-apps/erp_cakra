#!/bin/bash
# Boot wrapper: pastikan custom app (bind-mounted) ter-install di env container INI
# setiap kali container start. Bikin `docker compose up` (recreate) AMAN walau folder
# `env` tidak dipersist sebagai volume (image hanya bake crm). Dipanggil sebagai
# command tiap app-service di compose, lalu exec command aslinya ("$@").
BENCH=/home/frappe/frappe-bench
cd "$BENCH" || exit 1

for app in erp erpnext_custom agents; do
  if [ -d "apps/$app" ]; then
    env/bin/python -c "import $app" 2>/dev/null \
      || { echo "[ensure-apps] installing $app..."; env/bin/pip install -e "apps/$app" --no-deps -q 2>/dev/null; }
  fi
done

# Runtime deps yang dipakai app custom (di-skip oleh --no-deps di atas).
env/bin/python -c "import pypdfium2" 2>/dev/null \
  || { echo "[ensure-apps] installing pypdfium2..."; env/bin/pip install pypdfium2 -q 2>/dev/null; }

# apps.txt: configurator me-reset ke frappe/erpnext/crm — tambahkan app custom kembali.
if [ -f sites/apps.txt ]; then
  for app in erp erpnext_custom agents; do
    if [ -d "apps/$app" ] && ! grep -qx "$app" sites/apps.txt; then echo "$app" >> sites/apps.txt; fi
  done
fi

exec "$@"
