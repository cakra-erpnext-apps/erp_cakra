#!/usr/bin/env bash
set -euo pipefail

# Pencegahan brute force login. Idempotent, aman diulang.
#   ./harden-login.sh                    -> laporan + kencangkan penguncian
#   ./harden-login.sh user@contoh.com    -> plus nonaktifkan user itu
#
# Frappe sudah mengunci login gagal beruntun per-IP dan per-username
# (frappe/auth.py get_login_attempt_tracker). Skrip ini cuma mengencangkan
# setelannya, tidak menambah kode apa pun.

BACKEND="${BACKEND:-erp_oakglobal_prod-backend-1}"
SITE="${SITE:-app.oakglobalmaritim.com}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-5}"
LOCK_SECONDS="${LOCK_SECONDS:-300}"
DISABLE_USER="${1:-}"

docker ps --format '{{.Names}}' | grep -qx "$BACKEND" || {
  echo "container $BACKEND tidak jalan" >&2; exit 1; }

docker exec -i "$BACKEND" bash -lc "cd /home/frappe/frappe-bench && bench --site $SITE console" <<EOF
exec("""
import frappe

print("=== login gagal 7 hari terakhir (per IP + user) ===")
rows = frappe.db.sql('''
    SELECT ip_address, user, COUNT(*) c, MAX(creation) terakhir
    FROM \`tabActivity Log\`
    WHERE status='Failed' AND creation > NOW() - INTERVAL 7 DAY
    GROUP BY ip_address, user ORDER BY c DESC LIMIT 25
''')
for r in rows:
    print(f"  {r[0] or '-':<18} {r[1] or '-':<35} {r[2]:>4}x  {r[3]}")
if not rows:
    print("  (bersih)")

print()
print("=== user aktif yang tidak pernah / lama tidak login ===")
stale = frappe.db.sql('''
    SELECT name, last_login FROM tabUser
    WHERE enabled=1 AND user_type='System User' AND name NOT IN ('Administrator','Guest')
      AND (last_login IS NULL OR last_login < NOW() - INTERVAL 90 DAY)
    ORDER BY last_login IS NOT NULL, last_login LIMIT 40
''')
for r in stale:
    print(f"  {r[0]:<40} {r[1] or 'BELUM PERNAH'}")
if not stale:
    print("  (tidak ada)")

print()
ss = frappe.get_doc("System Settings")
print(f"=== penguncian: {ss.allow_consecutive_login_attempts} percobaan / {ss.allow_login_after_fail} detik ===")
ss.allow_consecutive_login_attempts = $MAX_ATTEMPTS
ss.allow_login_after_fail = $LOCK_SECONDS
ss.save()
print(f"    -> jadi {ss.allow_consecutive_login_attempts} percobaan / {ss.allow_login_after_fail} detik")

target = "$DISABLE_USER"
if target:
    if not frappe.db.exists("User", target):
        print(f"!!  user {target} tidak ada")
    else:
        u = frappe.get_doc("User", target)
        u.enabled = 0
        u.save(ignore_permissions=True)
        frappe.db.sql("DELETE FROM tabSessions WHERE user=%s", target)
        print(f"    user {target} dinonaktifkan + sesinya dihapus")

frappe.db.commit()
""")
EOF
