# 05 — Views, Lists, Forms (Display & Edit Layer)

Spec for rebuilding the Frappe CRM "how data is displayed and edited" layer in **Go**.
Covers: **List Views**, **Saved / View Settings**, the **Form Layout engine**, the **Field Controls catalog**, and **Form Scripts** (including the 3 custom file-based scripts).

Source of truth read directly from `D:\System_ERPNext\crm\frontend\src` (Vue 3) and `D:\System_ERPNext\crm\crm` (Frappe backend). All identifiers below are real.

---

## 1. LIST VIEWS

### 1.1 Architecture

Each list page (`src/pages/Leads.vue`, `Inquiries.vue`, `Contacts.vue`, `Organizations.vue`, `Quotations.vue`, `Estimations.vue`, `Tasks.vue`) is a thin wrapper that:

1. Renders `ViewControls.vue` (toolbar: views dropdown, filter, sort, group-by, column-settings, view-type switch).
2. Loads data from one backend endpoint: **`crm.api.doc.get_data`**.
3. Delegates row rendering to a per-doctype `*ListView.vue` (`src/components/ListViews/`), or to `Kanban/KanbanView.vue` / grouped rows depending on `view_type`.

The per-doctype list components are:

| Component | Doctype |
|---|---|
| `LeadsListView.vue` | CRM Lead |
| `InquiriesListView.vue` | CRM Inquiry |
| `ContactsListView.vue` | Contact |
| `OrganizationsListView.vue` | CRM Organization |
| `QuotationsListView.vue` | CRM Quotation |
| `EstimationsListView.vue` | CRM Estimation |
| `TasksListView.vue` | CRM Task |
| `CallLogsListView.vue` | CRM Call Log |
| `LinkedDocsListView.vue` | generic linked docs |

Shared building blocks: `ListRows.vue` (handles infinite scroll + grouped rendering), frappe-ui `ListView/ListHeader/ListRows/ListRowItem/ListFooter/ListSelectBanner`. Scroll position is persisted per doctype in `localStorage` key `scrollPosition<doctype>`.

### 1.2 The `get_data` endpoint (the single list contract)

`crm.api.doc.get_data(doctype, filters, order_by, page_length=20, page_length_count=20, column_field, title_field, columns, rows, kanban_columns, kanban_fields, view, default_filters)`

**Request params**
- `filters`: dict `{ fieldname: value | [operator, value] }`. Special tokens: `"@me"` → `frappe.session.user`; `"%@me%"` → `"%<user>%"`.
- `order_by`: string e.g. `"modified desc"` (comma-separated for multi-sort).
- `page_length` / `page_length_count`: pagination size (default 20).
- `columns` / `rows`: JSON. If present → **custom view** (`is_default=False`). `rows` = list of fieldnames actually fetched.
- `view`: `{ custom_view_name, view_type, group_by_field }`. `view_type` ∈ `list | group_by | kanban`.
- `column_field`, `title_field`, `kanban_columns`, `kanban_fields`: kanban-only.
- `default_filters`: merged into `filters` but not shown in UI.

**Column resolution order** (server, `view_type != kanban`):
1. If `columns`/`rows` passed → custom view.
2. Else if a standard `CRM View Settings` row exists for `{dt, type, is_standard:1, user}` → use its `columns`/`rows`.
3. Else → controller's `default_list_data()` (`columns` + `rows`).
4. Hard fallback columns: `[{Name,Data,name,16rem},{Last Modified,Datetime,modified,8rem}]`, rows `["name"]`.
Server also: appends any `column.key` missing from `rows`; drops columns whose meta is `hidden`; shrinks `_liked_by` width `10rem`→`50px`; appends `group_by_field` to rows.

**Response dict** (exact keys):
```
data, columns, rows, fields, column_field, title_field,
kanban_columns, kanban_fields, group_by_field, page_length,
page_length_count, is_default, views, total_count, row_count,
form_script, list_script, view_type
```
- `fields` = full filterable field meta for the doctype + standard fields (`name, creation, modified, modified_by, _assign, owner, _liked_by`).
- `views` = `get_views(doctype)` (see §2).
- `form_script` / `list_script` = enabled CRM Form Script source for `Form` / `List` view (see §5).

### 1.3 Column definition shape

A column is `{ label, type, key, width, options?, align? }`:
- `type` = the Frappe fieldtype (`Data`, `Link`, `Currency`, `Datetime`, `Text`, `Check`, `Rating`, `Duration`...).
- `key` = fieldname.
- `width` = CSS (`"12rem"`, `"8rem"`, `"50px"`).
- `options` = target doctype for `Link`.
- `align` = `"right"` for numeric columns (Currency/Float/Int/Percent/Duration).

### 1.4 Default columns per doctype (verbatim from `default_list_data()`)

**CRM Lead** (`crm_lead.py`)
| label | type | key | width | options |
|---|---|---|---|---|
| Name | Data | lead_name | 12rem | |
| Organization | Link | organization | 10rem | CRM Organization |
| Status | Link | status | 8rem | CRM Lead Status |
| Email | Data | email | 12rem | |
| Mobile No. | Data | mobile_no | 11rem | |
| Assigned To | Text | _assign | 10rem | |
| Last Modified | Datetime | modified | 8rem | |

rows: `name, lead_name, organization, status, email, mobile_no, lead_owner, first_name, sla_status, response_by, first_response_time, first_responded_on, modified, _assign, image`

**CRM Inquiry** (`crm_inquiry.py`)
| label | type | key | width | options/align |
|---|---|---|---|---|
| Subject | Data | subject | 11rem | |
| Communication | Link | communication_status | 7rem | CRM Communication Status |
| Organization | Link | organization | 12rem | CRM Organization |
| Annual Revenue | Currency | annual_revenue | 11rem | align right |
| Status | Link | status | 10rem | CRM Inquiry Status |
| Email | Data | email | 12rem | |
| Mobile No. | Data | mobile_no | 11rem | |
| Assigned To | Text | _assign | 10rem | |
| Last Modified | Datetime | modified | 8rem | |

rows: `name, organization, annual_revenue, status, email, currency, mobile_no, inquiry_owner, sla_status, response_by, first_response_time, first_responded_on, modified, _assign, subject, communication_status`

**CRM Organization** (`crm_organization.py`)
| label | type | key | width | options |
|---|---|---|---|---|
| Organization | Data | organization_name | 16rem | |
| Website | Data | website | 14rem | |
| Industry | Link | industry | 14rem | CRM Industry |
| Annual Revenue | Currency | annual_revenue | 14rem | |
| Last Modified | Datetime | modified | 8rem | |

rows: `name, organization_name, organization_logo, website, industry, currency, annual_revenue, modified`

**CRM Quotation** (`crm_quotation.py`)
| label | type | key | width |
|---|---|---|---|
| Number | Data | name | 12rem |
| Subject | Data | subject | 16rem |
| Account | Link | account | 14rem |
| Inquiry | Link | inquiry | 12rem |
| Date | Date | date | 8rem |
| Net Total | Currency | net_total | 10rem |
| Created By | Link | owner | 10rem |
| Last Modified | Datetime | modified | 8rem |

(`Contact` uses standard Frappe defaults — no `default_list_data` override in `crm/overrides/contact.py` for columns beyond the framework default; CRM Estimation/Task similarly carry their own `default_list_data`.)

### 1.5 Row rendering & cell types

Per-doctype `*ListView.vue` maps `column.key` / `column.type` to a cell renderer. Examples from `LeadsListView.vue`:
- `status` → `IndicatorIcon` colored prefix + label.
- `lead_name` → `Avatar` (image/initials) + name.
- `lead_owner` / `_assign` → `Avatar` / `MultipleAvatar`.
- `mobile_no` → `PhoneIcon`.
- date keys (`modified, creation, first_response_time, first_responded_on, response_by`) → `Tooltip` showing absolute date, body shows `timeAgo`.
- `sla_status` → colored `Badge`.
- `_liked_by` → heart toggle button (calls `likeDoc`).
- `column.type === 'Check'` → disabled checkbox; `'Rating'` → disabled `RatingInput`; `'Duration'` → `formatDuration`.
Clicking most cells emits `applyFilter` (click-to-filter on that value).

### 1.6 Filtering (`Filter.vue` + `crm.api.doc.get_filterable_fields`)

Filterable fieldtypes: `Check, Data, Float, Int, Currency, Dynamic Link, Link, Long Text, Select, Small Text, Text Editor, Text, Duration, Rating, Date, Datetime`. Standard fields added: `name, owner, modified_by, _user_tags, _liked_by, _comments, _assign, creation, modified`. A controller may exclude fields via `get_non_filterable_fields()` (CRM Lead excludes `converted`).

Operator map (frontend → backend):
```
equals → =        not equals → !=
like → LIKE       not like → NOT LIKE
in → in           not in → not in
>,<,>=,<=          is → is
between → between  timespan → timespan
true → yes         false → no
```
Operators offered depend on fieldtype (string/number/select/link/check/duration/date/rating each have a tailored set). `_assign` supports only Like/Not like/Is. `like` auto-wraps value in `%...%`. Filter dict sent: `{ fieldname: [operator, value] }` (or raw value → coerced to `=`).

**Quick Filters**: `crm.api.doc.get_quick_filters(doctype, cached)` returns `{label, fieldname, fieldtype, options}[]`, persisted in **CRM Global Settings** doc `{dt, type:"Quick Filters", json}`. Falls back to fields with `in_standard_filter`. `update_quick_filters` writes the Global Settings JSON and toggles `in_standard_filter` via Property Setters. (Component: `QuickFilterField.vue`.)

### 1.7 Sorting (`SortBy.vue` + `crm.api.doc.sort_options`)

`sort_options(doctype)` returns all non-`no_value` fields plus standard `name, creation, modified, modified_by, owner`. Frontend keeps an ordered set of `{fieldname, direction}` (`asc|desc`) and serializes to `order_by` string `"f1 asc, f2 desc"`. Default sort `modified desc` shows no badge.

### 1.8 Group By (`GroupBy.vue` + `crm.api.doc.get_group_by_fields`)

Groupable fieldtypes: `Check, Data, Float, Int, Currency, Dynamic Link, Link, Select, Duration, Date, Datetime` + standard fields. When `view_type=="group_by"`, `view.group_by_field` is sent; server appends it to rows and (for the response) builds `group_by_field = {label, fieldname, fieldtype, options}` where `options` are the distinct values (Select options or distinct data values, sorted per `order_by`). `ListRows.vue` renders grouped sections (`ListGroupHeader` + `ListGroupRows`) when every row has `{group, rows[]}`.

### 1.9 Kanban (`Kanban/KanbanView.vue`, `KanbanSettings.vue`)

When `view_type=="kanban"`, `get_data` returns `data` as an array of columns: `{ column: {name, color, order, page_length, count, all_count, delete?}, fields: kanban_fields, data: [rows] }`.
- `column_field` (Link or Select) defines the columns. For Link → `frappe.get_all(options)`; for Select → split options.
- `title_field` = card title; default from controller `default_kanban_settings()`.
- `kanban_fields` = JSON list of fields shown on each card.
- Per-column `order` array preserves manual card ordering; `page_length` defaults 20 with per-column "Load More" (`count < all_count`).
- Drag within a column updates `order`; drag across columns sets `column_field` via `frappe.client.set_value`.
- `KanbanSettings.vue` edits `{column_field, title_field, kanban_fields[]}`; only Link/Select allowed as column field.

**Default kanban settings** (`default_kanban_settings()`):
- CRM Lead: `column_field=status`, `title_field=lead_name`, `kanban_fields=["organization","email","mobile_no","_assign","modified"]`.
- CRM Inquiry: `column_field=status`, `title_field=organization`, `kanban_fields=["annual_revenue","email","mobile_no","_assign","modified"]`.

### 1.10 Column Settings (`ColumnSettings.vue`)

Add / remove / reorder (drag) / resize columns and edit per-column width. Persists `{ columns, rows, isDefault, reload, reset }`. If `isDefault` → view stores empty columns (uses `default_list_data`); else stores custom `columns`/`rows` as JSON in **CRM View Settings**. `name` is never removed from rows. "Reset to Default" clears custom columns.

### 1.11 Bulk actions (`ListBulkActions.vue`)

Selection banner exposes: **Edit** (bulk field update via EditValueModal), **Delete** (with linked-doc checks), **Assign To**, **Clear Assignment** (`frappe.desk.form.assign_to.remove_multiple`). CRM Lead adds **Convert to Inquiry** (`crm.fcrm.doctype.crm_lead.crm_lead.convert_to_inquiry`). Custom actions can be injected via the doctype's `bulkActions`. Each action: `{label, onClick(ctx)}` where `ctx = {list, selections, unselectAll, call, toast, $dialog, router}`.

### 1.12 Pagination

`ListFooter` binds `pageLengthCount`; "Load More" emits `loadMore` (increments page length, re-fetches). `total_count` and `row_count` come from the response.

---

## 2. SAVED VIEWS / VIEW SETTINGS

### 2.1 Backend doctype: `CRM View Settings` (`crm_view_settings.json`)

Read-only doctype (`read_only:1`), autoincrement name, title field `label`. Roles: System Manager / Sales Manager / Sales User. Key fields:

| field | type | meaning |
|---|---|---|
| label | Data | display name |
| icon | Data | emoji / icon |
| user | Link User | owner (empty = public/standard) |
| is_standard | Check | built-in standard view (one per type) |
| is_default | Check | default view for its type |
| type | Select `list/group_by/kanban` | view type |
| dt | Link DocType | target doctype |
| route_name | Data | route slug |
| pinned | Check | pinned in sidebar |
| public | Check | shared with everyone |
| load_default_columns | Check | ignore stored columns, use defaults |
| filters | Code (JSON) | filter dict |
| order_by | Code | sort string |
| columns | Code (JSON) | column defs |
| rows | Code (JSON) | fetched fieldnames |
| group_by_field | Data | group-by fieldname |
| column_field | Data | kanban column field |
| title_field | Data | kanban card title field |
| kanban_columns | Code (JSON) | kanban column order/meta |
| kanban_fields | Code (JSON) | kanban card fields |

### 2.2 Load API: `crm.api.views.get_views(doctype)`

```python
View = qb.DocType("CRM View Settings")
select * where (user == "" OR user == session.user) [and dt == doctype]
```
→ returns the user's own views **plus** all public/standard (`user==""`) views for that doctype. Also embedded in every `get_data` response as `views`.

### 2.3 "Public / Saved / Pinned / Standard" concept (`ViewControls.vue`)

The views dropdown is grouped:
- **Standard views** — `list`, `group_by`, `kanban` (always available where allowed). A standard view is a `CRM View Settings` row with `is_standard=1` and `user=session.user`; the server prefers it over `default_list_data` when resolving columns.
- **Saved views** — custom, not pinned, not public.
- **Public views** — `public=1` (shared, `user==""`).
- **Pinned views** — `pinned=1`.

View manipulation calls (whitelisted on `crm.fcrm.doctype.crm_view_settings.crm_view_settings`):
`create_or_update_standard_view(view)`, `set_as_default(name, type, doctype)`, `pin(name, value)`, `public(name, value)`, `delete(name)`. Changing filters/sort/group-by/columns recomputes params and re-calls `get_data` (cache key `[doctype, view_name, viewType]`).

---

## 3. FORM LAYOUT ENGINE

### 3.1 Concept

A form is **data, not code**. Layout JSON is stored in **CRM Fields Layout** and rendered by `src/components/FieldLayout/`. There are two surfaces:
- **Main tab / data fields** — the big multi-section (optionally multi-tab) form body.
- **Side panel** — the compact right-hand sidebar (sections only, no tabs).

### 3.2 Backend doctype: `CRM Fields Layout` (`crm_fields_layout.json`)

Name format `format:{dt}-{type}` (e.g. `CRM Lead-Side Panel`). Fields:
- `dt` (Link DocType)
- `type` Select: **`Quick Entry`** (new-doc modal), **`Side Panel`** (sidebar), **`Data Fields`** (main form body), **`Grid Row`** (child-table row editor), **`Required Fields`** (mandatory-fields collector).
- `layout` (Code/JSON) — the layout tree.

### 3.3 Layout JSON shape

Two nesting forms — **with tabs** (Data Fields) and **flat sections** (Side Panel / Quick Entry):

```jsonc
// Tabbed (Data Fields)
[
  { "name": "tab_main", "label": "",
    "sections": [
      { "name": "section_x", "label": "Inquiry", "opened": true,
        "collapsible": true, "hideLabel": false, "hideBorder": false,
        "columns": [
          { "name": "col_a", "label": "", "fields": ["inquiry", "subject"] },
          { "name": "col_b", "fields": ["account"] }
        ] } ] }
]

// Flat (Side Panel / Quick Entry) — sections at top level, no "sections" wrapper
[
  { "name": "details_section", "label": "Details", "opened": true,
    "columns": [ { "name": "col1", "fields": ["organization","website","territory"] } ] }
]
```
Hierarchy: **Tab → Section → Column → fields[]** (field = fieldname string, resolved to full field meta by the server).

Real examples (from `crm/fixtures/crm_fields_layout.json`):
- `CRM Lead-Side Panel`: sections `Details / Person / Company-Legal / Address`.
- `CRM Quotation-Data Fields` (tab `tab_main`): sections `Inquiry, Quote Information, Product, Additionals, Terms & Conditions (collapsible), Rate Info (collapsible), Remark, Print`.
- `CRM Quotation-Side Panel`: `Inquiry, Inquiry Details, Contacts, Organization`.
- `CRM Estimation-Data Fields` (tab `tab_data`): `Estimation, Revenue, Expense, Remarks`.

### 3.4 Load / save APIs (`crm_fields_layout.py`)

- **`get_fields_layout(doctype, type, parent_doctype=None)`** — loads the stored `CRM Fields Layout`, else `get_default_layout(doctype)`. Normalizes to tabs (wraps flat sections in `{name:"first_tab", sections:[...]}`). Replaces each fieldname string with full field meta (`as_dict()`), applies perm-level restrictions. For `type=="Required Fields"`, appends a synthetic section listing any `reqd && !default` fields not already in the layout.
- **`get_sidepanel_sections(doctype)`** — loads the `Side Panel` layout, expands fieldnames to field objects (excludes Tab/Section/Column Break).
- **`save_fields_layout(doctype, type, layout)`** — upsert the JSON.
- Side-panel can be mutated server-side at runtime: `add_or_remove_lost_reason_section_in_sidepanel` injects/removes a `lost_reason_section` (`lost_reason`, `lost_notes`) into the `*-Side Panel` layout when a Lead/Inquiry status type becomes `Lost`.

### 3.5 Frontend renderers (`src/components/FieldLayout/`)

- **`FieldLayout.vue`** — top-level. Props: `tabs, data, doctype, isGridRow, preview, context`. Renders frappe-ui `Tabs`; hides the tab-list when there is ≤1 tab without a label (`hasTabs`). Applies **script overrides** for tab/section (`hidden`, etc.) from `doc.fieldPropertyOverrides`. Provides `data, hasTabs, doctype, preview, isGridRow, fieldLayoutContext` via Vue `provide`.
- **`Section.vue`** — renders a section (collapsible via `opened`/`collapsible`, label hide via `hideLabel`, border via `hideBorder`); maps `section.columns` → `Column`.
- **`Column.vue`** — optional column label; maps `column.fields` → `Field`.
- **`Field.vue`** — the dispatcher that turns one field-meta into the right control (see §4). Also evaluates `depends_on`, `read_only_depends_on`, `mandatory_depends_on`, hides empty read-only fields (`hide_empty_read_only_fields` sysdefault), and merges per-field script overrides (`fieldPropertyOverrides`).

**Editors**: `FieldLayoutEditor.vue` (main/tab layout) and `SidePanelLayoutEditor.vue` (sidebar) provide drag-and-drop section/column/field editing that writes the JSON back via `save_fields_layout`. `SidePanelLayout.vue` renders the sidebar at runtime. The `Modals/FieldLayoutDialog.vue` renders a standalone layout (used by form scripts' `formDialog` helper).

---

## 4. FIELD CONTROLS CATALOG

`Field.vue` is the single source mapping **Frappe fieldtype → input widget**. Controls live in `src/components/Controls/`. Full mapping:

| Frappe fieldtype | Control / widget | File |
|---|---|---|
| Data / (fallback) | frappe-ui `FormControl type=text` | (frappe-ui) |
| Read-only any (except special) | `FormControl type=text disabled` | (frappe-ui) |
| Select | `FormControl type=select` (options split on `\n`, blank prepended unless reqd); optional colored prefix `IndicatorIcon` | (frappe-ui) |
| Check | `FormControl type=checkbox` + clickable label | (frappe-ui) |
| Link / Dynamic Link | **`Link.vue`** (async search, inline create, optional Edit button) | `Controls/Link.vue` |
| Link→User (auto-detected) | `Link.vue` rendered as **User** picker w/ `UserAvatar`, filtered to CRM users | `Controls/Link.vue` |
| User (options=User) | `Link.vue` User variant | `Controls/Link.vue` |
| Table | **`Grid.vue`** (child-table editor) | `Controls/Grid.vue` |
| Table MultiSelect | **`TableMultiselectInput.vue`** | `Controls/TableMultiselectInput.vue` |
| Autocomplete | frappe-ui `Combobox` | (frappe-ui) |
| Time | frappe-ui `TimePicker` | (frappe-ui) |
| Datetime | frappe-ui `DateTimePicker` | (frappe-ui) |
| Date | frappe-ui `DatePicker` | (frappe-ui) |
| Small Text / Text / Long Text / Code | `FormControl type=textarea` | (frappe-ui) |
| Password | **`Password.vue`** | `Controls/Password.vue` |
| Int | **`FormattedInput.vue`** (number formatting) | `Controls/FormattedInput.vue` |
| Float | `FormattedInput.vue` (`getFormattedFloat`) | `Controls/FormattedInput.vue` |
| Percent | `FormattedInput.vue` (`getFormattedPercent`) | `Controls/FormattedInput.vue` |
| Currency | `FormattedInput.vue` (`getFormattedCurrency`) | `Controls/FormattedInput.vue` |
| Duration | **`DurationInput.vue`** | `Controls/DurationInput.vue` |
| Rating | **`RatingInput.vue`** (max = options or 5) | `Controls/RatingInput.vue` |
| Button | **`ButtonControl.vue`** (theme/variant from `button_color`) | `Controls/ButtonControl.vue` |
| Attach / Attach Image | **`AttachControl.vue`** (`imageOnly` for Attach Image) | `Controls/AttachControl.vue` |
| HTML | **`HtmlControl.vue`** (renders `options` template or script-injected HTML via `fieldHtmlMap`) | `Controls/HtmlControl.vue` |
| Text Editor | **`TextEditorControl.vue`** (rich text) | `Controls/TextEditorControl.vue` |
| Geolocation | **`GeolocationControl.vue`** (map) | `Controls/GeolocationControl.vue` |

**Additional Controls components** (used by Grid / forms, not in the main dispatch switch):
`ImageUploader.vue`, `MultiSelectEmailInput.vue`, `MultiSelectUserInput.vue`, `GridFieldsEditorModal.vue`, `GridRowFieldsModal.vue`, `GridRowModal.vue`.

**Field behaviors handled in `Field.vue`**:
- Visibility: `depends_on` (eval), read-only logic, hide empty read-only fields (sysdefault `hide_empty_read_only_fields`, default on).
- `reqd` / `mandatory_depends_on` → red `*`.
- `read_only` / `read_only_depends_on` → disabled, with script `read_only` override taking priority.
- Link `link_filters` parsed via `parseLinkFilters`; inline `create` callback opens `createDocument`.
- Every change calls `fieldChange → triggerOnChange(fieldname, value[, row])` which both writes the value and fires the form-script onChange hook.
- **Grid** (Table): renders a grid header from child-doctype `Grid Row` layout; rows editable via `GridRowModal`; supports row add/remove triggers (`<parentfield>_add`, `<parentfield>_remove`).

---

## 5. FORM SCRIPTS

### 5.1 Two script sources, merged

1. **DB scripts** — doctype **CRM Form Script** (`crm_form_script.json`): fields `dt` (Link DocType), `view` (`Form`/`List`, set-once), `enabled` (Check), `is_standard` (Check, only `enabled` editable unless developer mode), `script` (Code/JS). Default stub:
   ```js
   function setupForm({ doc }) { return { actions: [] } }
   ```
   Loaded by `get_form_script(dt, view="Form")` → returns enabled script source (string, or list if multiple). Embedded in `get_data` response as `form_script` / `list_script`.
2. **File scripts** — `src/doctypes/<slug>/form.js` exporting a class (slug = doctype lowercased, spaces→`_`). Loaded via Vite `import.meta.glob('../doctypes/*/*.js')`. The parent-doctype class name must match the doctype (spaces stripped); child-doctype classes are wired to the parent.

Both are assembled in `src/data/script.js` (`getScript → setupScript → setupMultipleFormControllers`). DB scripts are `eval`-ed via `new Function(...helpers, "<script>; return ClassName;")`. File-script classes are instantiated directly.

### 5.2 Runtime wiring (`src/data/document.js` + `script.js`)

`useDocument(doctype, docname)` builds a `createDocumentResource`, then on load calls `setupFormScript()` which instantiates every controller class and fires `triggerOnLoad()` then `triggerOnRender()`. The document reactive object also carries `fieldHtmlMap` and `fieldPropertyOverrides`.

**Lifecycle hooks** (each tries camelCase, snake_case, and a legacy alias; run sequentially across controllers):
| Trigger | Method names tried |
|---|---|
| onLoad | `onLoad` / `on_load` / `onload` |
| onRender | `onRender` / `on_render` / `refresh` |
| onBeforeCreate | `onBeforeCreate` / `on_before_create` |
| onValidate | `onValidate` / `on_validate` / `validate` |
| onSave | `onSave` / `on_save` |
| onError | `onError` / `on_error` |
| onChange (per field) | a method **named exactly like the fieldname** |
| button click | a method named like the button fieldname |
| row add / remove | `<parentfield>_add` / `<parentfield>_remove` |
| onCreateLead | `onCreateLead` / `on_create_lead` |
| convertToInquiry | `convertToInquiry` / `convert_to_inquiry` |

During an onChange the controller exposes `this.value` (new value), `this.oldValue`, and (for grid rows) `this.currentRowIdx`.

### 5.3 Controller API surface (what `form` / `doc` expose)

On `this`:
- **`this.doc`** — reactive proxy of the document (read/write fields directly: `this.doc.subject = '...'`). Child doctypes get a proxy bound to parent.
- **`this.value` / `this.oldValue`** — current change context.
- **Helpers injected**: `this.call` (frappe-ui `call`), `this.createDialog` (`$dialog`), `this.toast`, `this.socket`, `this.router`, `this.formDialog` (`renderFieldLayoutDialog`), `this.throwError(msg)`, `this.getMeta(doctype)`, `this.crm.makePhoneCall`, `this.crm.openSettings(page)`.
- **Field-property methods** (mutate `fieldPropertyOverrides`, read by `Field.vue`):
  - `setFieldProperty(fieldname, property, value, rowName?)` — e.g. `setFieldProperty('number','read_only',1)`.
  - `setFieldProperties(fieldname, {prop:value,...}, rowName?)`
  - `removeFieldProperty(fieldname, property, rowName?)`
  - `getField(fieldname)` — field meta merged with overrides.
- **`setFieldHtml(fieldname, html)`** — inject HTML into an `HTML` fieldtype (read by `HtmlControl` via `fieldHtmlMap`).
- **`this.actions` / `this.statuses`** — arrays surfaced to the form header (custom action buttons / status badges); proxied to the document context.
- **`getRow(parentField, idx?)`** — get a child-table row proxy.

### 5.4 The 3 custom file-based scripts (verbatim-summarized)

**A. `src/doctypes/crm_quotation/form.js` — class `CRMQuotation`** (the substantive one)
- `onLoad()`: marks `number` read-only (`setFieldProperty('number','read_only',1)`).
- `onRender()`: if `doc.account` set → `fillContactFromAccount()`; always `fillInquiryDetails()` (so old quotations re-populate).
- `inquiry()` (onChange of `inquiry`, a Link to **CRM Inquiry**):
  - if cleared → blank out `number, subject, account, account_name, contact_name` and clear the `inquiry_details` HTML.
  - else → `frappe.client.get_value` on **CRM Inquiry** for `organization, organization_name, subject`; sets `doc.number = inquiry`, `doc.subject`, `doc.account = organization`, `doc.account_name`; then `fillContactFromAccount()` + `fillInquiryDetails()`.
- `account()` (onChange of `account`): re-runs `fillContactFromAccount()`.
- `fillContactFromAccount()`: `frappe.client.get_list` on **Contact** filtered `company_name == account`, oldest first, limit 1 → sets `doc.contact_name` (or blank).
- `fillInquiryDetails()`: calls **`crm.api.quotation.get_inquiry_detail`** with the inquiry; builds an escaped HTML key/value block (Inquiry, Organization, Subject, Status, Contact, Email, Mobile, Territory, Source, Owner) and injects it via `setFieldHtml('inquiry_details', html)` into the sidebar HTML field.
  → Net effect: selecting an Inquiry (CRM Inquiry) auto-fills quotation header (number/subject/account/contact) and renders a read-only inquiry summary card.

**B. `src/doctypes/crm_task/form.js` — class `CRMTask`**
- `onRender()`: if `reference_doctype` + `reference_docname` set, adds one action **"Open <Lead|Inquiry>"** that routes to the Lead/Inquiry page (`router.push` with `{leadId}` or `{inquiryId}`). Label derives from `reference_doctype` (strips `"CRM "`).

**C. `src/doctypes/fcrm_note/form.js` — class `FCRMNote`**
- Identical pattern to CRMTask: `onRender()` adds an **"Open <Lead|Inquiry>"** action that navigates to the referenced Lead/Inquiry when `reference_doctype`/`reference_docname` are present.

---

## 6. NOTES FOR THE GO REBUILD

- One generic list endpoint (`get_data`) drives every list/group/kanban surface; the Go server needs the same column-resolution precedence (custom → standard CRM View Settings → controller default → hard fallback).
- Layouts are pure JSON (`Tab→Section→Column→fields`); a Go renderer can treat them as a tree and reuse the fieldtype→widget table in §4.
- Field meta drives controls; the dispatcher logic (read-only hiding, depends_on, Link→User auto-detection, script overrides) must be reproduced for parity.
- Form scripts are JS classes with name-based hooks; in Go either keep a JS sandbox for these or port the 3 known scripts as native handlers (quotation auto-fill is the only one with real business logic; task/note only add a navigation action).
