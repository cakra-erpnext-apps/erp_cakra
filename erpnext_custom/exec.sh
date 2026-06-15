#!/bin/bash

# =============================================================
#  Frappe / ERPNext — Module Structure Generator
#  Usage: bash create_module.sh
# =============================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Frappe Module Structure Generator      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── Input ─────────────────────────────────────────────────────
REPO_NAME="apps"

read -p "Nama modul  : " MODULE_NAME
[[ -z "$MODULE_NAME" ]] && echo -e "${RED}Error: nama modul kosong.${NC}" && exit 1

MODULE_SNAKE=$(echo "$MODULE_NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '_')

echo ""
echo -e "${YELLOW}Mau buat apa di modul '${MODULE_SNAKE}'?${NC}"
echo "  1) customize saja"
echo "  2) new saja"
echo "  3) keduanya (customize + new)"
read -p "Pilih [1/2/3]: " MODE
[[ "$MODE" != "1" && "$MODE" != "2" && "$MODE" != "3" ]] && echo -e "${RED}Pilihan tidak valid.${NC}" && exit 1

OVERRIDES=()
if [[ "$MODE" == "1" || "$MODE" == "3" ]]; then
  echo ""
  echo -e "${CYAN}Menu yang mau di-customize${NC} (pisahkan koma, contoh: Quotation,Sales Order)"
  read -p "> " OVERRIDE_INPUT
  IFS=',' read -ra OVERRIDES <<< "$OVERRIDE_INPUT"
fi

DOCTYPES=()
if [[ "$MODE" == "2" || "$MODE" == "3" ]]; then
  echo ""
  echo -e "${CYAN}Menu yang akan dibuat baru?${NC} (pisahkan koma, contoh: Isotank,Stacking)"
  read -p "> " DOCTYPE_INPUT
  IFS=',' read -ra DOCTYPES <<< "$DOCTYPE_INPUT"
fi

echo ""
read -p "Tambah API? [y/n]: " ADD_API

echo ""
echo -e "${YELLOW}Membuat struktur...${NC}"
echo ""

# ── Helper ────────────────────────────────────────────────────
BASE="${REPO_NAME}/${MODULE_SNAKE}"
mk() { mkdir -p "$(dirname "$1")"; touch "$1"; }
mf() { mkdir -p "$(dirname "$1")"; cat > "$1"; }

# ═══════════════════════════════════════════════════════════════
# ROOT REPO
# ═══════════════════════════════════════════════════════════════
mkdir -p "$BASE"

mf "${REPO_NAME}/.gitignore" << 'EOF'
__pycache__/
*.pyc
*.pyo
.DS_Store
node_modules/
*.egg-info/
dist/
.env
EOF

mf "${REPO_NAME}/setup.py" << EOF
from setuptools import setup, find_packages

setup(
    name="${REPO_NAME}",
    version="0.0.1",
    description="Custom Frappe App",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=[]
)
EOF

mk "${BASE}/__init__.py"
mk "${BASE}/patches.txt"
echo "${MODULE_NAME}" > "${REPO_NAME}/modules.txt"

# ═══════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════
HOOKS_API=""

if [[ "$ADD_API" == "y" || "$ADD_API" == "Y" ]]; then
  mf "${BASE}/api.py" << EOF
import frappe


# ─────────────────────────────────────────────────────────────
# Semua endpoint di bawah wajib pakai API key (secret key)
#
# Cara akses:
#   GET /api/method/${REPO_NAME}.${MODULE_SNAKE}.api.<function_name>
#   Header: Authorization: token <api_key>:<api_secret>
#
# Generate key:
#   ERPNext → User → [pilih user] → API Access → Generate Keys
# ─────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_list(doctype, fields=None, filters=None, limit=20):
    """
    Ambil list dokumen.

    Contoh:
      GET /api/method/${REPO_NAME}.${MODULE_SNAKE}.api.get_list?doctype=Isotank
    """
    import json
    _fields = json.loads(fields) if isinstance(fields, str) else (fields or ["name", "title"])
    _filters = json.loads(filters) if isinstance(filters, str) else (filters or {})

    return frappe.get_list(
        doctype,
        fields=_fields,
        filters=_filters,
        order_by="creation desc",
        limit=int(limit)
    )


@frappe.whitelist()
def get_detail(doctype, name):
    """
    Ambil satu dokumen.

    Contoh:
      GET /api/method/${REPO_NAME}.${MODULE_SNAKE}.api.get_detail?doctype=Isotank&name=ISO-0001
    """
    return frappe.get_doc(doctype, name)


@frappe.whitelist()
def create(doctype, data):
    """
    Buat dokumen baru.

    Contoh body:
      POST /api/method/${REPO_NAME}.${MODULE_SNAKE}.api.create
      { "doctype": "Isotank", "data": "{\"title\": \"ISO-001\"}" }
    """
    import json
    payload = json.loads(data) if isinstance(data, str) else data
    doc = frappe.get_doc({"doctype": doctype, **payload})
    doc.insert(ignore_permissions=False)
    frappe.db.commit()
    return {"name": doc.name, "status": "created"}


@frappe.whitelist()
def update(doctype, name, data):
    """
    Update dokumen yang sudah ada.
    """
    import json
    payload = json.loads(data) if isinstance(data, str) else data
    doc = frappe.get_doc(doctype, name)
    doc.update(payload)
    doc.save(ignore_permissions=False)
    frappe.db.commit()
    return {"name": doc.name, "status": "updated"}


@frappe.whitelist()
def delete(doctype, name):
    """
    Hapus dokumen.
    """
    frappe.delete_doc(doctype, name, ignore_permissions=False)
    frappe.db.commit()
    return {"name": name, "status": "deleted"}


# ─────────────────────────────────────────────────────────────
# Endpoint publik — tanpa login, tanpa API key
# ─────────────────────────────────────────────────────────────
@frappe.whitelist(allow_guest=True)
def status():
    """Health check. GET /api/method/${REPO_NAME}.${MODULE_SNAKE}.api.status"""
    return {"status": "ok", "app": "${REPO_NAME}", "module": "${MODULE_NAME}"}
EOF

  HOOKS_API="# API: /api/method/${REPO_NAME}.${MODULE_SNAKE}.api.<function_name>"
  echo -e "${GREEN}  ✓ api.py${NC}"
fi

# ═══════════════════════════════════════════════════════════════
# CUSTOMIZE
# ═══════════════════════════════════════════════════════════════
HOOKS_OVERRIDE_CLASS=""
HOOKS_DOCTYPE_JS=""
HOOKS_FIXTURES=""

if [[ "$MODE" == "1" || "$MODE" == "3" ]]; then
  mkdir -p "${BASE}/customize/overrides"
  mkdir -p "${BASE}/customize/fixtures"
  mkdir -p "${BASE}/customize/public/js"
  mkdir -p "${BASE}/customize/public/css"

  mk "${BASE}/customize/__init__.py"
  mk "${BASE}/customize/overrides/__init__.py"

  echo "[]" > "${BASE}/customize/fixtures/custom_field.json"
  echo "[]" > "${BASE}/customize/fixtures/property_setter.json"

  mf "${BASE}/customize/public/css/custom.css" << EOF
/* Custom styling — ${MODULE_NAME} */
EOF

  OVERRIDE_LIST=""
  DOCTYPE_JS_LIST=""
  FIXTURE_DT_LIST=""

  for RAW in "${OVERRIDES[@]}"; do
    DT=$(echo "$RAW" | xargs)
    [[ -z "$DT" ]] && continue
    SNAKE=$(echo "$DT" | tr '[:upper:]' '[:lower:]' | tr ' ' '_')
    CLASS=$(echo "$DT" | tr -d ' ')

    mf "${BASE}/customize/overrides/${SNAKE}.py" << EOF
import frappe
from frappe.model.document import Document


def get_base_class(doctype_name):
    """Ambil base class asli dari ERPNext secara dinamis."""
    import importlib, re
    snake = re.sub(r'(?<!^)(?=[A-Z])', '_', doctype_name).lower().replace(' ', '_')
    module_path = f"erpnext.selling.doctype.{snake}.{snake}"
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, doctype_name.replace(' ', ''))
    except Exception:
        return Document


Base = get_base_class("${DT}")


class Custom${CLASS}(Base):

    def validate(self):
        super().validate()
        self.custom_validate()

    def on_submit(self):
        super().on_submit()

    def custom_validate(self):
        # Tambahkan validasi custom di sini
        pass
EOF

    mf "${BASE}/customize/public/js/${SNAKE}.js" << EOF
frappe.ui.form.on('${DT}', {

    refresh(frm) {
        // Tambah tombol, hide/show field, dll
    },

    // Contoh: jalankan saat field diubah
    // nama_field(frm) {
    //     frm.set_value('field_lain', frm.doc.nama_field);
    // }
});
EOF

    OVERRIDE_LIST+="    \"${DT}\": \"${REPO_NAME}.${MODULE_SNAKE}.customize.overrides.${SNAKE}.Custom${CLASS}\",\n"
    DOCTYPE_JS_LIST+="    \"${DT}\": \"${MODULE_SNAKE}/customize/public/js/${SNAKE}.js\",\n"
    FIXTURE_DT_LIST+="\"${DT}\", "

    echo -e "${GREEN}  ✓ override: ${DT}${NC}"
  done

  HOOKS_OVERRIDE_CLASS="override_doctype_class = {\n${OVERRIDE_LIST}}\n"
  HOOKS_DOCTYPE_JS="doctype_js = {\n${DOCTYPE_JS_LIST}}\n"

  if [[ -n "$FIXTURE_DT_LIST" ]]; then
    FIXTURE_DT_LIST="${FIXTURE_DT_LIST%, }"
    HOOKS_FIXTURES="fixtures = [
    {\"doctype\": \"Custom Field\",    \"filters\": [[\"dt\", \"in\", [${FIXTURE_DT_LIST}]]]},
    {\"doctype\": \"Property Setter\", \"filters\": [[\"doc_type\", \"in\", [${FIXTURE_DT_LIST}]]]},
    {\"doctype\": \"Workspace\",       \"filters\": [[\"module\", \"=\", \"${MODULE_NAME}\"]]},
]\n"
  fi
fi

# ═══════════════════════════════════════════════════════════════
# NEW
# ═══════════════════════════════════════════════════════════════
if [[ "$MODE" == "2" || "$MODE" == "3" ]]; then
  mkdir -p "${BASE}/new/config"
  mkdir -p "${BASE}/new/doctype"
  mkdir -p "${BASE}/new/public/js"
  mkdir -p "${BASE}/new/public/css"

  mk "${BASE}/new/__init__.py"
  mk "${BASE}/new/config/__init__.py"
  mk "${BASE}/new/doctype/__init__.py"

  # Susun items desktop.py dengan idx berurutan
  DESKTOP_ITEMS=""
  IDX=1
  for RAW in "${DOCTYPES[@]}"; do
    DT=$(echo "$RAW" | xargs)
    [[ -z "$DT" ]] && continue
    DESKTOP_ITEMS+="                {\"type\": \"doctype\", \"name\": \"${DT}\", \"label\": _(\"${DT}\"), \"onboard\": 1, \"idx\": ${IDX}},\n"
    IDX=$((IDX + 1))
  done

  mf "${BASE}/new/config/desktop.py" << EOF
from frappe import _


def get_data():
    return [
        {
            "module_name": "${MODULE_NAME}",
            "color": "#4CAF50",
            "icon": "octicon octicon-file-directory",
            "type": "module",
            "label": _("${MODULE_NAME}"),
            "items": [
                # idx menentukan urutan menu di sidebar — ubah angkanya untuk reorder
$(echo -e "$DESKTOP_ITEMS")
            ]
        }
    ]
EOF

  for RAW in "${DOCTYPES[@]}"; do
    DT=$(echo "$RAW" | xargs)
    [[ -z "$DT" ]] && continue
    SNAKE=$(echo "$DT" | tr '[:upper:]' '[:lower:]' | tr ' ' '_')
    CLASS=$(echo "$DT" | tr -d ' ')

    mkdir -p "${BASE}/new/doctype/${SNAKE}"
    mk "${BASE}/new/doctype/${SNAKE}/__init__.py"

    mf "${BASE}/new/doctype/${SNAKE}/${SNAKE}.json" << EOF
{
 "name": "${DT}",
 "module": "${MODULE_NAME}",
 "doctype": "DocType",
 "is_submittable": 0,
 "fields": [
  {"fieldname": "title", "fieldtype": "Data",  "label": "Title", "reqd": 1, "in_list_view": 1},
  {"fieldname": "date",  "fieldtype": "Date",  "label": "Date"},
  {"fieldname": "notes", "fieldtype": "Text",  "label": "Notes"}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
 ]
}
EOF

    mf "${BASE}/new/doctype/${SNAKE}/${SNAKE}.py" << EOF
import frappe
from frappe.model.document import Document


class ${CLASS}(Document):

    def validate(self):
        pass

    def on_submit(self):
        frappe.msgprint(f"${DT} {self.name} submitted.")

    def on_cancel(self):
        pass
EOF

    mf "${BASE}/new/doctype/${SNAKE}/${SNAKE}.js" << EOF
frappe.ui.form.on('${DT}', {

    refresh(frm) {
        // logic saat form dibuka
    },

    onload(frm) {
        // logic saat form pertama load
    }
});
EOF

    mf "${BASE}/new/doctype/${SNAKE}/test_${SNAKE}.py" << EOF
import frappe
import unittest


class Test${CLASS}(unittest.TestCase):

    def test_create(self):
        doc = frappe.get_doc({"doctype": "${DT}", "title": "Test"})
        doc.insert()
        self.assertEqual(doc.title, "Test")
        doc.delete()
EOF

    echo -e "${GREEN}  ✓ doctype baru: ${DT}${NC}"
  done
fi

# ═══════════════════════════════════════════════════════════════
# hooks.py
# ═══════════════════════════════════════════════════════════════
mf "${BASE}/hooks.py" << EOF
app_name        = "${REPO_NAME}"
app_title       = "${REPO_NAME}"
app_publisher   = ""
app_description = "Custom Frappe App — ${MODULE_NAME}"
app_version     = "0.0.1"
app_email       = ""
app_license     = "MIT"

$(echo -e "$HOOKS_OVERRIDE_CLASS")
$(echo -e "$HOOKS_DOCTYPE_JS")
$(echo -e "$HOOKS_FIXTURES")
app_include_css = "/assets/${REPO_NAME}/${MODULE_SNAKE}/customize/css/custom.css"

scheduler_events = {
    # "daily": ["${REPO_NAME}.${MODULE_SNAKE}.tasks.daily_task"],
}

${HOOKS_API}
EOF

# ═══════════════════════════════════════════════════════════════
# README
# ═══════════════════════════════════════════════════════════════
mf "${REPO_NAME}/README.md" << EOF
# ${REPO_NAME}

Custom Frappe / ERPNext App — modul **${MODULE_NAME}**.

---

## Install

\`\`\`bash
bench get-app https://github.com/username/${REPO_NAME}.git
bench --site nama_site install-app ${REPO_NAME}
bench --site nama_site migrate
bench restart
\`\`\`

---

## Struktur Folder

\`\`\`
${REPO_NAME}/
└── ${MODULE_SNAKE}/
    ├── hooks.py              ← pusat config: daftarkan override, JS, fixtures, scheduler
    ├── patches.txt           ← daftar migration script
    ├── api.py                ← API endpoint (jika diaktifkan)
    │
    ├── customize/            ← override modul bawaan ERPNext (tidak menyentuh file ERPNext)
    │   ├── overrides/        ← extend class Python (validate, submit, cancel)
    │   ├── fixtures/         ← custom field & property setter dalam JSON (untuk Git)
    │   └── public/
    │       ├── js/           ← tambah tombol, hide/show field, event handler per DocType
    │       └── css/          ← styling tambahan
    │
    └── new/                  ← DocType & modul baru dari nol
        ├── config/
        │   └── desktop.py   ← daftarkan modul + urutan menu sidebar (via idx)
        ├── public/
        │   ├── js/
        │   └── css/
        └── doctype/
            └── nama_doctype/
                ├── nama_doctype.json   ← definisi field & form
                ├── nama_doctype.py     ← logic Python
                ├── nama_doctype.js     ← logic JavaScript (UI)
                └── test_*.py           ← unit test
\`\`\`

---

## Urutan Menu Sidebar

Diatur lewat \`idx\` di \`new/config/desktop.py\`:

\`\`\`python
"items": [
    {"name": "Isotank",  "idx": 1},   # muncul pertama
    {"name": "Stacking", "idx": 2},   # muncul kedua
]
\`\`\`

Tukar nilai \`idx\` untuk reorder → \`bench restart\`.

---

## API (Secret Key)

Semua endpoint wajib pakai API key kecuali \`/status\`.

**Generate key:** ERPNext → User → API Access → Generate Keys

**Format header:**
\`\`\`
Authorization: token <api_key>:<api_secret>
\`\`\`

**Endpoint tersedia:**

| Method | Endpoint | Keterangan |
|--------|----------|------------|
| GET | \`/api/method/${REPO_NAME}.${MODULE_SNAKE}.api.get_list\` | Ambil list dokumen |
| GET | \`/api/method/${REPO_NAME}.${MODULE_SNAKE}.api.get_detail\` | Ambil satu dokumen |
| POST | \`/api/method/${REPO_NAME}.${MODULE_SNAKE}.api.create\` | Buat dokumen baru |
| POST | \`/api/method/${REPO_NAME}.${MODULE_SNAKE}.api.update\` | Update dokumen |
| POST | \`/api/method/${REPO_NAME}.${MODULE_SNAKE}.api.delete\` | Hapus dokumen |
| GET | \`/api/method/${REPO_NAME}.${MODULE_SNAKE}.api.status\` | Health check (publik) |

**Contoh curl:**
\`\`\`bash
curl -X GET "http://site/api/method/${REPO_NAME}.${MODULE_SNAKE}.api.get_list?doctype=Isotank" \\
  -H "Authorization: token abc123:xyz789"
\`\`\`

**Dari JavaScript di form:**
\`\`\`javascript
frappe.call({
    method: "${REPO_NAME}.${MODULE_SNAKE}.api.get_list",
    args: { doctype: "Isotank" },
    callback(r) { console.log(r.message); }
});
\`\`\`

---

## Workflow Harian

| Ubah file | Perintah |
|-----------|----------|
| \`.py\` | \`bench restart\` |
| \`.js\` / \`.css\` | \`bench build --app ${REPO_NAME}\` atau \`bench watch\` |
| \`.json\` / field baru | \`bench --site nama_site migrate\` |
| Tambah custom field lewat UI | \`bench --site nama_site export-fixtures\` |
| Ubah urutan menu | Edit \`idx\` di \`desktop.py\` → \`bench restart\` |

---

## Push ke GitHub

\`\`\`bash
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/username/${REPO_NAME}.git
git push -u origin main
\`\`\`
EOF

echo -e "${GREEN}  ✓ README.md${NC}"

# ═══════════════════════════════════════════════════════════════
# OUTPUT: tree
# ═══════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}Struktur yang dibuat:${NC}"
echo ""
find "${REPO_NAME}" -not -path '*/__pycache__/*' | sort | awk '
{
  n = split($0, parts, "/")
  indent = ""
  for (i = 1; i < n-1; i++) indent = indent "│   "
  if (n > 1) {
    if (system("test -d " $0) == 0)
      print indent "├── " parts[n] "/"
    else
      print indent "├── " parts[n]
  } else {
    print parts[n] "/"
  }
}'

echo ""
echo -e "${YELLOW}Langkah selanjutnya:${NC}"
echo ""
echo "  1. Copy app ke bench:"
echo -e "     ${CYAN}cp -r \$(pwd)/${REPO_NAME} ~/frappe-bench/apps/${REPO_NAME}${NC}"
echo ""
echo "  2. Install ke site:"
echo -e "     ${CYAN}bench --site nama_site install-app ${REPO_NAME}${NC}"
echo -e "     ${CYAN}bench --site nama_site migrate && bench restart${NC}"
echo ""
echo "  3. Aktifkan developer mode:"
echo -e "     ${CYAN}bench --site nama_site set-config developer_mode 1${NC}"
echo ""
if [[ "$ADD_API" == "y" || "$ADD_API" == "Y" ]]; then
echo -e "${CYAN}  API endpoint:${NC}"
echo "  GET /api/method/${REPO_NAME}.${MODULE_SNAKE}.api.get_list?doctype=NamaDocType"
echo "  Header: Authorization: token <api_key>:<api_secret>"
echo "  Generate key: ERPNext → User → API Access → Generate Keys"
echo ""
fi
echo -e "${GREEN}Done! Push ke GitHub:${NC}"
echo -e "  ${CYAN}cd ${REPO_NAME} && git init && git add . && git commit -m 'initial'${NC}"
echo ""