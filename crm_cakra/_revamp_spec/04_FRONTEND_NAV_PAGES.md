# Frappe CRM Frontend — Navigation, Routes & Pages Spec

Source: `D:\System_ERPNext\crm\frontend` (Vue 3 SPA, frappe-ui, Pinia, vue-router).
Purpose: complete UI/UX + navigation spec so the app can be rebuilt (target: Go).
This is a **customized** Frappe CRM build. Notable local customizations are flagged with **[CUSTOM]**.

The SPA is mounted under base path **`/crm`** (`createWebHistory('/crm')`). All in-app links live under `/crm/...`.

---

## 1. App Shell & Bootstrap

`src/App.vue` is the root:

- Wraps everything in `<FrappeUIProvider>`.
- If route is `Not Permitted` → renders `NotPermitted` page directly (no shell).
- Else if `session.isLoggedIn` → renders a responsive `<Layout>` with `<router-view :key="$route.fullPath">` inside.
- Always renders global `<Dialogs />` and `<DoctypeModals />`.
- **Layout selection is by viewport width** (computed once at load):
  - `window.innerWidth < 640` → `MobileLayout` (`components/Layouts/MobileLayout.vue`)
  - else → `DesktopLayout` (`components/Layouts/DesktopLayout.vue`)
- Theme: defaults to `light` if no `theme` in localStorage. Timezones / translated messages injected via `setConfig` from `window.*`.

**DesktopLayout** = `[AppSidebar | (AppHeader + <slot/>)]` + `GlobalModals`.
**MobileLayout** = `[MobileSidebar(drawer) | (MobileAppHeader + <slot/>)]` + `GlobalModals`.

The header is an empty teleport target `<div id="app-header">`; each page's `LayoutHeader.vue` teleports its own header content (`#left-header`, `#right-header`) into it. `AppHeader` also embeds the telephony `CallUI`.

---

## 2. Route Table (`src/router.js`)

Base: `/crm`. List routes have an `alias` (e.g. `/leads`) plus a canonical `/{entity}/view/:viewType?` path. `viewType` ∈ `list | kanban | group_by` (or a saved-view name/label that the guard resolves).

| Path | Alias | Name | Component | Props | Notes |
|---|---|---|---|---|---|
| `/` | — | `Home` | (none) | — | Guard redirects to default view or `Leads` |
| `/notifications` | — | `Notifications` | `MobileNotification.vue` | — | Mobile notifications list |
| `/dashboard` | — | `Dashboard` | `Dashboard.vue` | — | Manager dashboard |
| `/leads/view/:viewType?` | `/leads` | `Leads` | `Leads.vue` | — | List/Kanban/GroupBy |
| `/leads/:leadId` | — | `Lead` | `Lead.vue` **or** `MobileLead.vue` | `true` | Mobile chosen if `innerWidth < 768` |
| `/inquiries/view/:viewType?` | `/inquiries` | `Inquiries` | `Inquiries.vue` | — | **meta.label = 'Inquiry'** **[CUSTOM relabel]** |
| `/inquiries/new` | — | `NewInquiry` | `InquiryNew.vue` | — | Full-page create form |
| `/inquiries/:inquiryId` | — | `Inquiry` | `Inquiry.vue` **or** `MobileInquiry.vue` | `true` | Mobile if `<768` |
| `/quotations/view/:viewType?` | `/quotations` | `Quotations` | `Quotations.vue` | — | **[CUSTOM doctype]** |
| `/quotations/new` | — | `NewQuotation` | `QuotationNew.vue` | — | |
| `/quotations/:quotationId` | — | `Quotation` | `Quotation.vue` | `true` | Detail w/ state machine |
| `/estimations/view/:viewType?` | `/estimations` | `Estimations` | `Estimations.vue` | — | **[CUSTOM doctype]** |
| `/estimations/new` | — | `NewEstimation` | `EstimationNew.vue` | — | |
| `/estimations/:estimationId` | — | `Estimation` | `Estimation.vue` | `true` | Detail |
| `/notes/view/:viewType?` | `/notes` | `Notes` | `Notes.vue` | — | Card grid |
| `/tasks/view/:viewType?` | `/tasks` | `Tasks` | `Tasks.vue` | — | List/Kanban |
| `/contacts/view/:viewType?` | `/contacts` | `Contacts` | `Contacts.vue` | — | List |
| `/contacts/:contactId` | — | `Contact` | `Contact.vue` **or** `MobileContact.vue` | `true` | Mobile if `<768` |
| `/organizations/view/:viewType?` | `/organizations` | `Organizations` | `Organizations.vue` | — | List |
| `/organizations/:organizationId` | — | `Organization` | `Organization.vue` **or** `MobileOrganization.vue` | `true` | Mobile if `<768` |
| `/call-logs/view/:viewType?` | `/call-logs` | `Call Logs` | `CallLogs.vue` | — | List |
| `/data-import` | — | `DataImportList` | `DataImport.vue` | — | Import landing |
| `/data-import/doctype/:doctype` | — | `NewDataImport` | `DataImport.vue` | `true` | New import for a doctype |
| `/data-import/:importName` | — | `DataImport` | `DataImport.vue` | `true` | Existing import |
| `/welcome` | — | `Welcome` | `Welcome.vue` | — | Onboarding splash |
| `/:invalidpath` | — | `Invalid Page` | `InvalidPage.vue` | — | Catch-all |
| `/not-permitted` | — | `Not Permitted` | `NotPermitted.vue` | — | Access denied |

**Mobile-vs-desktop routing:** done at route-config time via `handleMobileView(name)` returning `Mobile${name}` when `window.innerWidth < 768`. Applies to `Lead`, `Inquiry`, `Contact`, `Organization` detail pages only. (Note: layout selection in App.vue uses a `<640` breakpoint; detail-component selection uses `<768`.)

### Navigation Guard (`router.beforeEach`)
Order of checks:
1. `router.previousRoute = from` is stored.
2. If logged in and users not yet fetched → `await users.promise`.
3. **Permission gate:** if logged in, target ≠ `Not Permitted`, and `!isCrmUser()` → redirect to `Not Permitted`.
4. **Home redirect:** target `Home` & logged in → load views, pick `getDefaultView()`. If none → `Leads`. Else navigate to the default view's `route_name` + `viewType` (+ `?view=` for non-standard saved views).
5. **Not logged in:** `window.location.href = '/login?redirect-to=/crm'` (hard redirect to Frappe login).
6. **Unmatched route** (`to.matched.length === 0`) → `Invalid Page`.
7. **Detail tab restore:** for `Inquiry`/`Lead` with no hash → append `#<lastTab>` from `localStorage['lastInquiryTab'|'lastLeadTab']` (default `#activity`).
8. **List default view resolution:** for the 9 list routes with no `?view=` query — resolves the correct `viewType` (global default → standard default → `list`) and, for non-standard views, appends `?view=<name>`. Also resolves a saved-view name/label passed in `:viewType` into the proper `viewType` + `?view=`.

Doctype map used by the guard (route name → backend doctype):
`Leads→CRM Lead`, `Inquiries→CRM Inquiry`, `Contacts→Contact`, `Organizations→CRM Organization`, `Quotations→CRM Quotation`, `Estimations→CRM Estimation`, `Notes→FCRM Note`, `Tasks→CRM Task`, `Call Logs→CRM Call Log`.

---

## 3. Navigation / Menu Structure

### 3.1 Left Sidebar — Desktop (`components/Layouts/AppSidebar.vue`)
Collapsible (`220px` ⇄ `48px`, persisted in `localStorage['isSidebarCollapsed']`).

Top: **UserDropdown** (brand logo + brand name + current user's full name + chevron).

Then a **Notifications** button (icon `NotificationsIcon`, opens the notifications side panel; shows unread Badge / dot).

**Section "All Views"** (label hidden) — the primary nav, in this exact order **[CUSTOM order & labels]**:

| # | Label | Icon | Route (name) |
|---|---|---|---|
| 1 | **Dashboard** | `LayoutDashboard` (lucide) | `Dashboard` |
| 2 | **Accounts** | `OrganizationsIcon` | `Organizations` |
| 3 | **Contacts** | `ContactsIcon` | `Contacts` |
| 4 | **Leads** | `LeadsIcon` | `Leads` |
| 5 | **Inquiries** | `InquiriesIcon` | `Inquiries` |
| 6 | **Quotations** | `QuotationIcon` | `Quotations` |
| 7 | **Estimations** | `EstimationIcon` | `Estimations` |
| 8 | **Notes** | `NoteIcon` | `Notes` |
| 9 | **Tasks** | `TaskIcon` | `Tasks` |
| 10 | **Call Logs** | `PhoneIcon` | `Call Logs` |

> **[CUSTOM relabels]** vs stock Frappe CRM: "Organizations" → **Accounts**, "Inquiries" → **Inquiries**. "Quotations" and "Estimations" are custom-added entries. (Stock sidebar order is Leads/Inquiries/Contacts/Organizations/Notes/Tasks/Call Logs.)

**Section "Public Views"** (only if any) and **Section "Pinned Views"** (only if any) — each renders saved views from `viewsStore` (`getPublicViews()` / `getPinnedViews()`), with icon resolved per route name (fallback `PinIcon`) and a `to` of `{ name: route_name, params: { viewType }, query: { view: name } }`.

**Bottom block:**
- Banners (conditional): `SalesHierarchyBanner` **[CUSTOM]**, `SignupBanner` (demo site), `TrialBanner` (FC site), `GettingStartedBanner` (onboarding incomplete).
- **Clear Demo Data** (red; managers only, when demo data exists).
- **Help** (opens `HelpModal` with the onboarding help-center article tree; links to docs.frappe.io/crm).
- **Expand/Collapse** toggle.
- Mounted (hidden): `<Notifications>` panel, `<Settings>` modal, `HelpModal`, `IntermediateStepModal`.

**Onboarding steps** (driven by `useOnboarding('frappecrm')`, surfaced in GettingStartedBanner/HelpModal): setup password, create first lead, invite team (managers), convert lead→inquiry, create first task, create first note, add first comment, send first email, change inquiry status. Each step deep-links into the relevant page/tab and fires telemetry.

### 3.2 Left Sidebar — Mobile (`components/Mobile/MobileSidebar.vue`)
A slide-in drawer (`260px`, headless-ui Dialog) toggled by the hamburger in `MobileAppHeader`. Top UserDropdown, a Notifications link (→ route `Notifications`), then **All Views / Public Views / Pinned Views** sections.

> **Note (inconsistency):** the mobile sidebar's hard-coded link list is the **stock** set/labels: Leads, Inquiries, Contacts, Organizations, Notes, Tasks, Call Logs — it does **not** include Dashboard/Quotations/Estimations and does **not** apply the "Accounts"/"Inquiries" relabels. Desktop and mobile nav differ.

### 3.3 Top Bar
- **Desktop** (`AppHeader.vue`): `#app-header` teleport target (page header lands here) + `CallUI` (telephony widget) on the right.
- **Mobile** (`MobileAppHeader.vue`): hamburger (toggles drawer) + `#app-header` target + `CallUI`.
- Per-page header content comes from each page's `LayoutHeader` → `ViewBreadcrumbs` (list pages) or `Breadcrumbs` (detail pages) on the left, and action buttons (Create / Custom Actions / Save / Convert / etc.) on the right.

### 3.4 "+ Create" Actions
There is **no global "+" button**. Creation is per-page, via the right-side header `Create` button:
- **Leads** → opens `LeadModal` (in-page modal).
- **Inquiries (Inquiries)** → routes to `NewInquiry` (full-page form). Kanban "+" in a column passes the column's status as a query default.
- **Quotations / Estimations** → route to `NewQuotation` / `NewEstimation`.
- **Contacts / Organizations / Call Logs** → open `ContactModal` / `OrganizationModal` / `CallLogModal` (via `useDoctypeModal`).
- **Notes / Tasks** → open Note/Task modals (`useDoctypeModal`).
- **UserDropdown** (top of sidebar) is a settings/app menu, not a create menu — items come from `FCRM Settings.dropdown_items`; standard items: App Selector (`Apps.vue` → other Frappe apps + Desk), **Settings**, Login to FC, About, **Logout**.

### 3.5 App Switcher (`components/Apps.vue`)
Hover popover inside UserDropdown. Resource `frappe.apps.get_apps`; always prepends "Desk" (`/app`), lists other installed apps (excludes `crm`).

---

## 4. The List-Page Pattern (shared by 9 list pages)

All list pages share the same skeleton (Leads/Inquiries/Quotations/Estimations/Contacts/Organizations/Tasks/CallLogs use it; Notes is a card variant):

```
LayoutHeader
  #left-header  → ViewBreadcrumbs (routeName + views dropdown)
  #right-header → CustomActions (from list customizations) + Create button
ViewControls (owns the data fetch; emits to parent)
  → KanbanView   (when route.params.viewType == 'kanban')
  → <Entity>ListView   (list / group_by)
  → EmptyState   (no rows)
<Entity>Modal  (create)
```

### 4.1 `ViewControls.vue` — the data + view engine
This is the heart of every list page. It owns:
- **Primary list fetch:** `createResource({ url: 'crm.api.doc.get_data', params: {...} })` — returns `data`, `columns`, `rows`, `total_count`, `row_count`, `page_length`, `views`, kanban config, etc. Cache key `[doctype, view, viewType]`.
- **Quick filters:** load `crm.api.doc.get_quick_filters`; save `crm.api.doc.update_quick_filters`.
- **Filter / Sort / GroupBy / ColumnSettings / KanbanSettings** controls (each a child component), plus a quick-filter bar (with "Add Filter", drag-to-reorder, "Customize Quick Filters" for managers).
- **Views dropdown** (rendered by `ViewBreadcrumbs`): Standard Views (List/Kanban/GroupBy), Saved Views, Public Views, Pinned Views, + "Create View". Per-view actions: Duplicate, Set As Default, Edit, Pin/Unpin, Make Public/Private, Delete.
- **View persistence** (CRM View Settings backend methods):
  - `...crm_view_settings.create_or_update_standard_view`
  - `...crm_view_settings.set_as_default`, `.public`, `.pin`, `.delete`, `.fetch_and_update_kanban_columns`
- **Export:** builds a URL to `frappe.desk.reportview.export_query` (Excel/CSV, all or selected rows) → `window.location.href`.
- **Import:** dropdown item → `router.push({ name: 'NewDataImport', params: { doctype } })`.
- **Like / unlike:** `frappe.desk.like.toggle_like`; "liked by me" filter via `_liked_by` LIKE.
- **Kanban move:** `frappe.client.set_value` on the column field.
- `usePageMeta` sets the browser tab title/favicon per current view.

### 4.2 `ListBulkActions.vue` — bulk operations (selection toolbar)
Available when rows are selected:
- **Edit** (bulk field edit → `EditValueModal`).
- **Delete** (1 → `DeleteLinkedDocModal`; many → `BulkDeleteLinkedDocModal`).
- **Assign To** (`AssignmentModal`) / **Clear Assignment** (`frappe.desk.form.assign_to.remove_multiple`).
- **Convert to Inquiry** (leads only) → `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_inquiry` per selected lead.
- **Custom bulk actions** from list customizations (`setupListCustomizations`).

---

## 5. Page-by-Page Catalog

### Leads (`Leads.vue`) — route `Leads`, doctype **CRM Lead**
- **Loads:** `crm.api.doc.get_data` (via ViewControls). Status colors from `statusesStore` (`CRM Lead Status`). Meta via `getMeta('CRM Lead')`.
- **Views:** list, group_by, kanban. Rich cell rendering (status indicator, owner/org avatars, SLA badge, assignees, relative times, email/note/task/comment counts).
- **Actions:** Create (LeadModal), per-row dropdown: Make a Call (if telephony), New Note, New Task (both via `useDoctypeModal.showModal`, reference = CRM Lead). Kanban "+" seeds the column field. Broadcast `trigger_lead_create` opens the modal (used by onboarding).
- Telemetry + onboarding (`create_first_note`/`task`).

### Lead (`Lead.vue` / `MobileLead.vue`) — route `Lead`, doctype **CRM Lead**
- **Loads:** `useDocument('CRM Lead', leadId)` (doc + assignees + permissions + form scripts). Side-panel layout: `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections`.
- **Layout:** left = `Tabs` → `Activities`; right = resizable side panel (avatar/image upload, SLA, field sections via `SidePanelLayout`).
- **Tabs:** Activity, Emails, Comments, Data, Calls, Tasks, Notes, Attachments, WhatsApp (gated). Active tab persisted in `localStorage['lastLeadTab']` via `useActiveTabManager`.
- **Actions:** edit/save fields (`document.save`/`triggerOnChange`), change **status** (dropdown; Lost flow via `LostReasonModal`), **Convert to Inquiry** (`ConvertToInquiryModal`, hidden once `doc.converted`), **Assign** (`AssignTo`), **Void/Unvoid** `crm.api.void.void_document` **[CUSTOM]**, make call, send email (`openEmailBox`), open website, attach file (`FilesUploader`), delete (`DeleteLinkedDocModal`).
- **[CUSTOM]** When `doc.converted` flips true, a watcher forces all fields `read_only:1`.

### Inquiries / "Inquiries" (`Inquiries.vue`) — route `Inquiries` (label **Inquiry**), doctype **CRM Inquiry**
- Identical list pattern to Leads (status from `CRM Inquiry Status`, org logos from `organizationsStore`).
- **Create** routes to `NewInquiry` (not a modal). Per-row dropdown: Make a Call, New Note, New Task (reference = CRM Inquiry). Kanban "+" → `NewInquiry` with column-field query.

### Inquiry (`Inquiry.vue` / `MobileInquiry.vue`) — route `Inquiry`, doctype **CRM Inquiry**
- **Loads:** `useDocument('CRM Inquiry', inquiryId)`; lazy `useDocument('CRM Organization', org)` for logo; side panel `get_sidepanel_sections`; **contacts** via `crm.fcrm.doctype.crm_inquiry.api.get_inquiry_contacts`.
- **Tabs:** same set as Lead; active tab in `localStorage['lastInquiryTab']`.
- **Side panel extras:** organization avatar; a **Contacts section** listing linked contacts with primary badge + per-contact dropdown.
- **Actions:** edit/save fields; change status (Lost flow; onboarding `change_inquiry_status`); Void/Unvoid **[CUSTOM]**; **add/remove/set-primary contact** (`crm_inquiry.add_contact` / `remove_contact` / `set_primary_contact`); create Organization (`OrganizationModal`) / Contact (`ContactModal`); call primary contact; send email; attach; delete; assign. Socket `crm_customer_created`; broadcast `reload-inquiry-sections`.

### NewInquiry (`InquiryNew.vue`) — route `NewInquiry`, doctype **CRM Inquiry**
- **Loads:** `useDocument('CRM Inquiry')` (new); field layout `...get_fields_layout` (type "Data Fields"). Renders via `FieldLayout`.
- **Create:** `frappe.client.insert` → push to `Inquiry`. Cancel → `Inquiries`.
- **[CUSTOM] onMount defaults:** seeds from `route.query` (kanban), `inquiry_owner`=current user, `status`=first inquiry status, `currency='IDR'`, `exchange_rate=1`.

### Quotations (`Quotations.vue`) — route `Quotations`, doctype **CRM Quotation** **[CUSTOM]**
- List pattern; views list/group_by/kanban. **Create** → `NewQuotation`. (A local `createDoc` via `frappe.client.insert` exists but is unused.)

### Quotation (`Quotation.vue`) — route `Quotation`, doctype **CRM Quotation** **[CUSTOM]**
- **Loads:** `createDocumentResource('CRM Quotation', id)`; side panel `get_sidepanel_sections`; `useDocument` for grid/assignees; child meta `CRM Quotation Product`.
- **Tabs:** Data (DataFields grid), Activity, Comments, Notes, Attachments. Header: copy-id, AssignTo, **state Dropdown**.
- **State machine:** `Draft→Created→Sent→{Approved|Rejected}` (+ Expired); transitions via `quotation.setValue.submit({state})`.
- **Actions:** Save (when dirty & not converted), **Print** (`window.print` of `QuotationPrintContent`), **Convert to Estimation** → `crm.fcrm.doctype.crm_quotation.crm_quotation.convert_to_estimation` → routes to `Estimation` (confirm dialog text is Indonesian), **Void/Unvoid** `crm.api.void.void_document`, Delete → `Quotations`, attach file. When converted, doc + grid locked read-only ("Converted" disabled button).

### NewQuotation (`QuotationNew.vue`) — route `NewQuotation` **[CUSTOM]**
- **Loads:** `useDocument('CRM Quotation')`; `...get_fields_layout`; **available inquiries** via `crm.api.quotation.get_available_inquiries` (Won inquiries not yet quoted) applied as a link filter on `inquiry`.
- Selecting an inquiry auto-fills account/subject via `frappe.client.get_value` on `CRM Inquiry`.
- Live `amount = qty*price` + `net_total`. Defaults: account visible read-only, `date`=today, `currency='IDR'`, `rate=1`, `printed_by`=session user.
- **Save:** `frappe.client.insert` → route to `Quotation`. Cancel → `Quotations`.

### Estimations (`Estimations.vue`) — route `Estimations`, doctype **CRM Estimation** **[CUSTOM]**
- List pattern; **Create** → `NewEstimation`.

### Estimation (`Estimation.vue`) — route `Estimation`, doctype **CRM Estimation** **[CUSTOM]**
- **Loads:** `createDocumentResource('CRM Estimation', id)`; `get_sidepanel_sections`; `useDocument` (grid/assignees). Field overrides: `revenue_items.type_id` link-filter `{item_category:'Revenue'}`, `expense_items.type_id` `{item_category:'Expense'}`.
- **Tabs:** Data, **Route** (`EstimationRoute`), Activity, Comments, Notes, Attachments. No state machine / void / print / convert.
- **Actions:** Assign, attach, **Delete** → `Estimations`.

### NewEstimation (`EstimationNew.vue`) — route `NewEstimation` **[CUSTOM]**
- **Loads:** `useDocument('CRM Estimation')`; `...get_fields_layout`. Same revenue/expense link-filter overrides; defaults `effective_date`=today, `purpose='Customer'`.
- **Create:** `frappe.client.insert` → route to `Estimation`. Cancel → `Estimations`.

### Contacts (`Contacts.vue`) — route `Contacts`, doctype **Contact**
- List pattern; **Create** → `ContactModal`. Org logos from `organizationsStore`.

### Contact (`Contact.vue` / `MobileContact.vue`) — route `Contact`, doctype **Contact**
- **Loads:** `useDocument('Contact', id)`; linked inquiries `crm.api.contact.get_linked_inquiries`; side panel `get_sidepanel_sections`.
- **Layout:** left side panel (image, multi-email/multi-phone dropdowns, address); right `Tabs` = **Inquiries** only (`tabIndex` ref, not persisted).
- **Actions:** edit fields; multi-value email/phone: **set primary** `crm.api.contact.set_as_primary`, **create** `crm.api.contact.create_new`, **edit** `frappe.client.set_value`, **delete** `frappe.client.delete`; create/edit Address (modal); change/remove image; make call; delete (`DeleteLinkedDocModal`; mobile uses `$dialog` + `frappe.client.delete`).

### Organizations (`Organizations.vue`) — route `Organizations` (sidebar label **Accounts**), doctype **CRM Organization**
- List pattern; **Create** → `OrganizationModal`. Special render for `organization_name` (logo) and `website`.

### Organization (`Organization.vue` / `MobileOrganization.vue`) — route `Organization`, doctype **CRM Organization**
- **Loads:** `useDocument('CRM Organization', id)`; `get_sidepanel_sections`; linked `createListResource('CRM Inquiry', {organization})` and `createListResource('Contact', {company_name})`.
- **Tabs:** Inquiries, Contacts (`tabIndex`, not persisted).
- **Actions:** edit fields; **rename** org (`frappe.client.rename_doc` when `organization_name` changes, then re-route) [desktop only]; change/remove logo; open website; create/edit address; delete.

### Notes (`Notes.vue`) — route `Notes`, doctype **FCRM Note**
- Card grid (not a table). `ViewControls` with `hideColumnsButton`, `defaultViewName='Notes View'`.
- **Actions:** Create / edit (card click) via `useDoctypeModal.showModal`; **Delete** `frappe.client.delete`. Deep-link `?open=<note>` opens a card then strips the query.

### Tasks (`Tasks.vue`) — route `Tasks`, doctype **CRM Task**
- List + Kanban (`allowedViews: ['list','kanban']`).
- **Actions:** Create (defaults status `Backlog`, priority `Low`) / edit / **Delete** `frappe.client.delete`; reference-doc button routes to `Inquiry`/`Lead`. Deep-link `?open=<task>` (int). Onboarding `create_first_task`.

### Call Logs (`CallLogs.vue`) — route `Call Logs`, doctype **CRM Call Log**
- List pattern; **Create** → `CallLogModal`. Detail modal loads `crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log`. Deep-link `?open=<name>`.

### Dashboard (`Dashboard.vue`) — route `Dashboard` (TypeScript)
- **Loads:** `crm.api.dashboard.get_dashboard` (params from/to date + user). Save layout: `frappe.client.set_value` on `CRM Dashboard` "Manager Dashboard". Reset: `crm.api.dashboard.reset_to_default`.
- **UI:** date-range presets (Last 7/30/60/90 Days + Custom Range), Sales User filter (`Link` to User), `DashboardGrid`, `AddChartModal`. Admin/manager-gated **Edit / Add Chart / Reset / Save** (drag reorder grid).

### DataImport (`DataImport.vue`) — routes `DataImportList` / `NewDataImport` / `DataImport`
- Thin wrapper over frappe-ui's `DataImport` component (upload → map → run import). `doctypeMap` covers CRM Lead, CRM Inquiry, Contact, CRM Task, CRM Organization, CRM Call Log (each with list/page routes).

### Welcome (`Welcome.vue`) — route `Welcome`
- Onboarding splash: "Add Sample Data" / "Connect your Email" cards (no handlers — placeholders) + "Or create leads manually" → `LeadModal`.

### MobileNotification (`MobileNotification.vue`) — route `Notifications`
- Notifications list from `notificationsStore`. Click → `mark_doc_as_read` + navigate (Lead/Inquiry anchor via hash). "Mark all as read". Socket `crm_notification` triggers reload.

### InvalidPage / NotPermitted
- **InvalidPage:** "Invalid page or not permitted to access" + button → `Leads`.
- **NotPermitted:** "Access Denied" card + "Login with Different Account" → `sessionStore.logout`. Rendered standalone (outside the shell).

---

## 6. Stores & Data Layer

### 6.1 Backend communication primitives (frappe-ui)
- `createResource({ url, params, cache, auto, transform, onSuccess, onError })` — single RPC to a whitelisted method (`/api/method/<dotted.path>`).
- `createListResource({ doctype, fields, filters, orderBy, ... })` — list fetch (`frappe.client.get_list`-style).
- `createDocumentResource({ doctype, name })` — single doc with `.doc`, `.save`, `.setValue`, `.delete`, `.reload`, realtime.
- `call('<method>', params)` — one-off RPC.
- All go through the Frappe REST API; auth via session cookie (`user_id`).

### 6.2 Pinia / module stores (`src/stores/`)

| Store | Type | Holds / Key endpoints |
|---|---|---|
| `session.js` (`crm-session`) | Pinia | `user` (from `user_id` cookie), `isLoggedIn`; `login` (`login`), `logout` (`logout`). |
| `users.js` (`crm-users`) | Pinia | `crm.api.session.get_users` → all users + CRM users; `getUser`, `isAdmin`/`isManager`/`isSalesUser`/`isTelephonyAgent`/`isWebsiteUser`, `isCrmUser` (used by permission guard). Roles: System Manager / Sales Manager / Sales User. |
| `views.js` (`crm-views`) | Pinia | `crm.api.views.get_views` → all saved views; derives `pinnedViews`, `publicViews`, `standardViews` (keyed `"<doctype> <type>"`), `defaultView`. `getView/getDefaultView/getPinnedViews/getPublicViews/reload`. Central to routing + sidebar. |
| `statuses.js` (`crm-statuses`) | Pinia | listResources for `CRM Lead Status`, `CRM Inquiry Status`, `CRM Communication Status` (name/color/position/type). `getLeadStatus/getInquiryStatus`, `statusOptions(doctype, statuses, onChange)` (builds dropdown w/ indicator color + telemetry). |
| `organizations.js` (`crm-organizations`) | Pinia | `crm.api.session.get_organizations` → name→org map (logos). `getOrganization`. |
| `notifications.js` (`crm-notifications`) | Pinia + module | `crm.api.notifications.get_notifications` (`notifications`), `unreadNotificationsCount` (computed), `crm.api.notifications.mark_as_read`; `visible` ref + `toggle()` for the panel. |
| `meta.js` (module `getMeta`) | factory | `frappe.desk.form.load.getdoctype` per doctype → `doctypesMeta`, `userSettings`. Field helpers (`getFields`, currency/float/percent formatters, grid settings, `saveUserSettings` via `frappe.model.utils.user_settings.save`). |
| `settings.js` (module `getSettings`) | module | `createDocumentResource('FCRM Settings')` → `settings` (dropdown_items, etc.) + `brand` (name/logo/favicon). |
| `global.js` (`crm-global`) | Pinia | exposes `$dialog`, `$socket`; `makeCall/setMakeCall` bridge for telephony. |
| `theme.js` | module | `theme` (`useStorage`), `setTheme`/`toggleTheme` (sets `data-theme` attr). |

### 6.3 Document & script layer (`src/data/`)
- **`document.js` (`useDocument(doctype, docname)`):** the workhorse for every detail/new page. Wraps `createDocumentResource` (or a reactive `__newDocument` stub when no name). Provides cached `document` (doc + save/setValue/delete), `assignees` (`crm.api.doc.get_assigned_users`), `permissions` (`frappe.client.get_doc_permissions`), and a full **form-script lifecycle**: `triggerOnLoad/Render/BeforeCreate/Validate/Save/Error/Change`, row add/remove, button triggers, `triggerConvertToInquiry`, `triggerOnCreateLead`, mandatory-field checks, attachment tracking, `setFieldHtml`/`fieldPropertyOverrides`. Save is wrapped to run validate + mandatory checks first. Toasts on success/error/permission/mandatory.
- **`script.js` (`getScript(doctype, view)`):** loads form scripts from two sources — **file-based** controllers in `src/doctypes/<slug>/<view>.js` (Vite `import.meta.glob`) and **DB-based** `CRM Form Script` records (filtered by `dt`, `view`, `enabled`). Compiles classes (parent + child-table controllers), injects helpers (`createDialog`, `toast`, `socket`, `router`, `call`, `formDialog`, `throwError`, `crm.makePhoneCall`, `crm.openSettings`) and a doc proxy, and adds prototype helpers (`getRow`, `actions`/`statuses` getters/setters, `setFieldHtml/Property/Properties`, `removeFieldProperty`, `getField`). This is the per-doctype customization mechanism (see MEMORY: file-based onchange/auto-fill scripts).

---

## 7. Backend Endpoint Map (page → method highlights)

| Concern | Method |
|---|---|
| List data (all lists) | `crm.api.doc.get_data` |
| Quick filters | `crm.api.doc.get_quick_filters` / `update_quick_filters` |
| Assignees / permissions | `crm.api.doc.get_assigned_users`, `frappe.client.get_doc_permissions` |
| Views CRUD | `crm.api.views.get_views`; `...crm_view_settings.*` (create_or_update_standard_view, set_as_default, public, pin, delete, fetch_and_update_kanban_columns) |
| Side-panel / field layout | `...crm_fields_layout.get_sidepanel_sections`, `...crm_fields_layout.get_fields_layout` |
| Users / orgs / statuses | `crm.api.session.get_users`, `crm.api.session.get_organizations`, list of `CRM Lead/Inquiry/Communication Status` |
| Lead→Inquiry convert | `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_inquiry` |
| Inquiry contacts | `crm.fcrm.doctype.crm_inquiry.api.get_inquiry_contacts`; `crm_inquiry.{add_contact,remove_contact,set_primary_contact}` |
| Contact multi-value | `crm.api.contact.{get_linked_inquiries,set_as_primary,create_new}` |
| Quotation **[CUSTOM]** | `crm.api.quotation.get_available_inquiries`; `...crm_quotation.convert_to_estimation` |
| Void **[CUSTOM]** | `crm.api.void.void_document` (Lead, Inquiry, Quotation) |
| Dashboard | `crm.api.dashboard.{get_dashboard,reset_to_default}` |
| Call log | `...crm_call_log.get_call_log` |
| Notifications | `crm.api.notifications.{get_notifications,mark_as_read}` |
| Onboarding | `crm.api.onboarding.{get_first_lead,get_first_inquiry}` |
| Generic | `frappe.client.{insert,set_value,get_value,delete,rename_doc}`, `frappe.desk.form.load.getdoctype`, `frappe.desk.reportview.export_query`, `frappe.desk.like.toggle_like`, `frappe.desk.form.assign_to.remove_multiple`, `frappe.apps.get_apps` |

---

## 8. Rebuild Notes (Go target)
- **Mobile vs desktop** is decided client-side at load by viewport width (640 for layout, 768 for Lead/Inquiry/Contact/Organization detail components). A Go-templated UI can decide server-side or keep two templates.
- **Routing semantics to preserve:** `/crm` base; list routes have `:viewType` (list/kanban/group_by) and optional `?view=<savedView>`; detail routes restore last tab via `localStorage` + URL hash; `Home` redirects to the user's default view; non-CRM users → Not Permitted; logged-out → `/login?redirect-to=/crm`.
- **The list engine is generic** (`crm.api.doc.get_data` + view settings). Most list behavior is configuration, not per-page code.
- **[CUSTOM] divergences from stock Frappe CRM:** sidebar relabels (Accounts, Inquiries) and order; added Dashboard/Quotations/Estimations doctypes & pages; Void/Unvoid flow; Quotation state machine + convert-to-Estimation + print; IDR/exchange-rate defaults; read-only-after-convert lock; mobile sidebar still shows the stock labels (desktop/mobile nav are out of sync).
