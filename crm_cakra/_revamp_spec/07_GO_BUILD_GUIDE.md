# Go Revamp — Build Guide (Architecture + Phased Plan)

> Execution plan for rebuilding the CRM (spec 00–06) in **Go**. Opinionated defaults are given so an
> AI builder can start immediately; swap stack choices if you have house preferences. Acceptance
> criteria are included per phase so progress is verifiable.

---

## 1. The core architecture decision: hybrid (recommended)

Frappe is fully metadata-driven (see 00 §2). You have two extremes and a middle path:

| Approach | Pros | Cons |
|----------|------|------|
| **A. Static typed** — one Go struct + handcoded CRUD per entity | Simple, fast, type-safe, idiomatic Go | Lose saved views, dynamic columns, runtime form layouts, form scripts; lots of repetition |
| **B. Full meta engine** — reimplement Frappe's dynamic DocType engine in Go | 1:1 behavior, the Vue frontend works unchanged | Huge effort; fights Go's type system; you rebuild Frappe |
| **C. Hybrid ✅** | Typed core entities **+** a thin metadata layer only for *views, layouts, filters, form scripts* | Best effort/feature ratio; keeps the valuable dynamic UX | Two paradigms to bridge |

**Recommendation: C (hybrid).**
- Model the **~12 real entities** (Lead, Inquiry, Organization, Contact-link, Task, Note, Call Log,
  Quotation+children, Estimation+children, Transportation Mode) as **typed structs + sqlc queries**.
- Keep a small **`meta` package**: a registry describing each doctype's fields, plus tables backing
  `CRM View Settings` (saved views/columns/filters) and `CRM Fields Layout` (form trees). The generic
  list endpoint and the form renderer read from this layer — so you preserve the dynamic UX without a
  full Frappe clone.
- Config/master doctypes (statuses, sources, SLA, settings) → plain typed tables + a settings singleton.

---

## 2. Recommended Go stack

- **HTTP:** `chi` (or `echo`/`gin`) — REST routes. Mirror Frappe's call convention with a compat route
  `POST/GET /api/method/<dotted.path>` → handler, so the existing Vue SPA can talk to Go with minimal change.
- **DB:** PostgreSQL (cleaner than MariaDB for new build) or MariaDB if you want to keep Frappe's DB.
  **Access:** `sqlc` (typed queries) + `pgx`. Avoid heavy ORMs; the generic list engine needs raw SQL building.
- **Migrations:** `goose` or `golang-migrate`. Seed data (statuses/sources/SLA/layouts) as migration or a
  `seed` command (spec 03 lists every seed category).
- **Money:** `shopspring/decimal`. **Validation:** `go-playground/validator` + domain rules in services.
- **Auth/session:** cookie session or JWT; replicate Frappe roles (System/Sales Manager, Sales User) +
  **assignment-based row access** (spec 03, `api/permissions.py`). **Realtime:** `coder/websocket` hub
  (notifications, list refresh) — optional for v1.
- **Background jobs / scheduler:** `robfig/cron` + a worker (lead syncing cron, SLA recompute, email).
- **Frontend:** **keep the existing Vue 3 + frappe-ui SPA** initially, repointed at the Go API (fastest
  path to parity, since spec 04/05 document every endpoint contract). Replace later if desired. Building
  a new Go-templated UI (templ/HTMX) is a separate, larger track — do it only after API parity.

---

## 3. Suggested project layout

```
crm-go/
  cmd/
    server/        # main: HTTP server
    seed/          # seed statuses/sources/SLA/layouts/demo
    worker/        # cron: lead-sync, SLA, email
  internal/
    entity/        # typed domain: lead, inquiry, organization, quotation, estimation, task, note, calllog
      lead/ inquiry/ ...   # model.go + service.go (validate/convert/void) + queries.sql (sqlc)
    meta/          # doctype field registry, fieldtypes, naming-series counter
    views/         # CRM View Settings: saved views, column resolution, filter/sort/group/kanban builder
    layout/        # CRM Fields Layout: tab/section/column/field tree load+save
    listengine/    # the generic get_data implementation (the spine)
    auth/          # sessions, roles, assignment-based permission_query + has_permission
    sla/           # working-hours/holiday response-time engine
    integrations/  # twilio, exotel, whatsapp, erpnext, facebook clients
    api/           # http handlers mapped to the 69 endpoints (compat /api/method/*)
    db/            # pgx pool, sqlc generated, migrations
    realtime/      # websocket hub (optional v1)
  migrations/
  seed/            # JSON seed payloads (lifted from spec 03 + fixtures/)
```

---

## 4. How to implement the hard pieces

**4.1 Naming series (`LD/####/CMI/YY` etc.).** A `naming` service: parse the pattern, keep a counter row
per (series, year); on insert, increment atomically (`SELECT … FOR UPDATE` or a sequence per year), format.
Patterns: Lead `LD/####/CMI/YY`, Inquiry `INQ/####/CMI/YY`, Estimation `EST/####/CMI/YY`, Quotation
`QT/####/CMI/YYYY`. Reset counter when the year part rolls over.

**4.2 The generic list engine (`get_data`).** Port the contract from spec 03+05. Input: doctype, filters
`{field:[op,value]}`, order_by, group_by, page. Steps: resolve columns (custom → `CRM View Settings` →
entity `DefaultListData()` → fallback `name,modified`); build SQL safely (whitelist columns/operators from
the `meta` registry — never interpolate raw); return `{data, columns, rows, fields, kanban_*,
group_by_field, views, total_count, form_script}`. Operator map is fixed (equals→`=`, like→`LIKE`,
between, timespan, …) — copy it verbatim from spec 05.

**4.3 Row-level permissions.** Two hooks like Frappe: (a) a `WHERE` injector (`permission_query_conditions`)
that, for Sales User, limits rows to those assigned to the user (ToDo/`_assign`); (b) a per-doc
`HasPermission` check. Quotation/Estimation use assignment inheritance from the parent (spec 03/06).

**4.4 Conversion chain + soft-void.** Services: `Lead.ConvertToInquiry`, `Quotation.ConvertToEstimation`
(locks quotation → `Converted`, cascades assignees). `Void`/`Unvoid` set `is_void/void_reason/void_at/void_by`
(read-only block) instead of deleting — a reversible cancel (spec 06, `api/void.py`).

**4.5 Form layout + scripts.** `layout` package loads the Fields-Layout tree for a doctype/variant and the
form renderer (Vue) consumes it unchanged. Keep file-based form scripts in the SPA; only
`crm_quotation/form.js` has real logic (auto-fill account/contact/inquiry summary) — port its auto-fill to a
small Go endpoint if you want it server-authoritative.

**4.6 SLA engine.** Port `CRM Service Level Agreement` math (working hours per `CRM Service Day`, skip
`CRM Holiday`, priority response targets, `sla_status` state machine). Recompute on status changes + a cron.

---

## 5. Phased build plan (ordered, each phase shippable)

> Build the spine first, then entities, then the dynamic UX, then integrations.

**Phase 0 — Foundation.** DB + migrations + base columns (`name/owner/creation/modified/docstatus/idx`),
naming-series service, auth/sessions/roles, the `/api/method/*` compat router, sqlc wiring.
✅ *Done when:* can create a row with a correct `LD/0001/CMI/26`-style name and read it back over HTTP.

**Phase 1 — Core funnel entities (typed).** Lead, Inquiry/Inquiry, Organization, Contact-link, Task, Note,
Call Log — structs + CRUD services + validations from spec 01. Include the custom expedition fields on
Inquiry/Lead and the soft-void block.
✅ *Done when:* full CRUD + convert Lead→Inquiry works; custom fields persist; void/unvoid works.

**Phase 2 — The list engine + saved views.** Implement `get_data` (4.2), `CRM View Settings` CRUD,
filters/sort/group-by/kanban, column resolution, quick filters. Wire row permissions (4.3).
✅ *Done when:* the Vue list/kanban pages for every entity render against Go with filtering, grouping,
saved/pinned views, and assignment-scoped rows.

**Phase 3 — Quotation & Estimation (custom sales docs).** Quotation (+Product/+Additional), Estimation
(+Detail revenue/expense), `convert_to_estimation`, assignee inheritance, profit calc, the inquiry-picker
endpoints, and `crm_quotation/form.js` auto-fill. Heed the field_order gotcha (spec 06/00 §6).
✅ *Done when:* create Quotation from an Inquiry, convert to Estimation, profit computed, numbering correct.

**Phase 4 — Form layouts + form scripts.** `CRM Fields Layout` load/save, the form renderer, file-based
scripts loader. ✅ *Done when:* Lead/Inquiry/Quotation forms render from layout data; editing a layout changes
the form; quotation auto-fill fires.

**Phase 5 — Timeline & collaboration.** Activities/comments/emails/attachments/notifications endpoints
(spec 03), assignment (ToDo), notes/tasks on records. ✅ *Done when:* a Inquiry shows its activity timeline,
comments, assignments, and notifications.

**Phase 6 — SLA + masters + settings.** SLA engine (4.6), all status/source/lost-reason/industry/territory
(NSM) masters, settings singletons, seed data. ✅ *Done when:* response-time SLA tracks correctly across
working hours/holidays; masters drive dropdowns.

**Phase 7 — Integrations.** Twilio + Exotel telephony (call logs), WhatsApp, ERPNext cross-site sync,
Facebook lead syncing cron. ✅ *Done when:* inbound/outbound calls log; a Facebook lead imports as a CRM Lead.

**Phase 8 — Dashboard, data import/export, polish.** Dashboard charts (spec 03 `get_dashboard`), CSV/Excel
import-export, realtime refresh. ✅ *Done when:* dashboard renders; import creates rows; lists live-update.

---

## 6. Migrating the existing data

The current data lives in MariaDB (Frappe schema: `tab<DocType>` tables). Plan a one-time ETL: map each
`tab<DocType>` → the new Go table, preserving `name` (the formatted series) as PK and the child-table
`parent`/`parentfield` links. The naming counters must be initialized from the max existing number per
series/year so new records don't collide. (Out of scope for the spec files, but required for cutover.)

---

## 7. Don't-lose checklist (cross-reference before sign-off)

- [ ] Expedition fields on Inquiry/Lead (transportation mode, incoterms, job_service, ports, cargo) — spec 01/06
- [ ] Quotation/Estimation docs + conversion + profit calc — spec 01/06
- [ ] Per-year naming series LD/INQ/EST/QT with CMI code — spec 01/06
- [ ] Inquiry→Inquiry & Organization→Accounts relabels — spec 04/06
- [ ] Assignment-based row permissions — spec 03/06
- [ ] Reversible soft-void — spec 03/06
- [ ] Saved/pinned/public views + dynamic columns — spec 05
- [ ] Data-driven form layouts + quotation auto-fill script — spec 05/06
- [ ] SLA working-hours/holiday engine — spec 02/06
- [ ] 5 fixtures (lead sources, transportation modes, item-category, layouts, translation) — spec 06
- [ ] Integrations: Twilio/Exotel/WhatsApp/ERPNext/Facebook — spec 02/03

---

**TL;DR for the builder:** go **hybrid** (typed entities + thin meta for views/layouts), expose a
`/api/method/*`-compatible API so the current Vue SPA keeps working, build the **list engine** early (it's
the spine), and treat **06_CUSTOMIZATIONS_DELTA.md** as the requirements doc — that's the business value,
the rest is recoverable CRM scaffolding.
