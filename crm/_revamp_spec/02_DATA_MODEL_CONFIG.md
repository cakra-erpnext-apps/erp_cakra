# 02 — Data Model: CONFIG / MASTER / SETTINGS / SINGLE + Lead Syncing

Source: Frappe CRM app at `D:\System_ERPNext\crm`. This document covers the **configuration / master / settings / single** doctypes and the **lead_syncing** module doctypes. The "core business entity" doctypes (CRM Lead, CRM Deal, CRM Organization, CRM Contact, CRM Task, CRM Call Log, CRM Note, CRM Estimation/Quotation/Product family, etc.) are documented elsewhere.

All doctypes here live in module **FCRM** unless noted; lead-syncing ones live in module **Lead Syncing**. Paths: `crm/crm/fcrm/doctype/<name>/<name>.json` and `crm/crm/lead_syncing/doctype/<name>/<name>.json`.

## Frappe → Go translation notes
- **DocType** → a table; `name` is the primary key (string). Frappe always adds: `name`, `creation` (datetime), `modified` (datetime), `modified_by`, `owner`, `docstatus` (int 0/1/2), `idx` (int). Reproduce these as standard columns.
- **issingle = 1** → a config **singleton**: one logical row. In Go model as a single config struct / one-row table / key-value (`Singles` table mirrors Frappe). Marked **[SINGLE]** below.
- **istable = 1** → a **child table** (embedded rows). Adds parent linkage columns: `parent`, `parenttype`, `parentfield`, plus `idx`. Marked **[CHILD]** below. No standalone permissions.
- **autoname**: `field:X` = name == value of field X (unique). `hash`/`Random` = random id. `autoincrement` = bigint PK. `prompt`/"Set by user" = user supplies name. `format:{a}-{b}` = templated. Otherwise default `hash`.
- **Link** fieldtype → foreign key to `options` doctype (by `name`). **Dynamic Link** → FK whose target doctype is named in another field (`options` points at that field). **Table** → has-many child rows of `options` doctype.
- **Check** → bool (0/1). **Int/Float/Currency/Percent** → numeric. **Duration** → seconds (int/float). **Date/Datetime/Time** → temporal. **Select** → enum (newline-separated `options`; leading blank = allow empty). **Password** → encrypted secret. **Code/JSON/Text/Text Editor/HTML Editor/Small Text/Data** → string/text. **Attach** → file path/URL string. **Autocomplete** → free-text string with suggestions.
- `fetch_from = "link_field.target_field"` → denormalized copy pulled from a linked doc on save.
- `depends_on` / `mandatory_depends_on` / `read_only_depends_on` are UI/validation eval expressions — record them but they are not storage.

---

## Index

### Status & Master doctypes (standalone, user-editable lists)
1. [CRM Lead Status](#1-crm-lead-status)
2. [CRM Deal Status](#2-crm-deal-status)
3. [CRM Communication Status](#3-crm-communication-status) — *also acts as "priority" master for SLA*
4. [CRM Lead Source](#4-crm-lead-source)
5. [CRM Lost Reason](#5-crm-lost-reason)
6. [CRM Industry](#6-crm-industry)
7. [CRM Territory](#7-crm-territory) — *tree (NSM)*
8. [CRM Transportation Mode](#8-crm-transportation-mode) — *custom-looking master*
9. [CRM Deal Transportation Mode](#9-crm-deal-transportation-mode) **[CHILD]** — *custom-looking*
10. [CRM Dropdown Item](#10-crm-dropdown-item) **[CHILD]**

### SLA doctypes
11. [CRM Service Level Agreement](#11-crm-service-level-agreement)
12. [CRM Service Level Priority](#12-crm-service-level-priority) **[CHILD]**
13. [CRM Service Day](#13-crm-service-day) **[CHILD]**
14. [CRM Holiday](#14-crm-holiday) **[CHILD]**
15. [CRM Holiday List](#15-crm-holiday-list)
16. [CRM Rolling Response Time](#16-crm-rolling-response-time) **[CHILD]**
17. [CRM Status Change Log](#17-crm-status-change-log) **[CHILD]**

### Telephony / Integration doctypes
18. [CRM Telephony Agent](#18-crm-telephony-agent)
19. [CRM Telephony Phone](#19-crm-telephony-phone) **[CHILD]**
20. [CRM Twilio Settings](#20-crm-twilio-settings) **[SINGLE]**
21. [CRM Exotel Settings](#21-crm-exotel-settings) **[SINGLE]**

### Settings / Single / Config doctypes
22. [FCRM Settings](#22-fcrm-settings) **[SINGLE]**
23. [CRM Global Settings](#23-crm-global-settings) — *per-doctype config rows (NOT single)*
24. [ERPNext CRM Settings](#24-erpnext-crm-settings) **[SINGLE]**
25. [CRM Fields Layout](#25-crm-fields-layout)
26. [CRM Form Script](#26-crm-form-script)
27. [CRM View Settings](#27-crm-view-settings)
28. [CRM Dashboard](#28-crm-dashboard)
29. [CRM Notification](#29-crm-notification)
30. [CRM Invitation](#30-crm-invitation)

### Lead Syncing module
31. [Facebook Page](#31-facebook-page)
32. [Facebook Lead Form](#32-facebook-lead-form)
33. [Facebook Lead Form Question](#33-facebook-lead-form-question) **[CHILD]**
34. [Lead Sync Source](#34-lead-sync-source)
35. [Failed Lead Sync Log](#35-failed-lead-sync-log)

---

## 1. CRM Lead Status
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:lead_status` (name = the status text, unique) · **translated_doctype:** 1
- Master list of lead statuses. Controller is `pass` (no logic).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| lead_status | Data | Status | — | 1 | 0 | — | 1 | — | — | *(unique)* |
| type | Select | Type | `Open / Ongoing / On Hold / Won / Lost` | 0 | 0 | Open | 1 | — | — |
| color | Select | Color | `black/gray/blue/green/red/pink/orange/amber/yellow/cyan/teal/violet/purple` | 0 | 0 | gray | 1 | — | — |
| position | Int | Position | — | 0 | 0 | 1 | 1 | — | — |

## 2. CRM Deal Status
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:deal_status` (unique) · **translated_doctype:** 1
- Master list of deal statuses. Controller is `pass`. Adds a `probability` used for forecasting (a standard Form Script copies `probability` onto the deal when status changes — see FCRM Settings §22).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| deal_status | Data | Status | — | 1 | 0 | — | 1 | — | — | *(unique)* |
| type | Select | Type | `Open / Ongoing / On Hold / Won / Lost` | 0 | 0 | Open | 1 | — | — |
| position | Int | Position | — | 0 | 0 | — | 1 | — | — |
| probability | Percent | Probability | — | 0 | 0 | — | 1 | — | — |
| color | Select | Color | (same 13-color palette as Lead Status) | 0 | 0 | gray | 1 | — | — |

## 3. CRM Communication Status
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:status` (unique) · `quick_entry: 1`
- Tiny master: list of communication statuses (e.g. "Open", "Replied"). **Also doubles as the "Priority" master**: `CRM Service Level Priority.priority` is a Link to this doctype. Controller `pass`.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| status | Data | Status | — | 1 | 0 | — | 1 | — | — | *(unique)* |

## 4. CRM Lead Source
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:source_name` (unique) · `allow_import`, `quick_entry`. Controller `pass`.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| source_name | Data | Source Name | — | 1 | 0 | — | 1 | — | — | *(unique)* |
| details | Text Editor | Details | — | 0 | 0 | — | 0 | — | — |

## 5. CRM Lost Reason
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:lost_reason` (unique) · `quick_entry`. Controller `pass`.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| lost_reason | Data | Lost Reason | — | 1 | 0 | — | 1 | — | — | *(unique)* |
| description | Text Editor | Description | — | 0 | 0 | — | 0 | — | — |

## 6. CRM Industry
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:industry` (unique) · `allow_import`, `quick_entry`. Controller `pass`.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| industry | Data | Industry | — | 0 | 0 | — | 0 | — | — | *(unique)* |

## 7. CRM Territory
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:territory_name` (unique) · **is_tree: 1** with `nsm_parent_field = parent_crm_territory` (Nested Set Model). Controller `pass`.
- **Go note:** model as an adjacency tree. `lft`/`rgt` are NSM bounds (maintain on insert/move/delete) and `is_group` marks a non-leaf node. `old_parent` tracks prior parent for re-parenting.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| territory_name | Data | Territory Name | — | 1 | 0 | — | 1 | — | — | *(unique)* |
| territory_manager | Link | Territory Manager | User | 0 | 0 | — | 0 | — | — |
| old_parent | Link | Old Parent | CRM Territory | 0 | 0 | — | 0 | — | — |
| parent_crm_territory | Link | Parent CRM Territory | CRM Territory | 0 | 0 | — | 0 | — | — | *(NSM parent; ignore_user_permissions)* |
| lft | Int | Left | — | 0 | 1 | — | 0 | — | — | *(hidden, no_copy)* |
| rgt | Int | Right | — | 0 | 1 | — | 0 | — | — | *(hidden, no_copy)* |
| is_group | Check | Is Group | — | 0 | 0 | 0 | 0 | — | — |

## 8. CRM Transportation Mode
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:mode_name` (unique) · `allow_import`, `quick_entry`. Controller `pass`.
- **CUSTOM-LOOKING master** (created 2026-06-04, terse hand-written JSON with inline permissions; not part of upstream Frappe CRM). Simple list of transportation modes referenced by the child table below and by CRM Deal.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| mode_name | Data | Transportation Mode | — | 1 | 0 | — | 1 | — | — | *(unique)* |

## 9. CRM Deal Transportation Mode  **[CHILD]**
- **Module:** FCRM · **istable:** 1 · **issingle:** 0 · no autoname (child). Controller: none of note.
- **CUSTOM-LOOKING child table** (created 2026-06-04). Embedded in CRM Deal to record one or more transportation modes per deal.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| mode | Link | Transportation Mode | CRM Transportation Mode | 1 | 0 | — | 1 | — | — | *(columns: 5)* |

## 10. CRM Dropdown Item  **[CHILD]**
- **Module:** FCRM · **istable:** 1 · **issingle:** 0. Controller `pass`.
- Child rows of **FCRM Settings.dropdown_items** — sidebar/nav dropdown entries (routes or separators). "Standard" rows are seeded from the `standard_dropdown_items` hook and may not be deleted (enforced in FCRM Settings).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| name1 | Data | Name | — | 0 | 1 | — | 0 | `eval:doc.is_standard` | — | *(unique; the stable key)* |
| label | Data | Label | — | 0 | 0 | — | 1 | — | — | *(mandatory if type==Route)* |
| type | Select | Type | `Route / Separator` | 0 | 0 | — | 1 | — | — | *(read_only if is_standard)* |
| route | Data | Route | — | 0 | 0 | — | 1 | `eval:doc.type == 'Route'` | — | *(mandatory if type==Route)* |
| open_in_new_window | Check | Open in new window | — | 0 | 0 | 1 | 0 | `eval:doc.type == 'Route'` | — |
| hidden | Check | Hidden | — | 0 | 0 | 0 | 1 | — | — |
| is_standard | Check | Is Standard | — | 0 | 1 | 0 | 0 | — | — |
| icon | Code | Icon | — | 0 | 0 | — | 0 | — | — | *(svg or feather icon name)* |

---

## 11. CRM Service Level Agreement
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:sla_name` (unique).
- Central SLA definition: validity window, condition, priority targets, working hours, holiday list, rolling responses.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| sla_name | Data | SLA Name | — | 1 | 0 | — | 1 | — | — | *(unique; in_standard_filter)* |
| apply_on | Link | Apply On | DocType (filtered to `CRM Lead`,`CRM Deal`) | 1 | 0 | — | 0 | — | — |
| enabled | Check | Enabled | — | 0 | 0 | 0 | 0 | — | — |
| default | Check | Default | — | 0 | 0 | 0 | 0 | — | — | *(only one default per apply_on)* |
| rolling_responses | Check | Rolling Responses | — | 0 | 0 | 0 | 0 | — | — | *(restart SLA each customer reply)* |
| condition | Code (Python) | Condition | — | 0 | 0 | — | 0 | `eval: !doc.condition_json` | — | *(simple python expr, e.g. `doc.status == 'Open'`)* |
| condition_json | Code | Condition | — | 0 | 0 | — | 0 | `eval: doc.condition_json` | — | *(portal-generated form of condition)* |
| start_date | Date | Start Date | — | 0 | 0 | — | 0 | — | — |
| end_date | Date | End Date | — | 0 | 0 | — | 0 | — | — |
| priorities | Table | Priorities | CRM Service Level Priority | 1 | 0 | — | 0 | — | — |
| working_hours | Table | Working Hours | CRM Service Day | 1 | 0 | — | 0 | — | — |
| holiday_list | Link | Holiday List | CRM Holiday List | 0 | 0 | — | 0 | — | — |

**Controller logic (`crm_service_level_agreement.py` + `utils.py`):** This is the heaviest config controller — port carefully.
- `validate`: (a) at most one `default` SLA per `apply_on`; (b) `condition` must safe-eval against a fresh doc of `apply_on`.
- `apply(doc)` — called on a Lead/Deal: orchestrates `handle_creation`, `handle_communication_status`, `handle_targets`, `handle_sla_status`, `handle_rolling_sla_status`. It **mutates fields on the target lead/deal** (these live on CRM Lead/CRM Deal, documented in the core spec): `sla_creation`, `first_responded_on`, `last_responded_on`, `first_response_time`, `last_response_time`, `response_by`, `sla_status`, and appends to the deal's/lead's `rolling_responses` child table.
- **Response-time math:** `calc_time(start, duration_seconds)` walks forward over working hours, skipping holidays and non-workdays, to compute a `response_by` deadline. `calc_elapsed_time(start, end)` sums seconds that fall inside working hours (excluding holidays/off-days) — second-by-second loop. `is_working_time` checks the per-weekday start/end window.
- **`sla_status` values produced:** `First Response Due`, `Fulfilled`, `Failed`, and (rolling) `Rolling Response Due`.
- Helper dicts: `get_priorities()` (priority→row), `get_default_priority()` (the row flagged `default_priority`, else first), `get_workdays()/get_working_days()/get_working_hours()` (weekday→times), `get_holidays()` (dates from the linked Holiday List).
- **`utils.get_sla(doc)`** picks the applicable SLA: filter enabled, within validity window, matching `apply_on`; if the doc has a `communication_status`, inner-join on Priority matching it; default SLA is evaluated last; first SLA whose `condition` safe-evals true wins. `get_context(doc)` builds the safe-eval namespace (`doc` dict + `frappe.utils`).

## 12. CRM Service Level Priority  **[CHILD]**
- **Module:** FCRM · **istable:** 1. Child of SLA `priorities`. Controller `pass`.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| default_priority | Check | Default Priority | — | 0 | 0 | 0 | 1 | — | — |
| priority | Link | Priority | CRM Communication Status | 1 | 0 | — | 1 | — | — |
| first_response_time | Duration | First Response Time | — | 1 | 0 | — | 1 | — | — | *(seconds)* |

## 13. CRM Service Day  **[CHILD]**
- **Module:** FCRM · **istable:** 1. Child of SLA `working_hours`. Controller `pass`.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| workday | Select | Workday | `Monday … Sunday` | 1 | 0 | — | 1 | — | — |
| start_time | Time | Start Time | — | 1 | 0 | — | 1 | — | — |
| end_time | Time | End Time | — | 1 | 0 | — | 1 | — | — |

## 14. CRM Holiday  **[CHILD]**
- **Module:** FCRM · **istable:** 1. Child of CRM Holiday List `holidays`. Controller `pass`.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| date | Date | Date | — | 1 | 0 | — | 1 | — | — |
| weekly_off | Check | Weekly Off | — | 0 | 0 | 0 | 0 | — | — |
| description | Text Editor | Description | — | 1 | 0 | — | 1 | — | — |

## 15. CRM Holiday List
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:holiday_list_name` (unique).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| holiday_list_name | Data | Holiday List Name | — | 1 | 0 | — | 1 | — | — | *(unique)* |
| from_date | Date | From Date | — | 1 | 0 | — | 1 | — | — |
| to_date | Date | To Date | — | 1 | 0 | — | 1 | — | — |
| total_holidays | Int | Total Holidays | — | 0 | 0 | — | 0 | — | — | *(auto-set = len(holidays))* |
| weekly_off | Select | Weekly Off | `'' / Monday … Sunday` | 0 | 0 | — | 0 | — | — |
| add_to_holidays | Button | Add to Holidays | (action `add_to_holidays`) | — | — | — | — | — | — | *(UI button)* |
| clear_table | Button | Clear Table | (action `clear_table`) | — | — | — | — | — | — | *(UI button)* |
| holidays | Table | Holidays | CRM Holiday | 0 | 0 | — | 0 | — | — |

**Controller logic:** `validate` → `validate_days` (to_date ≥ from_date; every holiday date within range) and set `total_holidays`. Whitelisted `get_weekly_off_dates()` generates all dates for the chosen `weekly_off` weekday between from/to (skipping ones already present) and appends them as `weekly_off=1` holiday rows.

## 16. CRM Rolling Response Time  **[CHILD]**
- **Module:** FCRM · **istable:** 1. Child table named `rolling_responses` on CRM Lead/CRM Deal (populated by SLA logic). Controller `pass`. All read-only.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| response_time | Duration | Response Time | — | 0 | 1 | — | 1 | — | — |
| responded_on | Datetime | Responded On | — | 0 | 1 | — | 1 | — | — |
| status | Select | Status | `Fulfilled / Failed` | 0 | 1 | — | 1 | — | — |

## 17. CRM Status Change Log  **[CHILD]**
- **Module:** FCRM · **istable:** 1. Child table tracking status transitions on Lead/Deal (duration spent in each status). Controller `pass`.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| from | Data | From | — | 0 | 0 | — | 1 | — | — |
| to | Data | To | — | 0 | 0 | — | 1 | — | — |
| from_date | Datetime | From Date | — | 0 | 0 | — | 1 | — | — |
| to_date | Datetime | To Date | — | 0 | 0 | — | 1 | — | — |
| duration | Duration | Duration | — | 0 | 0 | — | 1 | — | — |
| last_status_change_log | Link | Last Status Change Log | CRM Status Change Log | 0 | 0 | — | 0 | — | — |
| from_type | Data | From Type | — | 0 | 0 | — | 1 | — | — |
| to_type | Data | To Type | — | 0 | 0 | — | 1 | — | — |
| log_owner | Link | Owner | User | 0 | 0 | — | 0 | — | — |

---

## 18. CRM Telephony Agent
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:user` (unique — one agent record per user) · `title_field = user_name`.
- Per-user telephony configuration (which numbers / medium / receiving device).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| user | Link | User | User | 1 | 0 | — | 1 | — | — | *(unique; in_standard_filter)* |
| user_name | Data | User Name | — | 0 | 0 | — | 1 | — | `user.full_name` |
| mobile_no | Data | Mobile No. | — | 0 | 1 | — | 1 | — | — | *(derived from phone_nos primary)* |
| default_medium | Select | Default Medium | `'' / Twilio / Exotel` | 0 | 0 | — | 0 | — | — |
| twilio_number | Data | Twilio Number | — | 0 | 0 | — | 0 | — | — |
| exotel_number | Data | Exotel Number | — | 0 | 0 | — | 0 | — | — |
| call_receiving_device | Select | Device | `Computer / Phone` | 0 | 0 | Computer | 0 | — | — |
| phone_nos | Table | Phone Numbers | CRM Telephony Phone | 0 | 0 | — | 0 | — | — |

**Controller logic:** `validate` keeps `mobile_no` and the `phone_nos` table in sync — when `mobile_no` changes it adds the new number (primary) and removes the old; `set_primary` enforces exactly one primary row and sets `mobile_no` from it (throws if >1 primary).

## 19. CRM Telephony Phone  **[CHILD]**
- **Module:** FCRM · **istable:** 1. Child of CRM Telephony Agent `phone_nos`. Controller `pass`.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| number | Data | Number | — | 1 | 0 | — | 1 | — | — |
| is_primary | Check | Is Primary | — | 0 | 0 | 0 | 1 | — | — |

## 20. CRM Twilio Settings  **[SINGLE]**
- **Module:** FCRM · **issingle:** 1 · `track_changes`. Config singleton for Twilio voice integration. `api_key`/`api_secret`/`twiml_sid` are **permlevel 1** (restricted). `friendly_resource_name = "Frappe CRM"`.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| enabled | Check | Enabled | — | 0 | 0 | 0 | 0 | — | — |
| record_calls | Check | Record Calls | — | 0 | 0 | 0 | 0 | `enabled` | — |
| account_sid | Data | Account SID | — | 0 | 0 | — | 1 | `enabled` | — | *(mandatory if enabled)* |
| auth_token | Password | Auth Token | — | 0 | 0 | — | 1 | `enabled` | — | *(mandatory if enabled)* |
| api_key | Data | API Key | — | 0 | 1 | — | 0 | `enabled` | — | *(permlevel 1; auto-generated)* |
| api_secret | Password | API Secret | — | 0 | 1 | — | 0 | `enabled` | — | *(permlevel 1; auto-generated)* |
| twiml_sid | Data | TwiML SID | — | 0 | 0 | — | 0 | `enabled` | — | *(permlevel 1; auto-generated)* |
| app_name | Data | App Name | — | 0 | 0 | — | 0 | — | — |
| twilio_apps | Data | Twilio Apps | — | 0 | 0 | — | 0 | — | — | *(hidden; comma-joined app list)* |

**Controller logic (calls Twilio API via `twilio.rest.Client`):** `validate` flags `new_sid` if `account_sid` changed, then `validate_twilio_account` (fetch account to confirm SID/token). `on_update` (when account_sid set) instantiates a Twilio client and: `set_api_credentials` (create API key/secret if missing or SID changed), `set_application_credentials` (find/create a TwiML app pointing at the CRM voice webhook URL), `fetch_applications` (store comma-joined app names). `get_twilio_voice_url()` builds the public webhook URL (`/api/method/crm.integrations.twilio.api.voice`). **Go note:** reimplement as an external Twilio REST integration.

## 21. CRM Exotel Settings  **[SINGLE]**
- **Module:** FCRM · **issingle:** 1. Config singleton for Exotel telephony.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| enabled | Check | Enabled | — | 0 | 0 | 0 | 0 | — | — |
| record_call | Check | Record Outgoing Calls | — | 0 | 0 | 0 | 0 | `enabled` | — |
| account_sid | Data | Account SID | — | 0 | 0 | — | 0 | `enabled` | — | *(mandatory if enabled)* |
| subdomain | Data | Subdomain | — | 0 | 0 | — | 0 | `enabled` | — | *(mandatory if enabled)* |
| webhook_verify_token | Data | Webhook Verify Token | — | 0 | 0 | — | 0 | `enabled` | — | *(mandatory if enabled)* |
| api_key | Data | API Key | — | 0 | 0 | — | 1 | `enabled` | — | *(mandatory if enabled)* |
| api_token | Password | API Token | — | 0 | 0 | — | 1 | `enabled` | — | *(mandatory if enabled)* |

**Controller logic:** `validate` → if enabled, GET `https://{subdomain}/v1/Accounts/{account_sid}` with basic auth (`api_key`:`api_token`); throw "Invalid credentials" on non-200.

---

## 22. FCRM Settings  **[SINGLE]**
- **Module:** FCRM · **issingle:** 1. The primary application settings singleton (tabs: Settings, Currency, Branding, Dropdown items). **Note:** the controller also references `default_calendar_view`, `event_notifications`, `all_day_event_notifications` in its type hints (likely added via fixtures/hooks) though not in the JSON `field_order` — port `default_calendar_view` (Select: Daily/Weekly/Monthly) and the two event-notification child tables if present.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| restore_defaults | Button | Restore Defaults | (action) | — | — | — | — | — | — |
| restore_demo_data | Button | Restore Demo Data | (action) | — | — | — | — | — | — |
| enable_forecasting | Check | Enable Forecasting | — | 0 | 0 | 0 | 0 | — | — | *(makes deal expected_closure_date & expected_deal_value mandatory)* |
| auto_update_expected_deal_value | Check | Auto update Expected Deal Value | — | 0 | 0 | 1 | 0 | — | — |
| update_timestamp_on_new_communication | Check | Update timestamp on new communication | — | 0 | 0 | 1 | 0 | — | — |
| auto_mark_replied_on_response | Check | Mark lead/deal as replied on response | — | 0 | 0 | 0 | 0 | — | — | *(SLA only)* |
| auto_reopen_on_new_communication | Check | Reopen lead/deal on new communication | — | 0 | 0 | 0 | 0 | — | — | *(SLA only)* |
| currency | Link | Currency | Currency | 0 | 0 | — | 1 | — | — | *(becomes read-only once set)* |
| service_provider | Select | Service Provider | `frankfurter.app / fawazahmed-exchange-api / exchangerate.host / exchangerate-api` | 0 | 0 | frankfurter.app | 0 | — | — | *(exchange-rate provider)* |
| access_key | Data | Access Key | — | 0 | 0 | — | 0 | `eval:doc.service_provider == 'exchangerate.host'` | — | *(mandatory for exchangerate.host)* |
| brand_name | Data | Name | — | 0 | 0 | — | 0 | — | — |
| brand_logo | Attach | Logo | — | 0 | 0 | — | 0 | — | — |
| favicon | Attach | Favicon | — | 0 | 0 | — | 0 | — | — |
| dropdown_items | Table | (Dropdown items) | CRM Dropdown Item | 0 | 0 | — | 0 | — | — |

**Controller logic:**
- `validate`: (a) `do_not_allow_to_delete_if_standard` — prevent removing standard dropdown rows that come from the `standard_dropdown_items` hook; (b) `setup_forecasting` — when `enable_forecasting` toggles, add/remove a "Forecasted Sales" section in the `CRM Deal-Side Panel` layout (CRM Fields Layout) and create/delete Property Setters making `expected_closure_date`/`expected_deal_value` required on CRM Deal; (c) `make_currency_read_only` — once a currency is chosen, a Property Setter makes the field read-only.
- Whitelisted `restore_defaults(force)` → runs `crm.install.after_install`; `restore_demo_data()` → `crm.demo.api.create_demo_data`.
- Module funcs: `after_migrate`/`sync_table` keep `dropdown_items` synced with the hook; `create_forecasting_script` installs a standard CRM Form Script "Forecasting Script" (copies Deal Status `probability` onto the deal on status change).

## 23. CRM Global Settings
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 (**NOT a single** despite the name) · **autoname:** `hash` (Random). Controller `pass`.
- One **row per (DocType, type)** holding a JSON blob of "Quick Filters" or "Sidebar Items" configuration. Effectively a generic per-doctype config store.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| dt | Link | DocType | DocType | 1 | 0 | DocType | 1 | — | — |
| type | Select | Type | `Quick Filters / Sidebar Items` | 1 | 0 | — | 1 | — | — |
| json | JSON | JSON | — | 0 | 0 | — | 0 | — | — |

## 24. ERPNext CRM Settings  **[SINGLE]**
- **Module:** FCRM · **issingle:** 1. Config singleton bridging CRM ↔ ERPNext (same site or remote site via API).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| enabled | Check | Enabled | — | 0 | 0 | 0 | 0 | — | — |
| erpnext_company | Data | Company in ERPNext site | — | 0 | 0 | — | 0 | `enabled` | — | *(mandatory if enabled)* |
| is_erpnext_in_different_site | Check | Is ERPNext installed on a different site? | — | 0 | 0 | 0 | 0 | `enabled` | — |
| erpnext_site_url | Data | ERPNext Site URL | — | 0 | 0 | — | 0 | `enabled && is_erpnext_in_different_site` | — | *(mandatory if remote)* |
| api_key | Data | API Key | — | 0 | 0 | — | 0 | `enabled && is_erpnext_in_different_site` | — | *(mandatory if remote)* |
| api_secret | Password | API Secret | — | 0 | 0 | — | 0 | `enabled && is_erpnext_in_different_site` | — | *(mandatory if remote)* |
| create_customer_on_status_change | Check | Create customer on status change | — | 0 | 0 | 0 | 0 | `enabled` | — |
| deal_status | Link | Deal Status | CRM Deal Status | 0 | 0 | — | 0 | `enabled && create_customer_on_status_change` | — | *(trigger status)* |

**Controller logic (integration glue — Go note: reimplement as ERPNext REST client):**
- `validate` (when enabled): ensure ERPNext installed (local) ; add Property Setter so Quotation `quotation_to` allows CRM Deal/Prospect; create custom fields both sides (`erpnext_customer` Data field on CRM Deal locally, plus remote custom fields); install standard Form Script "Create Quotation from CRM Deal".
- Whitelisted helpers: `get_external_companies`, `is_erpnext_installed`, `reset_erpnext_form_script`, `get_customer_link`, `get_quotation_url`.
- `create_customer_in_erpnext(doc, method)` — **hook fired on CRM Deal save**: when enabled + `create_customer_on_status_change` + deal.status == settings.deal_status, create a Customer in ERPNext (local import or remote `FrappeClient.post_api`) from org/contacts/address, then write back `erpnext_customer` onto the deal and publish realtime `crm_customer_created`.
- `create_prospect_in_remote_site`, `get_quotation_url` build cross-site Quotation/Prospect creation links.

## 25. CRM Fields Layout
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `format:{dt}-{type}` (e.g. `CRM Deal-Side Panel`). Controller `pass` (no logic).
- Stores per-doctype UI layout JSON for the frontend (quick entry forms, side panels, grid rows, etc.).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| dt | Link | Document Type | DocType | 0 | 0 | — | 1 | — | — | *(in_standard_filter)* |
| type | Select | Type | `Quick Entry / Side Panel / Data Fields / Grid Row / Required Fields` | 0 | 0 | — | 1 | — | — |
| layout | Code (JSON) | Layout | — | 0 | 0 | — | 0 | — | — |

## 26. CRM Form Script
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `prompt` (user supplies name). Stores JS scripts that customize CRM Lead/Deal forms or list views (custom actions etc.).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| dt | Link | DocType | DocType | 1 | 0 | — | 1 | — | — |
| view | Select | Apply To | `Form / List` | 0 | 0 | Form | 1 | — | — | *(set_only_once)* |
| enabled | Check | Enabled | — | 0 | 0 | 0 | 0 | — | — | *(hidden)* |
| is_standard | Check | Is Standard | — | 0 | 0 | 0 | 0 | — | — | *(no_copy)* |
| script | Code (JS) | Script | — | 0 | 0 | `function setupForm({ doc }) { return { actions: [] } }` | 0 | — | — |

**Controller logic:** `validate` — outside dev mode, a **standard** script may only have its `enabled` flag changed (reverts any other edits); otherwise throws "need developer mode". Module func `get_form_script(dt, view="Form")` returns the enabled script(s) for a doctype/view.

## 27. CRM View Settings
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `autoincrement` (integer PK) · `read_only: 1` (doctype managed only via whitelisted API), `track_changes`, `title_field = label`.
- Saved list/group-by/kanban views per user (or public/standard). Code fields hold JSON.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| label | Data | Label | — | 0 | 0 | — | 1 | — | — | *(in_standard_filter; title)* |
| icon | Data | Icon | — | 0 | 0 | — | 0 | — | — |
| user | Link | User | User | 0 | 0 | — | 0 | — | — |
| is_standard | Check | Is Standard | — | 0 | 0 | 0 | 0 | — | — |
| is_default | Check | Is Default | — | 0 | 0 | 0 | 0 | — | — |
| type | Select | Type | `list / group_by / kanban` | 0 | 0 | list | 0 | — | — |
| dt | Link | DocType | DocType | 0 | 0 | — | 1 | — | — | *(in_standard_filter)* |
| route_name | Data | Route Name | — | 0 | 0 | — | 0 | — | — |
| pinned | Check | Pinned | — | 0 | 0 | 0 | 0 | — | — |
| public | Check | Public | — | 0 | 0 | 0 | 0 | — | — |
| filters | Code | Filters | — | 0 | 0 | — | 0 | — | — | *(JSON)* |
| order_by | Code | Order By | — | 0 | 0 | — | 0 | — | — |
| load_default_columns | Check | Load Default Columns | — | 0 | 0 | 0 | 0 | — | — |
| columns | Code | Columns | — | 0 | 0 | — | 0 | — | — | *(JSON)* |
| rows | Code | Rows | — | 0 | 0 | — | 0 | — | — | *(JSON)* |
| group_by_field | Data | Group By Field | — | 0 | 0 | — | 0 | — | — |
| column_field | Data | Column Field | — | 0 | 0 | — | 0 | — | — | *(kanban)* |
| title_field | Data | Title Field | — | 0 | 0 | — | 0 | — | — | *(kanban)* |
| kanban_columns | Code | Kanban Columns | — | 0 | 0 | — | 0 | — | — | *(JSON)* |
| kanban_fields | Code | Kanban Fields | — | 0 | 0 | — | 0 | — | — | *(JSON)* |

**Controller logic:** Doctype is API-driven. Whitelisted: `create`, `update`, `delete`, `public` (toggle public; Sales Manager+ only), `pin`, `set_as_default`, `create_or_update_standard_view`, `fetch_and_update_kanban_columns`. Helpers default-populate columns/rows from the controller's `default_list_data()` and derive kanban columns from a Link/Select field's options. `check_permission`: Administrator/System Manager edit anything; public views editable by Sales Manager; private views only by owner.

## 28. CRM Dashboard
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · **autoname:** `field:title` (unique) · `title_field = title`. Controller body `pass`.
- Saved dashboard layouts (grid of charts). Layout is a JSON array of widget descriptors.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| title | Data | Name | — | 0 | 0 | — | 0 | — | — | *(unique)* |
| private | Check | Private | — | 0 | 0 | 0 | 0 | — | — |
| user | Link | User | User | 0 | 0 | — | 0 | `private` | — | *(mandatory if private)* |
| layout | Code (JSON) | Layout | — | 0 | 0 | `[]` | 0 | — | — |

**Controller logic:** module-level `default_manager_dashboard_layout()` returns a large hard-coded JSON describing the "Manager Dashboard" widgets (number/axis/donut charts: total_leads, ongoing_deals, won_deals, sales_trend, funnel_conversion, deals_by_territory, etc.). `create_default_manager_dashboard(force)` seeds/refreshes a `CRM Dashboard` named "Manager Dashboard".

## 29. CRM Notification
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · default autoname (`hash`). In-app notifications (mentions, task, assignment, whatsapp).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| notification_text | Text | Notification Text | — | 0 | 0 | — | 0 | — | — |
| from_user | Link | From User | User | 0 | 0 | — | 0 | — | — |
| type | Select | Type | `Mention / Task / Assignment / WhatsApp` | 1 | 0 | — | 1 | — | — |
| to_user | Link | To User | User | 1 | 0 | — | 1 | — | — |
| read | Check | Read | — | 0 | 0 | 0 | 0 | — | — |
| reference_doctype | Link | Reference Doctype | DocType | 0 | 0 | — | 0 | — | — |
| reference_name | Dynamic Link | Reference Doc | (→ `reference_doctype`) | 0 | 0 | — | 0 | — | — |
| notification_type_doctype | Link | Notification Type Doctype | DocType | 0 | 0 | — | 0 | — | — |
| notification_type_doc | Dynamic Link | Notification Type Doc | (→ `notification_type_doctype`) | 0 | 0 | — | 0 | — | — |
| comment | Link | Comment | Comment | 0 | 0 | — | 0 | — | — | *(hidden)* |
| message | HTML Editor | Message | — | 0 | 0 | — | 1 | — | — |

**Controller logic:** `on_update` publishes realtime event `crm_notification` to `to_user`. Module func `notify_user(notification)` de-dupes and inserts a notification (skips if owner == assignee).

## 30. CRM Invitation
- **Module:** FCRM · **istable:** 0 · **issingle:** 0 · default autoname. User-invite flow (email invite to join CRM with a role).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| email | Data | Email | — | 1 | 0 | — | 1 | — | — |
| role | Select | Role | `'' / Sales User / Sales Manager / System Manager` | 1 | 0 | — | 1 | — | — |
| key | Data | Key | — | 0 | 0 | — | 0 | — | — | *(generated hash, len 12)* |
| invited_by | Link | Invited By | User | 0 | 0 | — | 1 | — | — | *(= session user)* |
| status | Select | Status | `'' / Pending / Accepted / Expired` | 0 | 0 | — | 1 | — | — |
| email_sent_at | Datetime | Email Sent At | — | 0 | 0 | — | 0 | — | — |
| accepted_at | Datetime | Accepted At | — | 0 | 0 | — | 0 | — | — |

**Controller logic:** `before_insert` validates email, generates `key`, sets `invited_by`=session user, `status`=Pending. `after_insert` emails the invite link (`/api/method/crm.api.accept_invitation?key=...`) and stamps `email_sent_at`. Whitelisted `accept_invitation`/`accept`: create the User if missing, append the chosen role plus implied roles (System Manager ⇒ +Sales Manager +Sales User; Sales Manager ⇒ +Sales User; Sales User ⇒ restrict block_modules to FCRM), mark Accepted with `accepted_at`. Module func `expire_invitations()` flips Pending → Expired after 3 days (scheduled).

---

## 31. Facebook Page
- **Module:** Lead Syncing · **istable:** 0 · **issingle:** 0 · **autoname:** `field:id` (the FB page id, unique) · `in_create: 1` (only created programmatically), `track_changes`, `title_field = page_name`. Controller `pass`.
- A Facebook Page fetched/stored when a Lead Sync Source is created. Links to Facebook Lead Form (link in `links`).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| page_name | Data | Page Name | — | 0 | 0 | — | 0 | — | — | *(title)* |
| account_id | Data | Account ID | — | 0 | 0 | — | 0 | — | — |
| category | Data | Category | — | 0 | 0 | — | 0 | — | — |
| id | Data | ID | — | 0 | 0 | — | 0 | — | — | *(unique; the name)* |
| access_token | Small Text | Access Token | — | 0 | 0 | — | 0 | — | — | *(page access token)* |

## 32. Facebook Lead Form
- **Module:** Lead Syncing · **istable:** 0 · **issingle:** 0 · **autoname:** `field:id` (FB form id, unique) · `in_create: 1`, `title_field = form_name`.
- A FB lead-gen form belonging to a Facebook Page, with a question→CRM-field mapping table.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| page | Link | Page | Facebook Page | 1 | 0 | — | 1 | — | — |
| id | Data | ID | — | 0 | 0 | — | 0 | — | — | *(unique; the name)* |
| form_name | Data | Form Name | — | 0 | 0 | — | 0 | — | — | *(title)* |
| questions | Table | Questions | Facebook Lead Form Question | 0 | 0 | — | 0 | — | — |

**Controller logic:** `validate` → `check_mandatory_crm_fields_mapped`: on update, ensure at least the mandatory CRM Lead field(s) (currently only `first_name`) are mapped by some question's `mapped_to_crm_field`; throw otherwise.

## 33. Facebook Lead Form Question  **[CHILD]**
- **Module:** Lead Syncing · **istable:** 1. Child of Facebook Lead Form `questions`. Controller — none of note (`editable_grid`).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| label | Data | Label | — | 0 | 0 | — | 1 | — | — |
| key | Data | Key | — | 1 | 0 | — | 1 | — | — |
| type | Data | Type | — | 0 | 0 | — | 1 | — | — |
| id | Data | ID | — | 0 | 0 | — | 0 | — | — |
| mapped_to_crm_field | Autocomplete | Mapped to CRM Field | — | 0 | 0 | — | 1 | — | — | *(target CRM Lead fieldname)* |

## 34. Lead Sync Source
- **Module:** Lead Syncing · **istable:** 0 · **issingle:** 0 · **autoname:** `prompt` (user-named) · `track_changes`. Links to Failed Lead Sync Log (`source`).
- A configured lead-sync integration (currently Facebook only) with a background sync schedule.

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| type | Select | Type | `Facebook` | 1 | 0 | Facebook | 1 | — | — |
| access_token | Password | Access Token | — | 1 | 0 | — | 0 | — | — | *(length 500)* |
| last_synced_at | Datetime | Last Synced At | — | 0 | 1 | — | 0 | — | — |
| enabled | Check | Enabled? | — | 0 | 0 | 1 | 0 | — | — |
| background_sync_frequency | Select | Background Sync Frequency | `Every 5 Minutes / Every 10 Minutes / Every 15 Minutes / Hourly / Daily / Monthly` | 1 | 0 | Hourly | 0 | — | — |
| facebook_page | Link | Facebook Page | Facebook Page | 0 | 0 | — | 0 | `eval:doc.type==="Facebook"` | — |
| facebook_lead_form | Link | Facebook Lead Form | Facebook Lead Form | 0 | 0 | — | 0 | `eval:doc.type==="Facebook"` | — | *(unique)* |

**Controller logic:** `validate` → only one enabled source per `facebook_lead_form`. `before_insert` → for Facebook, call `fetch_and_store_pages_from_facebook(access_token)` (populates Facebook Page records). Whitelisted `sync_leads()` → enqueues `_sync_leads` (long queue, or sync in dev mode), which runs `FacebookSyncSource(token, form).sync()`. **Go note:** the heavy lifting lives in `crm/lead_syncing/doctype/lead_sync_source/facebook.py` (`FacebookSyncSource`, `fetch_and_store_pages_from_facebook`) — a Facebook Graph API client (not a doctype; out of this doc's strict scope but required to reimplement the sync).

## 35. Failed Lead Sync Log
- **Module:** Lead Syncing · **istable:** 0 · **issingle:** 0 · default autoname · `in_create: 1`. Logs each lead-sync outcome (duplicate / failure / synced).

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on | fetch_from |
|---|---|---|---|---|---|---|---|---|---|
| type | Select | Type | `Duplicate / Failure / Synced` | 0 | 1 | Failure | 1 | — | — | *(in_standard_filter)* |
| source | Link | Source | Lead Sync Source | 0 | 1 | — | 1 | — | — | *(in_standard_filter)* |
| lead_data | Code (JSON) | Lead Data | — | 0 | 1 | — | 0 | — | — | *(raw lead payload)* |
| traceback | Code | Traceback | — | 0 | 1 | — | 0 | — | — |

**Controller logic:** Whitelisted `retry_sync()` — re-attempts syncing the stored `lead_data` via `FacebookSyncSource(...).sync_single_lead(...)`; on success sets `type` = Synced.

---

## Cross-references / relationship summary
- **SLA graph:** CRM Service Level Agreement —has-many→ CRM Service Level Priority (priority → CRM Communication Status; first_response_time in seconds) and CRM Service Day (working hours); —link→ CRM Holiday List —has-many→ CRM Holiday. SLA runtime writes onto CRM Lead/CRM Deal (`sla_status`, `response_by`, `first_response_time`, etc.) and their `rolling_responses` (CRM Rolling Response Time) child rows. Status transitions captured in CRM Status Change Log child rows.
- **Telephony:** CRM Telephony Agent (one per user) —has-many→ CRM Telephony Phone; medium configured by the two Single settings CRM Twilio Settings / CRM Exotel Settings.
- **Dropdown/Branding/Currency:** FCRM Settings (Single) —has-many→ CRM Dropdown Item; toggles forecasting by editing CRM Fields Layout + Property Setters; forecasting Form Script copies CRM Deal Status.probability onto deals.
- **ERPNext bridge:** ERPNext CRM Settings (Single) drives Customer/Quotation/Prospect creation in ERPNext and installs a CRM Form Script.
- **Lead syncing:** Lead Sync Source —link→ Facebook Page & Facebook Lead Form (—has-many→ Facebook Lead Form Question); outcomes recorded in Failed Lead Sync Log.
