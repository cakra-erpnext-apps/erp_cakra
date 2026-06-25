# 06 — Customizations Delta (Fork vs upstream frappe/crm)

> Purpose: precise, evidence-based inventory of everything the user customized in
> `D:\System_ERPNext\crm` on top of upstream `frappe/crm`. The Go rebuild MUST
> preserve every item listed here.

## Git evidence (baseline)

- `origin` = `https://github.com/cakra-erpnext-apps/crm.git`, `upstream` = `https://github.com/frappe/crm.git`.
- **All customizations live in a SINGLE commit** `7e1ec23c "Finish - CRM Customize"`,
  applied on top of upstream release commit `bf1b7f07` (`chore(release): Bumped to Version 1.72.0`).
  (Only later commit `08087d1a` just ignores frappe-ui submodule dirty state — not a feature.)
- Diff scope: `git diff --stat bf1b7f07 7e1ec23c` → **82 files, +7259 / −981**.
- Business domain: Indonesian freight forwarding / expedition / logistics (company code "CMI").

---

## Custom doctypes

All NEW, module `FCRM`, not present in upstream `bf1b7f07`. (Note: `crm_product`,
`crm_products`, `crm_dropdown_item` are UPSTREAM, NOT custom — verified.)

| DocType | Path | Type | Purpose |
|---|---|---|---|
| **CRM Quotation** | `crm/fcrm/doctype/crm_quotation/` | Master | Sales quotation built from an Inquiry (CRM Deal). Autoname `format:QT/{####}/CMI/{YYYY}`. State machine `Draft/Created/Sent/Approved/Rejected/Expired/Converted`. Has void fields, cargo/logistics tab, products table, additionals, T&C, rate-info, print-by. `title_field=subject`. |
| **CRM Quotation Product** | `crm/fcrm/doctype/crm_quotation_product/` | Child table | Line items of a quotation: `product` (Link→Item filtered `item_category=Revenue`), `qty`, `price`, `amount` (auto qty×price), `remark`. |
| **CRM Quotation Additional** | `crm/fcrm/doctype/crm_quotation_additional/` | Child table | Additional include/exclude lines: `type` (additional1/additional2), `title`, `item_name`, `price`. |
| **CRM Estimation** | `crm/fcrm/doctype/crm_estimation/` | Master | Costing/profit estimation (Expedition/Trading). Autoname in controller `EST/{####}/CMI/{YY}` (per-year reset counter). Revenue/Expense tabs, approval+profit, account-manager (KAM), 8-point Route tab, estimated KM/days, audit. `title_field=estimation_no`. |
| **CRM Estimation Detail** | `crm/fcrm/doctype/crm_estimation_detail/` | Child table | ONE child doctype used for BOTH revenue_items and expense_items (flagged via `is_expense`). Fields incl. `type_id`(Link Item), `qty`, `jalur`, `csize`, `area_id`, `jenis_karantina`, `dest_id`, `amount`, `per_doc`, `by_qty`, `uom`, `remarks`, `currency`, `supplier_id`, `shipping_line_id`, `port_id`, `sandaran_id`. |
| **CRM Transportation Mode** | `crm/fcrm/doctype/crm_transportation_mode/` | Master | Single field `mode_name` (autoname `field:mode_name`). Master list of expedition transport modes (Ocean/Inland/Railway/Air SOC/COC). |
| **CRM Deal Transportation Mode** | `crm/fcrm/doctype/crm_deal_transportation_mode/` | Child table | Single field `mode` (Link→CRM Transportation Mode). Used as Table MultiSelect on CRM Deal field `transportation_mode`. |

Frontend confirms these are first-class user features: dedicated pages
`pages/Quotation.vue`, `Quotations.vue`, `QuotationNew.vue`, `Estimation.vue`,
`Estimations.vue`, `EstimationNew.vue` + list views, modals, icons, router routes,
and an AppSidebar entry.

---

## Custom fields on stock doctypes

### CRM Deal (`crm/fcrm/doctype/crm_deal/crm_deal.json`) — net-new fields vs upstream

Domain-specific expedition/inquiry fields (verified absent in upstream):

| Field | Type | Notes |
|---|---|---|
| `subject` | Data | Inquiry subject (also `title_field` use in UI) |
| `deal_date` | Date | |
| `type_inquiry` | Select | Container 20/40/45, Domestic, Export/Import, FCL/LCL, Isotank T11/T14/T50/T75, OT/FR/HC/HD, Trucking, etc. |
| `service_type` | Select | New Customer / New Job Service / New Product / Existing Job Service / Existing Product |
| `business_unit` | Select | EMKL / FF / ISO / LOG / PCP / PKGOLEO |
| `job_service` | Select | ~55 expedition service options (Trucking/Export/Door-to-Door/Isotank/EMKL etc.) |
| `transportation_mode` | Table MultiSelect | → CRM Deal Transportation Mode |
| `incoterms` | Select | EXW/FCA/FAS/FOB/CFR/CIF/CPT/CIP/DPU/DAP/DDP |
| `shipper_consignee` | Data | |
| `origin`, `destination` | Data | |
| `port_pol_destination_detail_address` | Data | |
| `date_shipment` | Date | |
| `cargo_commodity` | Data | "Cargo Commodity / Type / HS Code" |
| `cargo_weight` | Data | "Cargo Weight (KG) / Volume / Packaging" |
| `cargo_packaging` | Data | |
| `status_cargo` | Data | |
| `qty`, `qty_volume` | Float / Data | |
| `rate` | Currency | |
| `estimasi_tarif` | Currency | "Estimasi Tarif" |
| `costing_procurement` | Currency | |
| `remarks` | (text) | |
| `is_void`, `void_section`, `void_reason`, `void_at`, `void_by` | soft-void block | |

Also a **custom autoname** on CRM Deal: controller `autoname()` →
`INQ/{####}/CMI/{YY}` (per-year reset). Naming series literal `INQ/.####./CMI/.YY.-`.

### CRM Lead (`crm/fcrm/doctype/crm_lead/crm_lead.json`) — net-new fields vs upstream

- Company/Legal section: `section_company_legal`, `nib`, `npwp`, `type_industry`, `target_goals`.
- Address section: `section_address`, `address`, `village`, `sub_district`, `regency`, `city`, `postal_code`.
- Soft-void block: `is_void`, `void_section`, `void_reason`, `void_at`, `void_by`.
- **Custom autoname** in `crm_lead.py`: `LD/{####}/CMI/{YY}` (per-year reset).

### Item (core ERPNext doctype) — via Custom Field fixture

- `Item-item_category` — Select `Revenue / Expense / Stock / Asset / Sparepart`,
  inserted after `item_group`, in list view + standard filter. Drives the
  `item_category=Revenue` link-filter on CRM Quotation Product.

---

## Fixtures (pinned custom data)

`hooks.py` `fixtures = [...]` exports these (with Indonesian intent-comments):

| Fixture file | DocType (filter) | What it pins |
|---|---|---|
| `crm_fields_layout.json` | CRM Fields Layout for `dt in [CRM Quotation, CRM Lead, CRM Estimation]` | Side-panel + Data-fields (+ Quick Entry for Lead) layouts. Includes the Quotation "Inquiry/Quote Information/Product/Additionals/Terms/Rate Info/Remark/Print" layout, Estimation Revenue/Expense/Remarks layout, Lead Company-Legal + Address sections. |
| `translation.json` | Translation where `translated_text like %Inquir%` | 31 rows. The **Deal→Inquiry relabel** (see below). |
| `crm_lead_source.json` | CRM Lead Source (all) | 19 sources, Indonesian-labelled (Referensi Eksternal, Database Marketing, Rujukan Karyawan, Panggilan Dingin, Pameran Dagang, etc.). |
| `crm_transportation_mode.json` | CRM Transportation Mode (all) | 8 modes: Ocean SOC/COC, Inland Truck SOC/COC, Railway SOC/COC, Air Freight SOC/COC. |
| `custom_field.json` | Custom Field `name = Item-item_category` | The Item Category select field (Revenue/Expense/Stock/Asset/Sparepart). |

---

## Relabeling (Deal → Inquiry)

- Implemented purely via **Translation** fixtures (`translation.json`) — the doctype
  name and route stay `CRM Deal`/`/deals`; only the UI label changes.
- Key rows: `Deal → Inquiry`, `Deals → Inquiries`, plus phrase translations
  ("convert {0} lead(s) to inquiry(s)", "Auto Update Expected Inquiry Value", etc.).
- `hooks.py` comment documents intent: *"Relabel Deal -> Inquiry di UI (lewat
  translation, tanpa ubah doctype/route)."*
- Reinforced throughout the new Quotation/Estimation UI and APIs, which call the
  Deal an "inquiry" (e.g. `crm.api.quotation.get_inquiry_detail`, the `inquiry`
  Link field on CRM Quotation pointing at CRM Deal filtered `status=Won`).

---

## Custom form-script architecture (file-based)

- The file-based loader (`import.meta.glob('../doctypes/*/*.js')` → `loadFileScript`)
  in `frontend/src/data/script.js` is **UPSTREAM** (already present in `bf1b7f07`;
  `script.js` itself has 0 changed lines in the custom commit). Not a user invention.
- The user's only **custom** file-based form script is
  `frontend/src/doctypes/crm_quotation/form.js` (added in the commit). It defines
  `class CRMQuotation` with `onLoad/onRender/inquiry()/account()` handlers:
  auto-fill account+subject+contact from the selected Inquiry (CRM Deal), render
  inquiry detail HTML in the sidebar via `crm.api.quotation.get_inquiry_detail`,
  and lock the `number` field read-only.
- NOTE: `frontend/src/doctypes/crm_task/form.js` and `.../fcrm_note/form.js` exist
  but are **upstream stock examples** (NOT in the custom commit) — do not attribute
  them to the user.

---

## Custom backend code (Indonesian-commented spots)

New / modified Python, all flagged by Indonesian comments (markers of user edits):

| File | What it adds |
|---|---|
| `crm/hooks.py` | `fixtures` list; `permission_query_conditions` + `has_permission` for CRM Quotation & CRM Estimation (assignment-based access). |
| `crm/api/permissions.py` (NEW) | Row-level access: Sales User sees only docs they own or are `_assign`ed; System Manager / Sales Manager / Administrator bypass. `quotation_query_conditions`, `estimation_query_conditions`, `quotation_has_permission`, `estimation_has_permission`. |
| `crm/api/void.py` (NEW) | `void_document(doctype, name, void, reason)` whitelisted soft-cancel (reversible) for `{CRM Quotation, CRM Lead, CRM Deal}` — sets `is_void/void_reason/void_at/void_by`. |
| `crm/api/quotation.py` (NEW) | `get_available_inquiries` (Won deals not yet used by a quotation), `get_inquiry_detail` (sidebar data), `get_quotation_contacts`. |
| `crm/api/activities.py` (MODIFIED) | +271 lines (activity feed adjustments for new flow). |
| `crm/fcrm/doctype/crm_quotation/crm_quotation.py` (NEW) | Controller: `validate` (1 inquiry → 1 quotation; Converted=final/locked), `before_save` (compute amounts/net_total + audit + default printed_by), `after_insert` (inherit inquiry assignees), `convert_to_estimation()` (whitelisted: copy products→Revenue rows, lock quotation, inherit assignees), `default_list_data`. Helper `_copy_assignees` carries access control inquiry→quotation→estimation. |
| `crm/fcrm/doctype/crm_estimation/crm_estimation.py` (NEW) | `autoname` (EST/####/CMI/YY), `validate` (purpose Customer/Agent unless from_convert), `before_save` (mark is_expense, compute rev_inc_tax & est_profit, audit), `default_list_data`. |
| `crm/fcrm/doctype/crm_lead/crm_lead.py` (MODIFIED) | `autoname` (LD/####/CMI/YY); `convert_to_deal` now blocks double-convert and sets status `Converted`. |
| `crm/fcrm/doctype/crm_deal/crm_deal.py` (MODIFIED, +/− ~900) | `autoname` (INQ/####/CMI/YY); field-order/layout rewrite to host the new expedition fields. |
| `crm/www/crm.py` (MODIFIED) | minor (4 lines). |

---

## Git-evidenced changed files (commit `7e1ec23c`)

**Backend (added):** `crm/api/permissions.py`, `crm/api/quotation.py`, `crm/api/void.py`,
the 7 custom doctype dirs (json/py/__init__ each), 5 fixtures
(`crm_fields_layout.json`, `crm_lead_source.json`, `crm_transportation_mode.json`,
`custom_field.json`, `translation.json`).
**Backend (modified):** `crm/api/activities.py`, `crm/hooks.py`, `crm/www/crm.py`,
`crm/fcrm/doctype/crm_deal/{crm_deal.json,crm_deal.py}`,
`crm/fcrm/doctype/crm_lead/{crm_lead.json,crm_lead.py}`.

**Frontend (added):** `pages/{Quotation,Quotations,QuotationNew,Estimation,Estimations,EstimationNew,DealNew}.vue`,
`components/ListViews/{QuotationsListView,EstimationsListView}.vue`,
`components/Modals/{QuotationModal,QuotationTerms}.vue`,
`components/Quotation/*` (Details/Form/Products/Print/Cargo/Additional/Terms + `shared/*`),
`components/Estimation/EstimationRoute.vue`,
`components/Icons/{QuotationIcon,EstimationIcon}.vue`,
`doctypes/crm_quotation/form.js`, `public/quotation/{logo.png,signature.png,README.md}`.
**Frontend (modified):** `router.js`, `vite.config.js`, `auto-imports.d.ts`, `.gitignore`,
`pages/{Deal,Deals,Lead,Leads}.vue`, `components/Layouts/AppSidebar.vue`,
`components/ListBulkActions.vue`, `components/Activities/DataFields.vue`,
`components/Settings/AssignmentRules/{AssigneeRules,AssignmentRuleView}.vue`.

> NOT customized (upstream, do not re-implement as "custom"): `crm_product`,
> `crm_products`, `crm_dropdown_item` doctypes; the file-script loader in
> `script.js`; `crm_task/form.js`, `fcrm_note/form.js`.
