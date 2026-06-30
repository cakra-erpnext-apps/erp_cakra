# Frappe CRM → Go Revamp — Master Spec (Overview & Index)

> **Purpose.** This folder is a complete, evidence-based specification of the CRM app at
> `D:\System_ERPNext\crm` so that an AI/engineering team can **rebuild it from scratch in Go**.
> Every fact here was extracted by reading the actual source (doctype JSON, Python controllers,
> Vue frontend, git history) — not assumed. Read this file first, then the numbered specs.

---

## 0. What this app actually is

- A **fork of upstream `frappe/crm` v1.72.0** (`bf1b7f07`) with **one customization commit**
  `7e1ec23c "Finish - CRM Customize"` — **82 files, +7259 / −981**.
- The customization turns the generic CRM into an **Indonesian freight / expedition (forwarding) CRM**,
  internal code **"CMI"**. The sales funnel and fields are logistics-specific (transportation mode,
  incoterms, container/isotank job services, port of loading/destination, cargo commodity/weight).
- **Backend:** Frappe framework (Python, metadata-driven ORM, MariaDB). **Frontend:** Vue 3 SPA using
  `frappe-ui`, talking to the backend purely through whitelisted JSON endpoints.
- Two Frappe "modules": **FCRM** (everything) and **Lead Syncing** (Facebook lead ads import).

### The funnel (core domain flow)
```
CRM Lead ──convert──▶ CRM Inquiry ("Inquiry") ──▶ CRM Quotation ──convert──▶ CRM Estimation
  LD/####/CMI/YY        INQ/####/CMI/YY            QT/####/CMI/YYYY            EST/####/CMI/YY
```
- **CRM Organization** is shown in the UI as **"Accounts"**; **CRM Inquiry** is shown as **"Inquiry"**
  (pure Translation relabel — doctype name & route stay `Inquiry`).
- Contacts use the **Frappe core `Contact`** doctype, linked through the `CRM Contacts` child table.
- Supporting objects: **CRM Task**, **FCRM Note**, **CRM Call Log**, activities/comments/emails timeline.
- Cross-cutting: **SLA** (response-time tracking with working hours + holidays), **assignment-based
  row permissions**, **reversible soft-void** (cancel without delete), **multi-currency**, **telephony**
  (Twilio + Exotel), **WhatsApp**, **ERPNext sync**, **Facebook lead syncing**.

---

## 1. How to read this spec (file index)

| File | Contents | Use it to build… |
|------|----------|------------------|
| **00_OVERVIEW.md** (this) | System map, Frappe→Go concept mapping, glossary | Orientation + architecture decisions |
| **01_DATA_MODEL_CORE.md** | 16 core entity + child doctypes, every field, controller logic, conversion chain | Go structs + DB schema for the funnel |
| **02_DATA_MODEL_CONFIG.md** | 35 config/master/settings/single + lead-syncing doctypes | Reference tables, settings store, SLA/telephony schema |
| **03_BACKEND_API_LOGIC.md** | 69 whitelisted endpoints (contracts), hooks/doc_events, seed/install data | Go HTTP API surface + event handlers + seeding |
| **04_FRONTEND_NAV_PAGES.md** | 27 routes, sidebar/menu tree, page-by-page catalog, stores/data layer | UI screens, navigation, page→endpoint map |
| **05_VIEWS_LISTS_FORMS.md** | List/Kanban/filter/group-by engine, Fields-Layout form engine, field controls, form scripts | The display+edit layer (the hard part) |
| **06_CUSTOMIZATIONS_DELTA.md** | Exactly what the user changed vs upstream (the "CMI" business logic) | **Do-not-lose list** — the actual value |
| **07_GO_BUILD_GUIDE.md** | Recommended Go stack, project layout, build phases/milestones, gotchas | The execution plan |

**Reading order for a builder:** 00 → 06 (what matters) → 01/02 (data) → 03 (API) → 05 (display engine) → 04 (UI) → 07 (plan).

---

## 2. The 4 Frappe concepts you MUST replicate in Go

Frappe is **metadata-driven**: there is almost no per-entity hand-written CRUD. The CRM's behavior
emerges from generic engines reading "DocType" metadata. A faithful Go rebuild has to reproduce these
four engines, or deliberately replace them with static code (see 07 for the trade-off).

1. **DocType meta = schema-as-data.** Each entity is a JSON file (`fcrm/doctype/*/*.json`) listing
   `fields[]` (fieldname, fieldtype, options, reqd, …), naming rule, permissions, and `links`. Every row
   in every table also has implicit columns: `name` (PK, often a formatted series), `owner`, `creation`,
   `modified`, `modified_by`, `docstatus`, `idx`. Fieldtypes map to Go/SQL types — see §4.

2. **The generic list engine — `crm.api.doc.get_data`.** ONE endpoint powers every list, kanban, and
   group-by view for every doctype. It resolves columns (custom → saved `CRM View Settings` → controller
   `default_list_data()` → fallback), applies a `{field:[op,value]}` filter map, sorts, paginates, and
   returns `{data, columns, rows, fields, kanban_*, group_by_field, views, total_count, form_script}`.
   **This is the spine of the app** (spec 03 + 05).

3. **Form layout = data, not code.** Forms aren't hardcoded screens. `CRM Fields Layout` rows store a
   **Tab → Section → Column → fields[]** JSON tree (variants: Quick Entry, Side Panel, Data Fields,
   Required Fields). The frontend renders any form by interpreting this tree (spec 05).

4. **Form scripts = per-doctype client logic.** Two sources merged at runtime: DB `CRM Form Script`
   records (JS eval'd) and **file-based** `frontend/src/doctypes/<slug>/form.js` classes with name-based
   hooks (`onLoad`, `onRender`, `onValidate`, `onSave`, `<fieldname>` = onChange). Only
   **`crm_quotation/form.js` is a user customization** (auto-fills account/contact/inquiry summary).

> If you skip these and write static CRUD per entity, you lose: saved views, dynamic columns, runtime
> form layout editing, and the form-script automations. Spec 07 recommends a **hybrid** (static typed
> core + a small meta layer for views/layouts).

---

## 3. What is CUSTOM (the must-not-lose list)

Full detail in **06_CUSTOMIZATIONS_DELTA.md**. Headline items:

- **7 custom doctypes:** `CRM Quotation` (+ child `CRM Quotation Product`, `CRM Quotation Additional`),
  `CRM Estimation` (+ child `CRM Estimation Detail` — reused for **both** revenue & expense rows,
  discriminated by `is_expense`), `CRM Transportation Mode` (master) + `CRM Inquiry Transportation Mode` (child).
- **~24 custom fields on CRM Inquiry** (the expedition block): `type_inquiry`, `service_type`, `business_unit`,
  `job_service` (~50 container/isotank enum values), `incoterms`, `transportation_mode` (Table MultiSelect),
  `origin`/`destination`, `cargo_*`, `qty`/`rate`/`estimasi_tarif`/`costing_procurement`, `inquiry_date`.
- **CRM Lead custom fields:** Indonesian legal/company (`nib`, `npwp`, `type_industry`), full ID address
  block (`village`/`sub_district`/`regency`/`city`/`postal_code`), Facebook sync ids, a `products` line table.
- **Core `Item-item_category` custom field** (Revenue/Expense/Stock/Asset/Sparepart) via fixture.
- **Custom per-year-reset naming:** `LD/####/CMI/YY`, `INQ/####/CMI/YY`, `EST/####/CMI/YY`, `QT/####/CMI/YYYY`.
- **Inquiry→Inquiry** & **Organization→Accounts** relabels (Translation only).
- **Custom backend:** `api/permissions.py` (assignment-based row access via `permission_query_conditions`
  + `has_permission`), `api/void.py` (reversible soft-cancel), `api/quotation.py` (inquiry pickers +
  `convert_to_estimation` + assignee inheritance), profit calc in the estimation controller.
- **5 fixtures** pinned in `hooks.py` (Fields Layout, Inquiry translation, 19 ID lead sources,
  8 transportation modes, item-category custom field).

---

## 4. Frappe → Go concept & type mapping (quick reference)

| Frappe concept | Go / infra equivalent |
|----------------|----------------------|
| DocType (JSON meta) | Go struct + DB table; keep a `Meta` registry for the dynamic layer |
| `name` (autoname series) | PK string; implement a **naming-series counter** (per-year reset) |
| Implicit `owner/creation/modified/modified_by/docstatus/idx` | base columns on every table (embed a `Base` struct) |
| Link field | foreign key (string PK ref) |
| Dynamic Link (`*_doctype` + `*_name`) | polymorphic ref (two columns: type + id) |
| Table (child) field | one-to-many child table with `parent`, `parenttype`, `parentfield`, `idx` |
| Table MultiSelect | junction table (e.g. Inquiry ⇄ Transportation Mode) |
| Select field | enum / `CHECK` constraint |
| Single doctype | settings singleton (one-row table or KV) |
| `@frappe.whitelist()` method | HTTP handler (`/api/method/<dotted.path>` → REST route) |
| `doc_events` (validate/on_update/after_insert) | service-layer hooks / domain events |
| `permission_query_conditions` + `has_permission` | row-level auth: inject `WHERE` + per-doc check |
| Fields Layout JSON | a layout table the form renderer reads (keep as data) |
| Form Script (JS) | keep file-based scripts as front-end logic, or port to server validation |
| Realtime (`frappe.publish_realtime`, socket.io) | WebSocket hub (e.g. nhooyr/websocket or centrifugo) |

**Fieldtype → SQL/Go:**
`Data/Small Text/Text/Long Text/Code/HTML` → `VARCHAR/TEXT` / `string`;
`Int/Check` → `BIGINT`/`bool`; `Float/Currency/Percent` → `DECIMAL`/`float64` (use decimal for money);
`Date` → `DATE`/`time.Time`; `Datetime` → `DATETIME`; `Time` → `TIME`;
`Link/Dynamic Link/Select` → `VARCHAR` (+FK/enum); `Table/Table MultiSelect` → child/junction tables;
`Attach/Attach Image` → file URL string; `Duration` → seconds int; `Rating` → float 0–1; `Geolocation` → JSON.

---

## 5. Scale of the system (so you can size the effort)

- **~55 doctypes** total: 16 core entity/child (spec 01) + 35 config/master/settings/lead-sync (spec 02) + a few covered in 03.
- **~260+ fields** in the core entities alone (Inquiry ~90, Lead ~70, Estimation ~55, Quotation ~50).
- **69 whitelisted endpoints** (54 in `api/*`, 15 in telephony integrations).
- **27 frontend routes**; sidebar menu order (desktop): **Dashboard · Accounts · Contacts · Leads ·
  Inquiries · Quotations · Estimations · Notes · Tasks · Call Logs** (Quotations/Estimations/Dashboard are custom).
- Integrations to reimplement as Go clients: **Twilio, Exotel, WhatsApp, ERPNext (cross-site FrappeClient),
  Facebook Graph (lead ads)**.

---

## 6. Known data-integrity gotchas (flagged by the mappers — read before coding)

- **CRM Quotation `field_order` is inconsistent**: references undefined fields (`additional1_detail`,
  `term_title`) and defines unwired ones (`company`, `branch`, `TaC`, `rates_tab`). Treat the union of
  `fields[]` as the real schema; ignore the broken layout order. `CRM Quotation Additional` child is fully
  defined but currently **orphaned** (not wired into the parent) — decide whether to keep it.
- **CRM Territory** is a **Nested Set tree** (`lft`/`rgt`/`parent_crm_territory`/`is_group`) — needs NSM handling.
- **CRM Estimation Detail** is one child doctype used for two grids (revenue + expense) via `is_expense`.
- **Money is multi-currency** — store currency + use decimal, don't use float64 for amounts.
- **`CRM Global Settings`** is *not* a Single despite the name (one row per (DocType,type), `autoname:hash`);
  **`FCRM/Twilio/Exotel/ERPNext CRM Settings`** are the true singletons.

➡ Continue to **07_GO_BUILD_GUIDE.md** for the recommended stack, project layout, and phased build plan.
