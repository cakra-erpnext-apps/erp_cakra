# Frappe CRM — Backend / API Logic Spec (for Go rebuild)

This document maps the Python backend of the Frappe CRM app (`crm/crm/`) to a
language-agnostic API + business-logic spec. Each whitelisted Python function
(`@frappe.whitelist()`) becomes an HTTP endpoint. In Frappe the calling
convention is:

```
POST/GET /api/method/<dotted.path>
```

with arguments passed as form/query params or JSON body. Return value is JSON
under `{"message": <return>}`. `allow_guest=True` means **no auth required**.
Functions without it require a valid session cookie/token. Date params are
`YYYY-MM-DD` strings; "dict"/"list" params are typically JSON-encoded strings
that the function parses with `frappe.parse_json`.

Cross-cutting concepts the Go rebuild must implement:

- **Meta**: every doctype has a schema (`frappe.get_meta`) listing fields with
  `fieldname`, `fieldtype`, `label`, `options`, `hidden`, `in_standard_filter`.
  Many endpoints introspect meta.
- **`no_value_fields`**: layout/section fieldtypes that hold no data
  (`Section Break`, `Column Break`, `Tab Break`, `HTML`, `Button`, `Heading`,
  `Fold`, `Table`, `Table MultiSelect`...). Filtered out in field listings.
- **`@me` substitution**: in filters, literal `"@me"` → current user;
  `"%@me%"` → `"%" + user + "%"` (used for `_assign LIKE`).
- **`_assign`**: JSON-array string column on every doc holding assigned user
  emails. `_liked_by`, `_comments`, `_user_tags` are similar meta columns.
- **Permissions**: `frappe.has_permission(doctype, ptype, name)`. Custom
  query-conditions and has_permission hooks for CRM Quotation/Estimation
  (see Hooks section).
- **CRM roles**: `System Manager`, `Sales Manager`, `Sales User`. Most CRM
  resources require one of these.

---

## api/__init__.py  (`crm.api.*`)

| Endpoint (dotted path) | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.get_translations` | guest | — | dict of translations | Returns all translations for the user's language (or System Settings language for Guest). |
| `crm.api.get_user_signature` | auth | — | HTML string or None | Returns current user's `email_signature`, else default outgoing Email Account signature, wrapped in `<p class="signature">`. |
| `crm.api.check_app_permission` | (helper, used by `add_to_apps_screen`) | — | bool | True for Administrator; else requires `FCRM` module access AND one of System Manager / Sales User / Sales Manager. |
| `crm.api.accept_invitation` | guest | `key` (str, req) | redirect | Looks up `CRM Invitation` by `key`, calls `.accept()`; on success logs the user in and redirects to `/crm`. |
| `crm.api.invite_by_email` | auth | `emails` (str, req), `role` (str, req) | `{existing_members, existing_invites, to_invite}` | Only Sales Manager/System Manager. Validates role (System/Sales Manager require System Manager). Splits emails, skips existing users/invites, creates `CRM Invitation` per new email. |
| `crm.api.delete_attachment` | DELETE/POST | `doctype` (str), `docname` (str), `file_url` (str) | — | Requires `write` perm on doc. Finds `File` by url+attached_to and deletes it. |
| `crm.api.get_file_uploader_defaults` | auth | `doctype` (str) | `{allowed_file_types, max_file_size, max_number_of_files, make_attachments_public}` | Reads allowed extensions/size from System Settings and meta `max_attachments`/`make_attachments_public`. |

---

## api/doc.py  (`crm.api.doc.*`) — GENERIC DOCUMENT / LIST ENGINE (CRITICAL)

This is the engine behind every list view, kanban, group-by, and filter UI.
Replicate signatures and response shapes exactly.

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.doc.sort_options` | auth | `doctype` (str) | list of `{label,value,fieldname}` | All non-`no_value` meta fields + standard fields (name, creation, modified, modified_by, owner) for the sort dropdown. |
| `crm.api.doc.get_filterable_fields` | auth | `doctype` (str) | list of field dicts | Fields whose fieldtype is in an allowed filter set (Check, Data, Float, Int, Currency, Link, Dynamic Link, Select, text types, Duration, Rating, Date, Datetime). Appends standard fields (name, owner=Created By, modified_by=Last Updated By, `_user_tags`=Tags, `_liked_by`=Like, `_comments`, `_assign`=Assigned To, creation, modified). Excludes controller's `get_non_filterable_fields()`. |
| `crm.api.doc.get_group_by_fields` | auth | `doctype` (str) | list of `{label,fieldname}` | Like above but allowed types for group-by (Check, Data, Float, Int, Currency, Link, Dynamic Link, Select, Duration, Date, Datetime) + standard fields incl. `_liked_by`, `_assign`, `_comments`. |
| `crm.api.doc.get_quick_filters` | auth | `doctype` (str), `cached` (bool=True) | list of `{label,fieldname,fieldtype,options}` | If a `CRM Global Settings` row (type "Quick Filters") exists for the doctype, use its JSON list of fieldnames; else fields with `in_standard_filter=1`. Select options split on newline into `{label,value}`. For `CRM Lead`, removes `converted`. |
| `crm.api.doc.update_quick_filters` | auth | `quick_filters` (JSON str), `old_filters` (JSON str), `doctype` (str) | — | Diffs new vs old. Writes/creates `CRM Global Settings` (type Quick Filters) JSON. Sets `in_standard_filter` Property Setter to 1 for added, 0 for removed fields. |
| `crm.api.doc.get_data` | auth | see below | big dict (see below) | **MAIN list/kanban/group-by endpoint.** |
| `crm.api.doc.remove_assignments` | auth | `doctype`, `name`, `assignees` (JSON list), `ignore_permissions` (bool=False) | — | For each assignee, `set_status(..., status="Cancelled")` (un-assign via ToDo). |
| `crm.api.doc.get_assigned_users` | auth | `doctype`, `name`, `default_assigned_to` (str?) | list[str] | Distinct `ToDo.allocated_to` where reference=doc and status≠Cancelled; falls back to `[default_assigned_to]` if empty. |
| `crm.api.doc.get_fields` | auth | `doctype`, `allow_all_fieldtypes` (bool=False) | list of field dicts | Meta fields, excluding `no_value_fields` + `Read Only` (unless allow_all). |
| `crm.api.doc.get_linked_docs_of_document` | auth | `doctype`, `docname` | list of `{doc,title,reference_docname,reference_doctype}` | Uses Frappe `get_linked_docs` + `get_dynamic_linked_docs`, dedups by docname, builds titles (Call Log → "Call from X to Y", Deal → organization, Notification → message). |
| `crm.api.doc.remove_linked_doc_reference` | auth | `items` (JSON list of `{doctype,docname}`), `remove_contact` (bool=False), `delete` (bool=False) | "success" | For each item with write perm: clears `reference_doctype`/`reference_docname` (or `contact`/`contacts` if remove_contact); optionally deletes the doc. Special handling for `CRM Notification`. |
| `crm.api.doc.delete_bulk_docs` | auth | `doctype`, `items` (JSON list), `delete_linked` (bool=False) | "success" | Validates list. For each doc, finds linked docs and clears/deletes their references. Deletes via `delete_bulk`; if >10 items, enqueues background job. |

### `get_data` — full signature

```
get_data(
  doctype: str,
  filters: dict,
  order_by: str,
  page_length: int = 20,
  page_length_count: int = 20,
  column_field: str | None = None,   # kanban column grouping field
  title_field: str | None = None,    # kanban card title field
  columns: str|list|None = None,     # JSON: [{label,type,key,width}]
  rows: str|list|None = None,        # JSON: ["fieldname", ...]
  kanban_columns: str|list|None = None,
  kanban_fields: str|list|None = None,
  view: str|dict|None = None,        # {custom_view_name, view_type, group_by_field}
  default_filters: dict|None = None,
)
```

**Behavior:**
1. Parse JSON-ish args. Apply `@me`/`%@me%` substitution in `filters`. Merge `default_filters`.
2. `view_type` ∈ {None/"list", "kanban", "group_by"}. `group_by_field` from `view`.
3. Resolve columns/rows:
   - If `columns` or `rows` passed → custom view (not default).
   - Else if a standard `CRM View Settings` row exists for `{dt, type=view_type|"list", is_standard=1, user}` → use its columns/rows.
   - Else if controller has `default_list_data()` → use that. Default fallback columns = Name + Last Modified; default rows = `["name"]`.
   - Ensure every column.key is in rows; translate labels; drop hidden columns; shrink `_liked_by` width to 50px; append `group_by_field` to rows.
4. **List**: `frappe.get_list(doctype, fields=rows, filters, order_by, page_length)`, then `parse_list_data` (calls controller's `parse_list_data` if present).
5. **Kanban** (`view_type=="kanban"`): derive `kanban_columns` from `column_field` (Link → all options docs; Select → option list). For each column: build `column_filters = {column_field: col} + filters`, fetch records (ordered list or by explicit `order` array via `get_records_based_on_order`), compute `all_count` and per-record counts (`getCounts`). Each entry: `{column, fields, data}`.
6. **Group-by** (`view_type=="group_by"`): builds `group_by_field` dict with computed `options` (Select → split options; else distinct values from data, sorted per `order_by`).
7. Always returns the `fields` list (meta fields + std fields name/creation/modified/modified_by/_assign/owner/_liked_by).

**Returns:**
```
{
  data, columns, rows, fields,
  column_field, title_field, kanban_columns, kanban_fields,
  group_by_field, page_length, page_length_count,
  is_default (bool),
  views: get_views(doctype),
  total_count: COUNT(name) over filters,
  row_count: len(data),
  form_script: get_form_script(doctype),       # Form-view client script
  list_script: get_form_script(doctype,"List"),# List-view client script
  view_type,
}
```

**`getCounts(d, doctype)`** adds per-row counts:
- `_email_count` = Communication (type Communication + Automated Message) for the doc
- `_comment_count` = Comment (comment_type=Comment)
- `_task_count` = CRM Task (reference_docname)
- `_note_count` = FCRM Note (reference_docname)

`COUNT_NAME` is version-aware (`{"COUNT":"name","as":"total_count"}` on Frappe ≥16, else `"count(name) as total_count"`).

---

## api/views.py  (`crm.api.views.*`)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.views.get_views` | auth | `doctype` (str) | list of `CRM View Settings` rows | All view-setting rows where `user == ""` (shared/global) OR `user == current user`, filtered by `dt == doctype`. (Note: `CRM View Settings` doctype itself has list/kanban/group_by saved views with columns, rows, filters, order_by, load_default_columns, is_standard, public, pinned.) |

---

## api/activities.py  (`crm.api.activities.*`)

Only `get_activities` is whitelisted; the rest are internal helpers that build
the activity timeline. The Go rebuild needs the full timeline assembly logic.

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.activities.get_activities` | auth | `name` (str) | `(activities, calls, notes, tasks, attachments)` tuple | Dispatches on whichever doctype `name` exists in: CRM Deal → CRM Lead → CRM Quotation → CRM Estimation; else 404. |

**Timeline assembly (per `get_*_activities`)** — must be replicated:
- Requires `read` perm. Loads `get_docinfo` (versions, comments, communications, automated_messages, attachment_logs).
- Emits a synthetic `creation` activity ("created this lead/deal/...". For a deal converted from a lead: prepends the lead's full activity history and uses "converted the lead to this deal").
- **Versions** (field-change log): reads `version.data.changed[0]` → emits `changed`/`added`/`removed` activity with `{field, field_label, old_value, value}`. Skips `avoid_fields` (per doctype: SLA/audit/converted fields; quotation skips `create_uid/create_date/write_uid/write_date`; estimation skips `created_by/create_date/last_mod_by/last_mod`). Translates option values for translatable link doctypes.
- **Comments**: `{name, activity_type:"comment", content, attachments}`.
- **Communications + automated_messages**: subject/content/sender/recipients/cc/bcc/attachments/read_by_recipient/delivery_status.
- **Attachment logs**: parsed via `parse_attachment_log` (BeautifulSoup `<a>` → added/removed + file_name/file_url/is_private).
- Appends linked **calls** (`CRM Call Log` by reference_docname + via `Dynamic Link`), **notes** (`FCRM Note`), **tasks** (`CRM Task`), plus notes/tasks linked through call logs.
- Sorts by `creation` desc, then `handle_multiple_versions` groups consecutive same-owner version edits into one (`other_versions` array).

Helper internals (not endpoints) the Go side reimplements: `get_attachments`, `get_linked_calls`, `get_linked_notes`, `get_linked_tasks`, `parse_call_log` (from CRM Call Log controller), `parse_attachment_log`, `is_translatable`.

---

## api/dashboard.py  (`crm.api.dashboard.*`)

Two whitelisted entry points + many internal `get_<chart>` builders dispatched by name.

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.dashboard.reset_to_default` | auth | — | — | System Manager only. `create_default_manager_dashboard(force=True)`. |
| `crm.api.dashboard.get_dashboard` | auth (`@sales_user_only`) | `from_date`, `to_date`, `user` (all opt) | list of layout blocks each with `data` | Defaults date range to current month. Sales Users forced to `user=self`. Loads `CRM Dashboard "Manager Dashboard".layout` (creates default if missing). For each layout item `l`, calls `get_<l.name>(from_date,to_date,user)` and attaches as `l["data"]`. |
| `crm.api.dashboard.get_chart` | auth (`@sales_user_only`) | `name` (str), `type` (str), `from_date`, `to_date`, `user` | one chart dict | Same date/user logic; dispatches to `get_<name>` builder; `{"error": "Invalid chart name"}` if unknown. |

**Chart builder functions** (internal, dispatched by name; each takes `from_date,to_date,user`):

| Builder | Output shape | Computation |
|---|---|---|
| `get_total_leads` | number-card `{title,tooltip,value,delta,deltaSuffix:"%"}` | Count CRM Lead in current vs previous equal-length period (by creation), % delta. user→`lead_owner`. |
| `get_ongoing_deals` | number-card % | Count CRM Deal joined CRM Deal Status, status type NOT IN (Won,Lost), current vs prev. |
| `get_average_ongoing_deal_value` | number-card (currency prefix) | Avg `deal_value * IfNull(exchange_rate,1)` of non Won/Lost deals. |
| `get_won_deals` | number-card % | Count deals with status type Won by `closed_date`, current vs prev. |
| `get_average_won_deal_value` | number-card (currency) | Avg deal value of Won deals (by closed_date). |
| `get_average_deal_value` | number-card (currency) | Avg deal value of ongoing+won (status type ≠ Lost) by creation. |
| `get_average_time_to_close_a_lead` | number-card (days, negativeIsBetter) | `TIMESTAMPDIFF(DAY, COALESCE(lead.creation, deal.creation), deal.closed_date)` averaged over Won deals. |
| `get_average_time_to_close_a_deal` | number-card (days) | Same but from deal.creation only. |
| `get_sales_trend` | line chart (time x-axis) | Per-day counts of leads, deals, won_deals via UNION ALL of two grouped queries, aggregated by date. |
| `get_forecasted_revenue` | line chart (monthly) | Per `expected_closure_date` month (last 12 mo): forecasted = expected_deal_value × (Lost→1 else probability/100) × exchange_rate; actual = deal_value×rate for Won. |
| `get_funnel_conversion` | bar (swapXY) | "Leads" total + `get_deal_status_change_counts` (status-change log counts per target status, ordered by status position, excluding currently-Lost deals). |
| `get_deals_by_stage_axis` | bar | Count deals grouped by status (excl. Lost), desc. |
| `get_deals_by_stage_donut` | donut | Count deals grouped by status (incl. all). |
| `get_lost_deal_reasons` | bar | Count Lost deals grouped by `lost_reason` (non-empty). |
| `get_leads_by_source` | donut | Count leads grouped by `source` (null→"Empty"). |
| `get_deals_by_source` | donut | Count deals grouped by `source`. |
| `get_deals_by_territory` | bar+line | Per territory: deals count + Σ(deal_value×rate). |
| `get_deals_by_salesperson` | bar+line | Per `deal_owner` (LEFT JOIN User for full_name): count + Σ value. |

Helpers: `get_base_currency_symbol()` (FCRM Settings.currency → Currency.symbol), `get_deal_status_change_counts()` (joins CRM Status Change Log → CRM Deal → CRM Deal Status). Custom pypika function `TimestampDiff` wraps SQL `TIMESTAMPDIFF`. All `user` filters narrow to that owner; date filters use `[from_date, to_date]` inclusive (current period uses `< to_date+1` half-open).

---

## api/comment.py  (`crm.api.comment.*`)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.comment.add_comment` | auth | `reference_doctype`, `reference_name`, `content` (HTML), `attachments` (list?) | Comment doc | Wraps frappe `add_comment` with current user as author. Attaches files (by File name, or `{fname,fcontent}` dicts) to the Comment. |

Non-endpoint hooks: `on_update(self,method)` → `notify_mentions` (parses `<span data-type="mention">` for emails, sends `CRM Notification` type "Mention" to each mentioned user, with HTML notification text referencing the lead/deal name). `extract_mentions`, `add_attachments` helpers.

---

## api/contact.py  (`crm.api.contact.*`)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.contact.get_linked_deals` | auth | `contact` (str) | list of CRM Deal dicts | Requires `read` on Contact. Finds CRM Deal parents via `CRM Contacts` child rows; returns deal core fields. |
| `crm.api.contact.create_new` | auth | `contact`, `field` ("email"/"mobile_no"/"phone"), `value` | True | Requires `write`. Appends a new email_id or phone_no child row (first one auto-primary). |
| `crm.api.contact.set_as_primary` | auth | `contact`, `field`, `value` | True | Requires `write`. Sets matching email/phone as primary, unsets others. |
| `crm.api.contact.search_emails` | auth | `txt` (str) | list of `[full_name,email_id,name]` | Searches Contacts with an email set, enabled, `like %txt%` on full_name/email_id/name, limit 20. |

Non-endpoint hook: `validate(doc,method)` → `update_deals_email_mobile_no`: when a Contact is saved, syncs `email`/`mobile_no` onto every CRM Deal where it is the primary contact.

---

## api/notifications.py  (`crm.api.notifications.*`)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.notifications.get_notifications` | auth | — | list of notification dicts | All `CRM Notification` where `to_user==current user`, newest first. Enriches with from_user full_name, a UI `hash` (`#whatsapp`, `#tasks`, `#<doc>` for mentions), maps `reference_doctype` CRM Deal→"deal"/else "lead" and route_name "Deal"/"Lead". |
| `crm.api.notifications.mark_as_read` | auth | `user` (opt), `doc` (opt) | — | Marks unread notifications read for the user; if `doc` given, or-filters on `comment`/`notification_type_doc`. |

---

## api/todo.py  (`crm.api.todo.*`)

No whitelisted endpoints — pure `ToDo` doc_event hooks (registered in hooks.py):
- `after_insert`: if ToDo references CRM Lead/Deal and the owner field (`lead_owner`/`deal_owner`) is empty, set it to `allocated_to`. For Lead/Deal/Task, `notify_assigned_user` (sends `CRM Notification` type "Assignment" with HTML text).
- `on_update`: if status changed to "Cancelled" on a Lead/Deal/Task assignment → `notify_assigned_user(is_cancelled=True)` ("assignment removed by …").
- `get_redirect_to_doc`: for CRM Task, redirect target is the task's own `reference_doctype/reference_docname`.

---

## api/user.py  (`crm.api.user.*`)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.user.change_password` | auth, **rate-limited 5/5min** | `old_password`, `new_password` | success msg | Uses `LoginAttemptTracker` for lockout. Rejects same-as-old, checks old password, enforces password-strength policy, then `update_password`. |
| `crm.api.user.add_existing_users` | auth | `users` (JSON list), `role` (default "Sales User") | — | System/Sales Manager only. Only System Manager may grant System/Sales Manager. Calls `update_user_role` per user. |
| `crm.api.user.update_user_role` | auth | `user`, `new_role` | — | Validates role; System-Manager-only escalations. Appends role hierarchy (System Manager ⊃ Sales Manager ⊃ Sales User), adjusts `block_modules` so Sales User only sees FCRM. |
| `crm.api.user.remove_crm_roles_from_user` | auth | `user` | — | System/Sales Manager only; can't remove self; blocks if Role Profile assigned. Removes Sales User/Manager (and System Manager only by a System Manager), re-blocks modules. |

---

## api/session.py  (`crm.api.session.*`)

`get_session_role_flags()` (helper) throws PermissionError unless user has a CRM role; returns `{is_system_manager,is_sales_manager,is_sales_user}`.

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.session.get_users` | auth | — | `(users, crm_users)` tuple | Enabled Users with role label resolved (System Manager > Sales Manager > Sales User > Guest), `is_telephony_agent`, language. `crm_users` = those with a CRM role. Non-System-Managers only see `crm_users`. |
| `crm.api.session.get_organizations` | auth | — | list of `CRM Organization` | All organizations (requires CRM role). |

---

## api/settings.py  (`crm.api.settings.*`)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.settings.create_email_account` | auth | `data` (dict) | None / error str | Creates an `Email Account` for a known service (Frappe Mail / GMail / Outlook / Sendgrid / SparkPost / Yahoo / Yandex) merging a per-service config preset. Non-Frappe-Mail services validate IMAP creds via `get_incoming_server()` before save; appends `CRM Lead` to `append_to`/imap_folder. |

`email_service_config` constant holds the IMAP/SMTP host/port/SSL presets per service — seed this table in Go.

---

## api/quotation.py  (`crm.api.quotation.*`)  — user customization (Indonesian comments)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.quotation.get_available_inquiries` | auth | `search` (opt) | list of CRM Deal | Deals with status "Won" not already used as a Quotation `inquiry`; optional org `like` search; limit 50. ("Inquiry" = relabeled Deal.) |
| `crm.api.quotation.get_inquiry_detail` | auth | `name` (CRM Deal) | dict | Returns deal summary for the Quotation sidebar: org, status, owner, primary contact (+ fresh full_name from Contact), email, mobile, territory, source, currency, deal_value. |
| `crm.api.quotation.get_quotation_contacts` | auth | `name` (CRM Quotation) | list of contact dicts | Contacts whose `company_name == quotation.account`, with primary email/phone resolved. |

---

## api/void.py  (`crm.api.void.*`)  — user customization

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.void.void_document` | auth | `doctype` (CRM Quotation/Lead/Deal), `name`, `void` (int=1), `reason` (opt) | `{is_void,void_by,void_at,void_reason}` | Soft-cancel (reversible). Requires `write`. Sets `is_void`, and when voiding stamps `void_reason/void_at/void_by`; un-voiding clears them. `VOIDABLE = {CRM Quotation, CRM Lead, CRM Deal}`. |

---

## api/permissions.py  (`crm.api.permissions.*`)  — user customization (assignment-based access)

Not HTTP endpoints — referenced by `permission_query_conditions` and
`has_permission` hooks. **Core access rule to replicate in Go:**

- `BYPASS_ROLES = {System Manager, Sales Manager}` (+ Administrator) → see ALL rows.
- Otherwise a user may only see/open a document they **own** (`owner == user`)
  OR are **assigned** to (`_assign LIKE %user%` / user ∈ parsed `_assign`).
- `quotation_query_conditions` / `estimation_query_conditions` → SQL string
  `` (`tabX`.owner = 'user' OR `tabX`._assign LIKE '%user%') `` injected into list queries.
- `quotation_has_permission` / `estimation_has_permission` → per-document boolean for direct opens.

Applied to **CRM Quotation** and **CRM Estimation**.

---

## api/assignment_rule.py  (`crm.api.assignment_rule.*`)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.assignment_rule.get_assignment_rules_list` | auth | — | list of rule dicts | `Assignment Rule`s for CRM Lead/Deal with `{name,description,disabled,priority,users_exists}`. |
| `crm.api.assignment_rule.duplicate_assignment_rule` | auth | `docname`, `new_name` | new doc | Clones an Assignment Rule under a new name. |

---

## api/auth.py  (`crm.api.auth.*`)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.auth.oauth_providers` | guest | — | list of `{name,provider_name,auth_url,icon}` | Enabled Social Login Keys with a client secret; builds OAuth2 authorize URL redirecting to `/crm`. |

---

## api/exchange_rate.py  (`crm.api.exchange_rate.*`)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.exchange_rate.get_exchange_rate` | auth | `from_currency`, `to_currency`, `date` (opt) | float rate | Caches by `exchange_rate_{from}_{to}_{date}` ("latest" keyed by today). Dispatches by FCRM Settings `service_provider`: paid (exchangerate.host, exchangerate-api — need access_key) fail explicitly; free (frankfurter.app, fawazahmed-exchange-api) fall back to each other. Raises a manager-targeted error if conversion unsupported. |

Internal fetchers: `_fetch_from_frankfurter`, `_fetch_from_fawaz_api`, `_fetch_from_exchangerate_host`, `_fetch_from_exchangerate_api`. The Go rebuild should keep the same provider list + fallback chain + caching key.

---

## api/live_demo.py  (`crm.api.live_demo.*`)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.live_demo.login` | guest | — | redirect | Logs in using `frappe.conf.demo_username/demo_password` (if configured), redirects to `/crm`. |

Non-endpoint hooks (User doc events): `validate_reset_password`, `validate_user` block the demo user from changing its password.

---

## api/onboarding.py  (`crm.api.onboarding.*`)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `crm.api.onboarding.get_first_lead` | auth | — | name or None | Oldest unconverted CRM Lead. |
| `crm.api.onboarding.get_first_deal` | auth | — | name or None | Oldest CRM Deal. |

---

## api/whatsapp.py  (`crm.api.whatsapp.*`)

Requires one of `System Manager / Sales Manager / Sales User` (`validate_access`). Depends on the optional `frappe_whatsapp` app's doctypes (WhatsApp Message/Templates/Settings/Account).

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `is_whatsapp_enabled` | auth | — | bool | True if WhatsApp Settings exist, a default outgoing account is set, and that account status is "Active". |
| `is_whatsapp_installed` | auth | — | bool | Whether `WhatsApp Settings` doctype exists. |
| `get_whatsapp_messages` | auth | `reference_doctype`, `reference_name` | list of message dicts | Returns WhatsApp Messages for the doc (and, for a CRM Deal, its source CRM Lead's). Resolves template bodies (param substitution `{{n}}`), attaches reactions, reply context, and `from_name`. Excludes reaction rows from the final list. Returns `[]` if `twilio_integration` app present. |
| `create_whatsapp_message` | auth | `reference_doctype`, `reference_name`, `message`, `to`, `attach`, `reply_to`, `content_type`="text" | new doc name | Creates a WhatsApp Message (optionally a reply). |
| `send_whatsapp_template` | auth | `reference_doctype`, `reference_name`, `template`, `to` | new doc name | Creates a Template-type WhatsApp Message. |
| `react_on_whatsapp_message` | auth | `emoji`, `reply_to_name` | new doc name | Creates a `reaction` content-type message replying to an existing message. |

Non-endpoint hooks: `validate(doc)` resolves the message's contact/lead/deal from the phone number and sets `reference_doctype/name`. `on_update(doc)` publishes realtime `whatsapp_message` and notifies assigned users of incoming messages (`CRM Notification` type "WhatsApp"). `add_roles()` (after_migrate) grants WhatsApp doctype perms to Sales roles.

---

## integrations/api.py  (`crm.integrations.api.*`)  — telephony (Twilio/Exotel shared)

| Endpoint | Method | Params | Returns | Logic |
|---|---|---|---|---|
| `is_call_integration_enabled` | auth | — | `{integrations:{twilio,exotel}, default_calling_medium}` | Reads `CRM Twilio Settings.enabled`, `CRM Exotel Settings.enabled`, and the user's `CRM Telephony Agent.default_medium`. |
| `set_default_calling_medium` | auth | `medium` | default medium | Creates/updates the user's `CRM Telephony Agent.default_medium`. |
| `add_note_to_call_log` | auth | `call_sid`, `note` (dict) | FCRM Note | Creates/updates an FCRM Note and links it to the call log. |
| `add_task_to_call_log` | auth | `call_sid`, `task` (dict) | CRM Task | Creates/updates a CRM Task and links it to the call log. |
| `get_contact_lead_or_deal_from_number` | auth | `number` | `(docname, doctype)` | Resolves a phone number to Contact → its CRM Lead/Deal. |
| `get_contact_by_phone_number` | auth | `phone_number` | contact dict | Parses number; matches Contact (normalized digits `LIKE`), attaches linked deal/lead; falls back to unmatched `{mobile_no}`. |
| `get_recording_url` | auth | `call_log_name` | streamed audio (audio/mpeg) | Fetches the provider recording using Twilio/Exotel credentials and streams it. |

## integrations/exotel/handler.py  (`crm.integrations.exotel.handler.*`)

| Endpoint | Method | Params | Logic |
|---|---|---|---|
| `handle_request` | **guest** (webhook, `?key=` verify token) | `**kwargs` | Incoming-call webhook: validates token, logs request, creates/updates `CRM Call Log`, publishes realtime `exotel_call`. |
| `make_a_call` | auth | `to_number`, `from_number?`, `caller_id?` | Outgoing call via Exotel API; validates exophone/agent mobile; creates Outgoing call log. |
| `is_integration_enabled` | auth | — | `CRM Exotel Settings.enabled`. |

## integrations/twilio/api.py  (`crm.integrations.twilio.api.*`)

| Endpoint | Method | Params | Logic |
|---|---|---|---|
| `is_enabled` | auth | — | `CRM Twilio Settings.enabled`. |
| `generate_access_token` | auth | — | Voice SDK access token for the agent (needs mapped `twilio_number`). |
| `voice` | **guest** (webhook) | `**kwargs` | Returns TwiML dial instructions for outgoing client calls; creates call log. |
| `twilio_incoming_call_handler` | **guest** (webhook) | `**kwargs` | TwiML for incoming calls; creates call log. |
| `update_recording_info` | **guest** (webhook) | `**kwargs` | Saves recording URL to the call log. |
| `update_call_status_info` | **guest** (webhook) | `**kwargs` | Updates call status/duration; relays user-defined message. |

---

# Hooks & events  (`hooks.py`)

### `add_to_apps_screen`
One app card: name `crm`, route `/crm`, `has_permission = crm.api.check_app_permission`.

### `doc_events`
| Doctype | Event | Handler |
|---|---|---|
| Contact | validate | `crm.api.contact.validate` (sync email/mobile to primary deals) |
| ToDo | after_insert | `crm.api.todo.after_insert` (set owner, notify assignment) |
| ToDo | on_update | `crm.api.todo.on_update` (notify cancellation) |
| Communication | after_insert | `crm.utils.on_communication_insert` (auto-create Lead from incoming email) |
| Communication | on_update | `crm.utils.on_communication_update` (update modified / communication_status) |
| Comment | after_insert | `crm.utils.on_comment_insert` (bump parent modified) |
| Comment | on_update | `crm.api.comment.on_update` (notify @mentions) |
| WhatsApp Message | validate | `crm.api.whatsapp.validate` (resolve contact from number) |
| WhatsApp Message | on_update | `crm.api.whatsapp.on_update` (realtime + notify) |
| **CRM Deal** | on_update | `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.create_customer_in_erpnext` (ERPNext sync) |
| User | before_validate | `crm.api.live_demo.validate_user` (block demo pwd change) |
| User | validate_reset_password | `crm.api.live_demo.validate_reset_password` |

### `permission_query_conditions` (user customization — Indonesian comment)
- `CRM Quotation` → `crm.api.permissions.quotation_query_conditions`
- `CRM Estimation` → `crm.api.permissions.estimation_query_conditions`

### `has_permission` (user customization)
- `CRM Quotation` → `crm.api.permissions.quotation_has_permission`
- `CRM Estimation` → `crm.api.permissions.estimation_has_permission`

(Rule: Sales User sees only owned/assigned; Manager/Admin see all.)

### `override_doctype_class`
- `Contact` → `crm.overrides.contact.CustomContact` (adds `default_list_data`)
- `Email Template` → `crm.overrides.email_template.CustomEmailTemplate` (adds `default_list_data`)

### `scheduler_events` — lead syncing (`crm.lead_syncing.background_sync.*`)
- `daily_long` → `sync_leads_from_sources_daily`
- `hourly_long` → `sync_leads_from_sources_hourly`
- `monthly_long` → `sync_leads_from_sources_monthly`
- cron `*/5 * * * *` → `sync_leads_from_sources_5_minutes`
- cron `*/10 * * * *` → `sync_leads_from_sources_10_minutes`
- cron `*/15 * * * *` → `sync_leads_from_sources_15_minutes`

Each calls `sync_leads_from_all_enabled_sources(<frequency label>)`.

### Install / migrate / test hooks
- `before_install = crm.install.before_install` (no-op)
- `after_install = crm.install.after_install` (seeds everything — see next section)
- `before_uninstall = crm.uninstall.before_uninstall`
- `after_migrate = [crm.fcrm.doctype.fcrm_settings.fcrm_settings.after_migrate, crm.api.whatsapp.add_roles]`
- `setup_wizard_complete = crm.demo.api.create_demo_data` (demo data toggle)
- `get_site_info = crm.activation.get_site_info`
- `before_tests = crm.tests.before_tests`

### Website / routing
- `website_route_rules`: `/crm/<path:app_path>` → route `crm` (SPA fallback).
- `app_icon_route = /crm`, `app_icon_url = /assets/crm/images/logo.svg`.

### Jinja
Not configured (commented out). No custom jinja methods/filters.

### Fixtures (exported to git — note user customizations)
- `CRM Fields Layout` where `dt ∈ [CRM Quotation, CRM Lead, CRM Estimation]` (portable layouts).
- `Translation` where translated_text `like %Inquir%` (relabels Deal→"Inquiry" in UI).
- `CRM Lead Source` (all).
- `CRM Transportation Mode` (all) — multi-select on Inquiry.
- `Custom Field` `Item-item_category` (global Item category: Revenue/Expense/Stock/Asset/Sparepart).

### Misc hooks
- `ignore_links_on_delete = ["Failed Lead Sync Log"]`
- `standard_dropdown_items` = app_selector, settings, login_to_fc, about, separator, logout (top-right menu, seeded into FCRM Settings on install).
- `export_python_type_annotations = True`, `require_type_annotated_api_methods = True`.

---

# Seed / install data  (`install.py::after_install`)

The Go rebuild must seed these on first boot.

### CRM Lead Status  (`add_default_lead_statuses`)
`(status, color, type, position)`:
New/gray/Open/1, Contacted/orange/Ongoing/2, Nurture/blue/Ongoing/3,
Qualified/green/Won/4, Converted/teal/Won/5, Unqualified/red/Lost/6, Junk/purple/Lost/7.

### CRM Deal Status  (`add_default_deal_statuses`)
`(status, color, type, probability, position)`:
Qualification/gray/Open/10/1, Demo/Making/orange/Ongoing/25/2,
Proposal/Quotation/blue/Ongoing/50/3, Negotiation/yellow/Ongoing/70/4,
Ready to Close/purple/Ongoing/90/5, Won/green/Won/100/6, Lost/red/Lost/0/7.

### CRM Communication Status  (`add_default_communication_statuses`)
`Open`, `Replied`.

### CRM Industry  (`add_default_industries`)
~50 industries (Accounting, Advertising, Aerospace, Agriculture, Airline, Apparel & Accessories, Automotive, Banking, Biotechnology, Broadcasting, Brokerage, Chemical, Computer, Consulting, Consumer Products, Cosmetics, Defense, Department Stores, Education, Electronics, Energy, Entertainment & Leisure/Executive Search, Financial Services, Food, Beverage & Tobacco, Grocery, Health Care, Internet Publishing, Investment Banking, Legal, Manufacturing, Motion Picture & Video, Music, Newspaper Publishers, Online Auctions, Pension Funds, Pharmaceuticals, Private Equity, Publishing, Real Estate, Retail & Wholesale, Securities & Commodity Exchanges, Service, Soap & Detergent, Software, Sports, Technology, Telecommunications, Television, Transportation, Venture Capital).

### CRM Lead Source  (`add_default_lead_sources`)
Email, Existing Customer, Reference, Advertisement, Cold Calling, Exhibition, Supplier Reference, Mass Mailing, Customer's Vendor, Campaign, Walk In, Facebook, Website.

### CRM Lost Reason  (`add_default_lost_reasons`)
Pricing, Competition, Budget Constraints, Missing Features, Long Sales Cycle, No Decision-Maker, Unresponsive Prospect, Poor Fit, Other (each with a description).

### CRM Global Settings — Quick Filters  (`add_default_quick_filters`)
- CRM Lead: lead_name, email, organization, status, source
- CRM Deal: organization, status, probability, email
- Contact: status, email_id, phone
- CRM Organization: organization_name, no_of_employees, territory, industry
- CRM Task: title, priority, assigned_to, status, due_date
- CRM Call Log: telephony_medium, type, status, from, to

### CRM Fields Layout  (`add_default_fields_layout`, idempotent; `force` re-creates)
Three layout types per doctype (JSON layouts stored verbatim — copy from install.py):
- **Quick Entry**: CRM Lead, CRM Deal, Contact, CRM Organization, Address, CRM Call Log, FCRM Note, CRM Task.
- **Side Panel**: CRM Lead, CRM Deal, Contact, CRM Organization.
- **Data Fields**: CRM Lead, CRM Deal.

(CRM Quotation / CRM Estimation layouts come from the git **fixtures**, not install.py.)

### Property Setters
- `Contact-main-search_fields` = `email_id`.
- `in_standard_filter` toggles (created dynamically via quick-filter API).
- Assignment Rule: `assign_condition_json` / `unassign_condition_json` custom Code fields + `depends_on` property setters.

### Custom Fields
- Email Template: `enabled` (Check), `reference_doctype` (Link→DocType).
- Email Account: `create_lead_from_incoming_email` (Check).
- Assignment Rule: `assign_condition_json`, `unassign_condition_json` (Code).
- Item: `item_category` (via fixtures).

### Scripts & Dashboard
- `add_default_scripts`: product-details CRM Form Script for CRM Lead & CRM Deal + forecasting script.
- `create_default_manager_dashboard`: the "Manager Dashboard" `CRM Dashboard` layout (drives `get_dashboard`).
- `add_standard_dropdown_items`: seeds FCRM Settings dropdown menu from the `standard_dropdown_items` hook.

### Demo data
Seeded via `setup_wizard_complete = crm.demo.api.create_demo_data` (wizard-triggered, optional).

---

## utils/__init__.py  (`crm.utils`)

Shared helpers (mostly doc_event handlers + utilities), not endpoints:
- `parse_phone_number` / `are_same_phone_number` (libphonenumber, default region "IN", E164 compare).
- `seconds_to_duration` (e.g. `1h 2m 3s`).
- `is_admin`, `is_sales_user`, `sales_user_only` (decorator → PermissionError if not a sales user/admin).
- `is_frappe_version(version, above, below)` — version gating.
- `create_lead_from_incoming_email` (Communication after_insert): if the Email Account has `create_lead_from_incoming_email` and the inbound email's sender has no existing Lead, creates a `CRM Lead` (source "Email") and links the Communication.
- `on_communication_insert` / `on_communication_update`: bump parent `modified` and set `communication_status` (Open on Received / Replied on Sent) based on FCRM Settings toggles (`auto_reopen_on_new_communication`, `auto_mark_replied_on_response`, `update_timestamp_on_new_communication`).
- `on_comment_insert`: enqueues parent `modified` bump for Lead/Deal comments.

---

## overrides/

- **`CustomContact`** (overrides `Contact`): adds `default_list_data()` → list columns (Name/Email/Phone/Organization/Last Modified) + rows. Consumed by `get_data`.
- **`CustomEmailTemplate`** (overrides `Email Template`): adds `default_list_data()` → columns (Name/Subject/Enabled/Doctype/Last Modified) + rows.

These `default_list_data()` (and analogous `default_kanban_settings()`, `parse_list_data()`, `get_non_filterable_fields()`) methods on each CRM doctype controller are the per-doctype hooks the generic `get_data` engine calls — the Go rebuild needs a registry mapping doctype → these defaults.
