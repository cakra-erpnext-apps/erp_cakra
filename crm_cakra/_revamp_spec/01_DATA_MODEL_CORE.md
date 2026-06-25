# Frappe CRM — Core Data Model Specification (for Go rebuild)

> Source app: `D:\System_ERPNext\crm` (Frappe CRM, module **FCRM**).
> This document is a **build specification**, transcribed verbatim from the doctype JSON + Python controllers. Every field, link, permission, and controller rule is listed. Use it to recreate the schema and business logic in Go from scratch.

## How to read this for a Go rebuild

Frappe doctype → Go mapping conventions used throughout:

| Frappe fieldtype | DB column / Go meaning |
|---|---|
| `Data`, `Small Text`, `Text`, `Text Editor`, `HTML` | `string` (TEXT) |
| `Select` | `string` enum — options are `\n`-separated; a leading blank means "" is allowed |
| `Link` | `string` **foreign key** to the linked doctype's `name` (PK). Not enforced by DB FK in Frappe; enforce in app layer |
| `Dynamic Link` | `string` FK whose target doctype is named by a sibling field (`options` points to that field) |
| `Table` | **one-to-many child rows** in a separate table; child rows carry `parent`, `parenttype`, `parentfield`, `idx` |
| `Table MultiSelect` | one-to-many child table holding only link rows (junction table) |
| `Check` | `int` 0/1 (bool) |
| `Int` | `int64` |
| `Float`, `Percent` | `float64` |
| `Currency` | `decimal` (store as numeric/decimal, not float) — `options` names the currency field |
| `Date` | date | `Datetime` → timestamp | `Duration` → seconds (`int`) |
| `Attach`, `Attach Image` | `string` (file URL) |
| `Autocomplete` | `string` with suggested options |
| Section Break / Column Break / Tab Break | **layout only**, NOT stored as columns. Listed here for UI fidelity only |

Every doctype also has the standard Frappe meta columns: `name` (PK, string), `owner`, `creation`, `modified`, `modified_by`, `docstatus` (int), `idx` (int), plus `_assign`, `_comments`, `_user_tags`, `_liked_by` (JSON text). Child tables additionally have `parent`, `parenttype`, `parentfield`.

---

## Index of doctypes covered

**Core business entities (parent doctypes):**
1. CRM Lead (`crm_lead`)
2. CRM Deal (`crm_deal`) — the "Inquiry"
3. CRM Organization (`crm_organization`)
4. CRM Task (`crm_task`)
5. FCRM Note (`fcrm_note`)
6. CRM Call Log (`crm_call_log`)
7. CRM Product (`crm_product`)
8. CRM Estimation (`crm_estimation`)
9. CRM Quotation (`crm_quotation`)
10. CRM Transportation Mode (`crm_transportation_mode`) — master/lookup

**Child tables (`istable: 1`):**
11. CRM Contacts (`crm_contacts`) — child of CRM Deal
12. CRM Products (`crm_products`) — child of CRM Lead & CRM Deal
13. CRM Estimation Detail (`crm_estimation_detail`) — child of CRM Estimation (used twice: revenue & expense)
14. CRM Quotation Product (`crm_quotation_product`) — child of CRM Quotation
15. CRM Quotation Additional (`crm_quotation_additional`) — child table (defined but not wired into Quotation `field_order`)
16. CRM Deal Transportation Mode (`crm_deal_transportation_mode`) — Table MultiSelect junction child of CRM Deal

> **Note on `crm_contact`:** there is **no** standalone `crm_contact` doctype in this app. Contacts are stored in Frappe core's `Contact` doctype; CRM references it via the `CRM Contacts` child table and `Link → Contact` fields. The child table is `CRM Contacts` (plural), documented below.

> **Heavily customized doctypes** (CMI / expedition business): CRM Lead, CRM Deal, CRM Estimation, CRM Quotation, CRM Transportation Mode, CRM Deal Transportation Mode. These carry forwarder/logistics fields (transportation mode, incoterms, cargo, ports, container/isotank job services) and a custom `INQ/EST/QT/LD` numbering scheme + a `void` soft-delete block.

---

# 1. CRM Lead

| Property | Value |
|---|---|
| name (doctype) | `CRM Lead` |
| module | FCRM |
| istable | 0 |
| issingle | 0 |
| is_submittable | 0 |
| autoname | **controller `autoname()`** — see below (NOT the JSON `naming_series`) |
| naming_rule | "" (overridden by code) |
| title_field | `lead_name` |
| track_changes | 1 |
| email_append_to | 1 (inbound email creates/updates Lead) |
| sender_field | `email`; sender_name_field | `first_name` |
| image_field | `image` |
| default sort | `modified DESC` |

### Autoname (controller `autoname()`)
Format `LD/{counter}/CMI/{yy}`, where `yy` = 2-digit current year and `counter` is a 4-digit zero-padded series **keyed per year** (`make_autoname("LD-{yy}-.####.")`), so it resets every year. Example: `LD/0001/CMI/26`. The JSON `naming_series` field default `CRM-LEAD-.YYYY.-` is effectively ignored.

### Fields (full, in layout order)

| # | fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | in_std_filter | hidden | depends_on | fetch_from | unique |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | **person_tab** | Tab Break | Person | | | | | | | | | | |
| | salutation | Link | Salutation | Salutation | | | | | | | | | |
| | first_name | Data | First Name | | **1** | | | | | | | | |
| | last_name | Data | Last Name | | | | | | | | | | |
| | **column_break_opsm** | Column Break | | | | | | | | | | | |
| | lead_name | Data | Full Name | | | | | | 1 | | | | |
| | email | Data | Email | Email | | | | | 1 | | | | |
| | mobile_no | Data | Mobile No. | Phone | | | | | | | | | |
| | **details** | Tab Break | Details | | | | | | | | | | |
| | organization | Data | Organization | | | | | | 1 | | | | |
| | website | Data | Website | | | | | | | | | | |
| | territory | Link | Territory | CRM Territory | | | | | | | | | |
| | industry | Link | Industry | CRM Industry | | | | | | | | | |
| | job_title | Data | Job Title | | | | | | | | | | |
| | source | Link | Source | CRM Lead Source | | | | | | | | | |
| | lead_owner | Link | Lead Owner | User | | | | | | | | | |
| | **organization_tab** | Tab Break | Others | | | **1 (read_only)** | | | | | | | |
| | **section_break_uixv** | Section Break | | | | | | | | | | | |
| | naming_series | Select | Series | `CRM-LEAD-.YYYY.-` | | | `CRM-LEAD-.YYYY.-` | | | | | | |
| | middle_name | Data | Middle Name | | | | | | | | | | |
| | gender | Link | Gender | Gender | | | | | | | | | |
| | phone | Data | Phone | Phone | | | | | | | | | |
| | **column_break_dbsv** | Column Break | | | | | | | | | | | |
| | status | Link | Status | CRM Lead Status | **1** | | | 1 | 1 | | | | (search_index) |
| | no_of_employees | Select | No. of Employees | `1-10 / 11-50 / 51-200 / 201-500 / 501-1000 / 1000+` | | | | | | | | | |
| | annual_revenue | Currency | Annual Revenue | | | | | | | | | | |
| | image | Attach Image | Image | | | | | | | **1** | | | |
| | converted | Check | Converted | | | | 0 | 1 | 1 | | | | |
| | **products_tab** | Tab Break | Products | | | | | | | | | | |
| | products | Table | Products | **CRM Products** | | | | | | | | | |
| | **section_break_ggwh** | Section Break | | | | | | | | | | | |
| | total | Currency | Total | (curr: currency) | | 1 | | | | | | | |
| | **column_break_uisv** | Column Break | | | | | | | | | | | |
| | net_total | Currency | Net Total (after discount) | (curr: currency) | | 1 | | | | | | | |
| | **sla_tab** | Tab Break | SLA | | | 1(ro) | | | | | | | |
| | sla | Link | SLA | CRM Service Level Agreement | | | | | | | | | |
| | sla_creation | Datetime | SLA Creation | | | 1 | | | | | | | |
| | **column_break_ffnp** | Column Break | | | | | | | | | | | |
| | sla_status | Select | SLA Status | `"" / First Response Due / Rolling Response Due / Failed / Fulfilled` | | 1 | | | | | | | |
| | communication_status | Link | Communication Status | CRM Communication Status | | | `Open` | | | | | | |
| | **response_details_section** | Section Break | Response Details | | | | | | | | | | |
| | response_by | Datetime | Response By | | | 1 | | | | | | | |
| | **column_break_pweh** | Column Break | | | | | | | | | | | |
| | first_response_time | Duration | First Response Time | | | 1 | | | | | | | |
| | first_responded_on | Datetime | First Responded On | | | 1 | | | | | | | |
| | **section_break_xnpz** | Section Break | | | | | | | | | | | |
| | rolling_responses | Table | Rolling Responses | CRM Rolling Response Time | | | | | | | | | |
| | **section_break_kikl** | Section Break | | | | | | | | | | | |
| | **column_break_ygds** | Column Break | | | | 1(ro) | | | | | | | |
| | last_response_time | Duration | Last Response Time | | | 1 | | | | | | | |
| | **column_break_tcqb** | Column Break | | | | | | | | | | | |
| | last_responded_on | Datetime | Last Responded On | | | 1 | | | | | | | |
| | **log_tab** | Tab Break | Log | | | 1(ro) | | | | | | | |
| | status_change_log | Table | Status Change Log | CRM Status Change Log | | | | | | | | | |
| | **syncing_tab** | Tab Break | Syncing | | | | | | | | | | |
| | facebook_lead_id | Data | Facebook Lead ID | | | | | | | | | | **1** |
| | **column_break_ixmu** | Column Break | | | | | | | | | | | |
| | facebook_form_id | Data | Facebook Form ID | | | | | | | | | | |
| | **lost_details_tab** | Tab Break | Lost Details | | | | | | | | | | |
| | lost_reason | Link | Lost Reason | CRM Lost Reason | | | | | | | | | |
| | lost_notes | Text | Lost Notes | | | | | | | | mandatory_depends_on: `lost_reason == "Other"` | | |
| | **section_company_legal** | Section Break | Company / Legal | | | | | | | | | | |
| | nib | Data | NIB | | | | | | | | | | |
| | npwp | Data | NPWP | | | | | | | | | | |
| | type_industry | Data | Type Industry | | | | | | | | | | |
| | target_goals | Small Text | Target Goals | | | | | | | | | | |
| | **section_address** | Section Break | Address | | | | | | | | | | |
| | address | Small Text | Address | | | | | | | | | | |
| | village | Data | Village | | | | | | | | | | |
| | sub_district | Data | Sub-District | | | | | | | | | | |
| | regency | Data | Regency | | | | | | | | | | |
| | city | Data | City | | | | | | | | | | |
| | postal_code | Data | Postal Code | | | | | | | | | | |
| | **void_section** | Section Break | Void | | | | | | | | | | |
| | is_void | Check | Void | | | 1 | 0 | | 1 | | | | |
| | void_reason | Small Text | Void Reason | | | 1 | | | | | | | |
| | void_at | Datetime | Voided At | | | 1 | | | | | | | |
| | void_by | Link | Voided By | User | | 1 | | | | | | | |

**Custom/non-standard fields (CMI):** `nib`, `npwp`, `type_industry`, `target_goals` (Company/Legal); full address block `address/village/sub_district/regency/city/postal_code`; void block `is_void/void_reason/void_at/void_by`; `facebook_lead_id` (unique) / `facebook_form_id` (lead-ads sync); `products` child table + `total/net_total` (a lead can carry product lines like a quote).

### Links (connected-doctype tabs)
`links: []` — none defined in JSON.

### Permissions
| role | read | write | create | delete | submit | email | print | export | report | share |
|---|---|---|---|---|---|---|---|---|---|---|
| System Manager | 1 | 1 | 1 | 1 | - | 1 | 1 | 1 | 1 | 1 |
| Sales Manager | 1 | 1 | 1 | 1 | - | 1 | 1 | 1 | 1 | 1 |
| Sales User | 1 | 1 | 1 | 1 | - | 1 | 1 | 1 | 1 | 1 |

### Controller logic (`crm_lead.py`, class `CRMLead`)
- **autoname()** — `LD/{counter}/CMI/{yy}` per-year counter (see above).
- **before_validate()** → `set_sla()`: if `sla` empty, look up an SLA via `get_sla(self)`; if none, clear `first_responded_on`/`first_response_time`; else set `sla`.
- **validate()** runs in order:
  - `validate_status()` — if new and no status: set `"New"` if that status exists, else first `CRM Lead Status` of type `Open`.
  - `set_full_name()` — `lead_name = "{salutation} {first_name} {middle_name} {last_name}"` (skip blanks) when `first_name` present.
  - `set_lead_name()` — if `lead_name` still empty: require org or email (else throw "A Lead requires either a person's name or an organization's name"), then fall back to organization → email local-part → `"Unnamed Lead"`.
  - `set_title()` — `title = organization or lead_name`.
  - `validate_email()` — validate email format; throw if `email == lead_owner`; set gravatar `image` from email if new/no image.
  - `validate_lost_reason()` — if status type is `Lost`: require `lost_reason`; if reason is `"Other"`, require `lost_notes`. On status change, add/remove the lost-reason sidebar section.
  - On change of `lead_owner` (existing doc): `share_with_agent()` + `assign_agent()`.
  - On change of `status`: `add_status_change_log(self)` (appends to `status_change_log` child).
- **after_insert()** — share/assign to `lead_owner`.
- **before_save()** → `apply_sla()`: if `sla` set, load that SLA doc and call `.apply(self)`.
- Methods: `assign_agent()` (creates ToDo assignment), `share_with_agent()` (DocShare write), `create_contact()` (creates core `Contact`, dedupes by Contact Email/Phone), `create_organization()` (creates/links `CRM Organization`), `update_lead_contact()`, `contact_exists()`, `create_deal()` (maps lead → new `CRM Deal`, excludes SLA/status/contact fields, maps `lead_owner→deal_owner`), `convert_to_deal()`.
- **Whitelisted module function** `convert_to_deal(lead, doc, deal, existing_contact, existing_organization)`: permission check; throw if already converted; set status to `Converted` (or `Qualified`); set `converted=1`; if SLA + `Replied` comm-status exists, set `communication_status="Replied"`; then create Contact + Organization + Deal.
- Statics: `get_non_filterable_fields()` → `["converted"]`; `default_list_data()`; `default_kanban_settings()` (kanban by `status`).

### Go struct shape (abridged)
```go
type CRMLead struct {
    Name string // PK "LD/0001/CMI/26"
    Salutation, FirstName, MiddleName, LastName *string
    LeadName, Email, MobileNo, Phone, Website *string
    Organization *string // free text, NOT FK
    Territory, Industry *string // FK CRMTerritory / CRMIndustry
    Source, LeadOwner *string // FK CRMLeadSource / User
    Status string // FK CRMLeadStatus (reqd)
    NoOfEmployees, SlaStatus *string // enums
    AnnualRevenue, Total, NetTotal decimal.Decimal
    Converted, IsVoid bool
    Sla *string; SlaCreation, ResponseBy, FirstRespondedOn, LastRespondedOn *time.Time
    FirstResponseTime, LastResponseTime *int // seconds
    CommunicationStatus *string
    FacebookLeadID *string // unique
    LostReason *string; LostNotes *string
    Nib, Npwp, TypeIndustry, TargetGoals *string
    Address, Village, SubDistrict, Regency, City, PostalCode *string
    VoidReason *string; VoidAt *time.Time; VoidBy *string
    Products          []CRMProducts          // one-to-many
    RollingResponses  []CRMRollingResponseTime
    StatusChangeLog   []CRMStatusChangeLog
}
```

---

# 2. CRM Deal (a.k.a. "Inquiry")

| Property | Value |
|---|---|
| name | `CRM Deal` |
| module | FCRM |
| istable | 0 |
| issingle | 0 |
| is_submittable | 0 |
| autoname | **controller** `INQ/{counter}/CMI/{yy}` (per-year counter). JSON `naming_series` default `INQ/.####./CMI/.YY.` is descriptive only. |
| title_field | `name` |
| track_changes | 1 |
| hide_name_column | 1 |
| default sort | `modified DESC` |

### Autoname (controller)
`INQ/{counter}/CMI/{yy}` — 4-digit per-year counter via `make_autoname("INQ-{yy}-.####.")`. Example `INQ/0001/CMI/26`.

### Fields (full, in layout order)

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | in_std_filter | depends_on | fetch_from | unique |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **organization_tab** | Tab Break | Organization | | | | | | | | | |
| naming_series | Select | Naming Series | (no options list) | | | `INQ/.####./CMI/.YY.` | | | | | |
| organization | Link | Organization | **CRM Organization** | | | | | 1 | | | |
| next_step | Data | Next Step | | | | | | | | | |
| **column_break_ijan** | Column Break | | | | | | | | | | |
| status | Link | Status | **CRM Deal Status** | **1** | | | 1 | 1 | | | (search_index) |
| deal_owner | Link | Deal Owner | User | | | | | | | | |
| **section_break_jgpm** | Section Break | | | | | | | | | | |
| probability | Percent | Probability | | | | | | | | | |
| expected_deal_value | Currency | Expected Deal Value | (curr: currency) | | | | | | | | |
| deal_value | Currency | Deal Value | (curr: currency) | | | | | | | | |
| **column_break_kpxa** | Column Break | | | | | | | | | | |
| expected_closure_date | Date | Expected Closure Date | | | | | | | | | |
| closed_date | Date | Closed Date | | | | | | | | | |
| **contacts_tab** | Tab Break | Contacts | | | | | | | | | |
| contacts | Table | Contacts | **CRM Contacts** | | | | | | | | |
| contact | Link | Contact | **Contact** (core) | | | | | | | | |
| **lead_details_tab** | Tab Break | Lead Details | | | | | | | | | |
| lead | Link | Lead | CRM Lead | | | | | | | | |
| source | Link | Source | CRM Lead Source | | | | | | | | |
| **column_break_wsde** | Column Break | | | | | | | | | | |
| lead_name | Data | Lead Name | | | | | | | | | |
| **organization_details_section** | Section Break | Organization Details | | | | | | | | | |
| organization_name | Data | Organization Name | | | | | | | | | |
| website | Data | Website | | | | | | | | `.website` | |
| no_of_employees | Select | No. of Employees | `1-10…1000+` | | | | | | | | |
| job_title | Data | Job Title | | | | | | | | | |
| **column_break_xbyf** | Column Break | | | | | | | | | | |
| territory | Link | Territory | CRM Territory | | | | | | | `.territory` | |
| currency | Link | Currency | Currency | | | | | | | | |
| exchange_rate | Float | Exchange Rate | | | | 1 | | | | | |
| annual_revenue | Currency | Annual Revenue | (curr: currency) | | | | | | | `.annual_revenue` | |
| industry | Link | Industry | CRM Industry | | | | | | | | |
| **person_section** | Section Break | Person | | | | | | | | | |
| salutation | Link | Salutation | Salutation | | | | | | | | |
| first_name | Data | First name | | | | | | | | | |
| last_name | Data | Last name | | | | | | | | | |
| **column_break_xjmy** | Column Break | | | | | | | | | | |
| email | Data | Primary email | Email | | | | | 1 | | | |
| mobile_no | Data | Primary mobile no | Phone | | | | | | | | |
| phone | Data | Primary phone | Phone | | | | | | | | |
| gender | Link | Gender | Gender | | | | | | | | |
| **products_tab** | Tab Break | Products | | | | | | | | | |
| products | Table | Products | **CRM Products** | | | | | | | | |
| **section_break_ccbj** | Section Break | | | | | | | | | | |
| total | Currency | Total | (curr: currency) | | 1 | | | | | | |
| **column_break_udbq** | Column Break | | | | | | | | | | |
| net_total | Currency | Net Total (after discount) | (curr: currency) | | 1 | | | | | | |
| **sla_tab** | Tab Break | SLA | | | 1(ro) | | | | | | |
| sla | Link | SLA | CRM Service Level Agreement | | | | | | | | |
| sla_creation | Datetime | SLA Creation | | | 1 | | | | | | |
| **column_break_pfvq** | Column Break | | | | | | | | | | |
| sla_status | Select | SLA Status | `"" / First Response Due / Rolling Response Due / Failed / Fulfilled` | | 1 | | | | | | |
| communication_status | Link | Communication Status | CRM Communication Status | | | `Open` | | | | | |
| **response_details_section** | Section Break | Response Details | | | | | | | | | |
| response_by | Datetime | Response By | | | 1 | | | | | | |
| **column_break_hpvj** | Column Break | | | | | | | | | | |
| first_response_time | Duration | First Response Time | | | 1 | | | | | | |
| first_responded_on | Datetime | First Responded On | | | 1 | | | | | | |
| **section_break_mwvg** | Section Break | | | | | | | | | | |
| rolling_responses | Table | Rolling Responses | CRM Rolling Response Time | | | | | | | | |
| **section_break_jgdr** | Section Break | | | | | | | | | | |
| last_response_time | Duration | Last Response Time | | | 1 | | | | | | |
| **column_break_evzj** | Column Break | | | | | | | | | | |
| last_responded_on | Datetime | Last Responded On | | | 1 | | | | | | |
| **log_tab** | Tab Break | Log | | | 1(ro) | | | | | | |
| status_change_log | Table | Status Change Log | CRM Status Change Log | | | | | | | | |
| **lost_details_tab** | Tab Break | Lost Details | | | | | | | | | |
| lost_reason | Link | Lost Reason | CRM Lost Reason | | | | | | | | |
| lost_notes | Text | Lost Notes | | | | | | | mandatory_depends_on: `lost_reason=="Other"` | | |
| **column_break_klqj** | Column Break | | | | | | | | | | |
| type_inquiry | Select | Type of Inquiry | (see enum below) | | | | | | | | |
| shipper_consignee | Data | Shipper/Consignee | | | | | | | | | |
| transportation_mode | **Table MultiSelect** | Transportation Mode | **CRM Deal Transportation Mode** | | | | | | | | |
| incoterms | Select | Incoterms | (see enum below) | | | | | | | | |
| date_shipment | Date | Date of Shipment | | | | | | | | | |
| **column_break_qlqj** | Column Break | | | | | | | | | | |
| qty_volume | Data | Quantity/Volume | | | | | | | | | |
| port_pol_destination_detail_address | Data | Port/POL/Destination Detail Address | | | | | | | | | |
| cargo_commodity | Data | Cargo Commodity / Type / HS Code | | | | | | | | | |
| cargo_weight | Data | Cargo Weight (KG) / Volume / Packaging | | | | | | | | | |
| status_cargo | Data | Status of Cargo | | | | | | | | | |
| **column_break_rlqj** | Column Break | | | | | | | | | | |
| job_service | Select | Job Service | (large enum, ~50 logistics services — see below) | | | | | | | | |
| service_type | Select | Service Type | `"" / New Customer / New Job Service / New Product / Existing Job Service / Existing Product` | | | | | | | | |
| business_unit | Select | Business Unit | (enum below) | | | | | | | | |
| remarks | Text | Remarks | | | | | | | | | |
| deal_date | Date | Deal Date | | | | | | | | | |
| cargo_packaging | Data | Cargo Packaging | | | | | | | | | |
| origin | Data | Origin | | | | | | | | | |
| destination | Data | Destination | | | | | | | | | |
| qty | Float | Quantity | | | | | | | | | |
| rate | Currency | Rate | (curr: currency) | | | | | | | | |
| estimasi_tarif | Currency | Estimasi Tarif | (curr: currency) | | | | | | | | |
| costing_procurement | Currency | Costing Procurement | (curr: currency) | | | | | | | | |
| subject | Data | Subject | | | | | | | | | |
| **void_section** | Section Break | Void | | | | | | | | | |
| is_void | Check | Void | | | 1 | 0 | | 1 | | | |
| void_reason | Small Text | Void Reason | | | 1 | | | | | | |
| void_at | Datetime | Voided At | | | 1 | | | | | | |
| void_by | Link | Voided By | User | | 1 | | | | | | |

> **Note:** `company`, `branch` etc. are NOT in CRM Deal (those are on CRM Quotation). The `fetch_from` values `.website`, `.territory`, `.annual_revenue` have an empty source-doc prefix in JSON (i.e. broken/legacy fetch definitions); in practice these are populated by form scripts / convert logic, not auto-fetch.

#### Enum: `type_inquiry`
`"" , Container 20, Container 40, Container 45, Domestic, Export, FR ( Flat Rack), Full Container Load, Full Isotank Load, HC (Hight Cube), HD (Heavy Duty), Import, Isotank T11, Isotank T14, Isotank T50, Isotank T75, Less Container Load, OT (Open Top), Product, Service Contract Logistic, STD (Standart), Trucking, Trucking Wingbox`

#### Enum: `incoterms`
`"" , EXW (EX WOKRS), FCA (FREE CARRIER), FAS (FREE ALONGSIDE SHIP), FOB (FREE ON BOARD), CFR (COST & FREIGHT), CIF (COST, INSURANCE & FREIGHT), CPT (COST PAID TO), CIP (CARRIER, INSURANCE PAID TO), DPU (DELIVERED AT PLACE UNLOADED), DAP (DELIVERED AT PLACE), DDP (DELIVERED DUTY PAID)`

#### Enum: `business_unit`
`"" , EMKL (TRUCKING DOMESTIK NON ISOTANK), FF (EXPORT/IMPORT CONTAINER DRY), ISO (LOCAL/ DOMESTIK ISOTANK), LOG (CONTRACT LOGISTICS), PCP (EXPORT ISOTANK), PKGOLEO (PRODUCT)`

#### Enum: `job_service` (logistics/expedition services — ~50 values, store as free-form string in Go)
`Trukcing Container 40ft, Trucking Isotank 25kl, Door To Port Flexitank 18kl, Trucking Container 20ft, Export Service Container 20 Dry, Export Service Container 40 Dry, Export Service Container 20 Reefer, Export Service Container 40 Reefer, Door To Door Isotank, Door To Door Container 20 Dry, Door To Door Container 40 Dry, Door To Door Container 20 Reefer, Doot To Door Container 40 Reefer, Freight LCL, Freight, Container Storage, Isotank, Container - Container 20 Dry, Container - Container 40 Dry, Container - Container 20 & 40 Dry, Container - Container 20 & 40 Reefer, Container - Container 20 Reefer, Container - Container 40 Reefer, EMKL & Trucking - Container 20 Dry, EMKL & Trucking - Container 40 Dry, EMKL & Trucking - Container 20 & 40 Dry, EMKL & Trucking, EMKL & Trucking - Container 20 Reefer, EMKL & Trucking - Container 40 Reefer, Import Door To Door, EMKL & Trucking - Isotank, Door To Port Isotank, Local Service, EMKL & Trucking - Isotank T75, Impor Trucking Container, Export Service Isotank, Impor Service Isotank, Impor Service Container, Door to Door Flexitank, Port To Port, Port To Door Isotank, Other Product, Product Packaging, Product Oleochemical, Repair Container, Toeslagh, Export Service Flexitank, Trucking + Rental Isotank, Door To Port, Cleaning Isotank, Export Isotank & Flexibag` (typos preserved from source).

**Custom/non-standard fields (CMI expedition):** the entire `type_inquiry`, `shipper_consignee`, `transportation_mode` (multiselect), `incoterms`, `date_shipment`, `qty_volume`, `port_pol_destination_detail_address`, `cargo_commodity`, `cargo_weight`, `status_cargo`, `job_service`, `service_type`, `business_unit`, `remarks`, `deal_date`, `cargo_packaging`, `origin`, `destination`, `qty`, `rate`, `estimasi_tarif`, `costing_procurement`, `subject` group — plus the `void` block. These define the forwarder/inquiry domain.

### Links
`links: []` — none.

### Permissions
Same matrix as CRM Lead (System Manager / Sales Manager / Sales User → full read/write/create/delete/email/print/export/report/share).

### Controller logic (`crm_deal.py`, class `CRMDeal`)
- **autoname()** — `INQ/{counter}/CMI/{yy}` (per-year).
- **before_validate()** → `set_sla()` (same pattern as Lead).
- **validate()**:
  - `validate_status()` — if new/no status: set `"Qualification"` if exists else first `Open`-type status.
  - `set_primary_contact()` — if exactly one contact, mark it primary; if a contact arg given, set that one primary and others not.
  - `set_primary_email_mobile_no()` — derive `email/mobile_no/phone` from the primary contact row; throw if more than one primary; clear them if no contacts.
  - On change of `deal_owner` (existing): share + assign agent.
  - On change of `status`: `add_status_change_log()`; if new status type == `Won`, set `closed_date = today`.
  - `validate_forecasting_fields()` — `update_closed_date()` (Won→today), `update_default_probability()` (pull `probability` from CRM Deal Status if 0), `update_expected_deal_value()` (if FCRM Settings `auto_update_expected_deal_value` and a total exists, set `expected_deal_value = net_total or total`). If FCRM Settings `enable_forecasting`: require `expected_deal_value` and `expected_closure_date` (else MandatoryError).
  - `validate_lost_reason()` — same Lost rules as Lead.
  - `update_exchange_rate()` — if `currency` changed or `exchange_rate` empty: set rate=1, or fetch `get_exchange_rate(currency, system_currency)` where system currency = FCRM Settings `currency` (default `USD`). Written via `db_set`.
- **after_insert()** — share/assign to `deal_owner`.
- **before_save()** → `apply_sla()`.
- Statics: `default_list_data()`, `default_kanban_settings()` (kanban by `status`, title by `organization`).
- **Whitelisted module functions:** `add_contact(deal, contact)`, `remove_contact(deal, contact)`, `set_primary_contact(deal, contact)`, `create_deal(doc: dict)` (creates Deal + auto-creates Contact + CRM Organization from the dict, sets first contact primary). Module helpers `create_organization`, `contact_exists`, `create_contact`.

### Go relationship implications
- `organization` → FK to `CRM Organization.name`.
- `lead` → FK to `CRM Lead.name` (the source lead, set on convert).
- `contact` → FK to core `Contact`. `contacts` → one-to-many `CRM Contacts` rows (the deal's contact list; one flagged `is_primary`).
- `transportation_mode` → junction table `CRM Deal Transportation Mode` (Table MultiSelect → many `mode` link rows). Model as `[]string` of transportation-mode names, or a child slice.
- `currency`/`exchange_rate` mirror the multi-currency pattern (rate captured once).

---

# 3. CRM Organization

| Property | Value |
|---|---|
| name | `CRM Organization` |
| module | FCRM |
| istable | 0 |
| issingle | 0 |
| autoname | `field:organization_name` → **PK = organization_name** (naming_rule "By fieldname") |
| title_field | (none) |
| image_field | `organization_logo` |
| default sort | `modified DESC` |

### Fields

| fieldname | fieldtype | label | options | reqd | read_only | in_std_filter | unique |
|---|---|---|---|---|---|---|---|
| organization_name | Data | Organization Name | | | | 1 | **1** |
| no_of_employees | Select | No. of Employees | `1-10…1000+` | | | 1 | |
| currency | Link | Currency | Currency | | | | |
| exchange_rate | Float | Exchange Rate | | | | | |
| annual_revenue | Currency | Annual Revenue | (curr: currency) | | | | |
| organization_logo | Attach Image | Organization Logo | | | | | |
| **column_break_pnpp** | Column Break | | | | | | |
| website | Data | Website | | | | | |
| territory | Link | Territory | CRM Territory | | | 1 | |
| industry | Link | Industry | CRM Industry | | | 1 | |
| address | Link | Address | Address (core) | | | | |

### Links
`links: []`.

### Permissions
Same 3-role matrix (System Manager / Sales Manager / Sales User, full).

### Controller logic (`crm_organization.py`, class `CRMOrganization`)
- **validate()** → `update_exchange_rate()`: identical pattern to CRM Deal (rate=1 or fetched from system currency, `db_set`).
- `default_list_data()` static for the list UI.

### Go note
PK is the literal organization name (string). `currency` FK, `address` FK to core `Address`. Because `organization_name` is the PK and `unique`, renaming the org renames the document (Frappe `allow_rename: 1`).

---

# 4. CRM Task

| Property | Value |
|---|---|
| name | `CRM Task` |
| module | FCRM |
| istable | 0 |
| autoname | `autoincrement` (naming_rule "Autoincrement") → **PK is an auto-increment integer** |
| title_field | (none) |
| default sort | `modified DESC` |

### Fields

| fieldname | fieldtype | label | options | reqd | in_list_view | in_std_filter |
|---|---|---|---|---|---|---|
| title | Data | Title | | **1** | 1 | 1 |
| priority | Select | Priority | `Low / Medium / High` | | | 1 |
| start_date | Date | Start Date | | | | |
| reference_doctype | Link | Reference Document Type | DocType | | | |
| reference_docname | Dynamic Link | Reference Doc | (→ reference_doctype) | | | |
| **column_break_cqua** | Column Break | | | | | |
| assigned_to | Link | Assigned To | User | | | 1 |
| status | Select | Status | `Backlog / Todo / In Progress / Done / Canceled` | | 1 | 1 |
| due_date | Datetime | Due Date | | | | 1 |
| **section_break_bzhd** | Section Break | | | | | |
| description | Text Editor | Description | | | | |

### Links / Permissions
`links: []`. Permissions: same 3-role full matrix.

### Controller logic (`crm_task.py`, class `CRMTask`)
- **after_insert()** → `assign_to()`: if `assigned_to` set, create a Frappe assignment (ToDo) with description `title or description`.
- **validate()** — if existing and `assigned_to` changed: `unassign` previous user, then `assign_to()` new.
- Statics: `default_list_data()`, `default_kanban_settings()` (kanban by `status`).

### Go note
PK = `int64` autoincrement. `reference_doctype` + `reference_docname` form a **polymorphic FK** (the task can attach to CRM Lead / CRM Deal / etc.). `assigned_to` → User; assignment also materialized as a separate ToDo record in Frappe (model assignment side-table if you need parity).

---

# 5. FCRM Note

| Property | Value |
|---|---|
| name | `FCRM Note` |
| module | FCRM |
| istable | 0 |
| autoname | default (hash name) — no autoname/naming_rule set |
| title_field | `title` |
| track_changes | 1 |
| default sort | `modified DESC` |

### Fields

| fieldname | fieldtype | label | options | reqd | default | in_list_view | in_std_filter |
|---|---|---|---|---|---|---|---|
| title | Data | Title | | **1** | | 1 | 1 |
| content | Text Editor | Content | | | | 1 | 1 |
| reference_doctype | Link | Reference Document Type | DocType | | `CRM Lead` | | |
| reference_docname | Dynamic Link | Reference Doc | (→ reference_doctype) | | | | |

### Links (connected-doctype tabs)
```
links: [ { link_doctype: "CRM Call Log", link_fieldname: "note" } ]
```
→ a Note shows related **CRM Call Log** records that point back to it via their `note` field.

### Permissions
Same 3-role full matrix.

### Controller logic (`fcrm_note.py`, class `FCRMNote`)
- No validate/hooks. Only `default_list_data()` static.

### Go note
Polymorphic attach via `reference_doctype` + `reference_docname` (default reference is `CRM Lead`). PK is a random hash string (Frappe default naming).

---

# 6. CRM Call Log

| Property | Value |
|---|---|
| name | `CRM Call Log` |
| module | FCRM |
| istable | 0 |
| autoname | `field:id` → **PK = the `id` field** (naming_rule "By fieldname") |
| title_field | (none) |
| default sort | `modified DESC` |

### Fields

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | in_std_filter | depends_on | unique |
|---|---|---|---|---|---|---|---|---|---|---|
| telephony_medium | Select | Telephony Medium | `"" / Manual / Twilio / Exotel` | | 1 | | 1 | 1 | | |
| **section_break_gyqe** | Section Break | | | | | | | | | |
| id | Data | ID | | | | | | | | **1** |
| from | Data | From Number | | **1** | | | 1 | 1 | | |
| status | Select | Status | `Initiated / Ringing / In Progress / Completed / Failed / Busy / No Answer / Queued / Canceled` | **1** | | | | 1 | | |
| duration | Duration | Duration | | | | | 1 | | | |
| medium | Data | Medium | | | | | | | | |
| start_time | Datetime | Start Time | | | | | | | | |
| reference_doctype | Link | Reference Document Type | DocType | | | `CRM Lead` | | | | |
| reference_docname | Dynamic Link | Reference Name | (→ reference_doctype) | | | | | | | |
| **column_break_ufnp** | Column Break | | | | | | | | | |
| to | Data | To Number | | **1** | | | 1 | 1 | | |
| type | Select | Type | `Incoming / Outgoing` | **1** | | | 1 | 1 | | |
| receiver | Link | Call Received By | User | | | | | | `type=='Incoming'` | |
| caller | Link | Caller | User | | | | | | `type=='Outgoing'` | |
| recording_url | Small Text | Recording URL | | | | | | | | |
| end_time | Datetime | End Time | | | | | | | | |
| note | Link | Note | FCRM Note | | | | | | | |
| **section_break_kebz** | Section Break | | | | | | | | | |
| links | Table | Links | Dynamic Link (core child) | | | | | | | |

### Links / Permissions
`links: []`. Permissions: same 3-role full matrix.

### Controller logic (`crm_call_log.py`, class `CRMCallLog`)
- **before_insert()** — if `id` empty, generate a 12-char hash; if `telephony_medium` empty, set `"Manual"`.
- `has_link()` / `link_with_reference_doc()` — manage the `links` child (`Dynamic Link`) for tying a call to multiple docs (CRM Lead/Deal/Task/Note).
- `as_dict()` override — adds `recording_url_path` API URL when a recording exists.
- Statics: `default_list_data()`, `parse_list_data()`.
- **Whitelisted module functions:** `get_call_log(name)` (returns the call plus resolved `_lead`/`_deal`, `_tasks`, `_notes`), `create_lead_from_call_log(call_log, lead_details)` (creates a CRM Lead pre-filled from the call's `from` number and links the call to the new lead). Module helper `parse_call_log(call)` enriches caller/receiver display.

### Go note
PK = `id` (string, 12-char hash if not provided). `links` is a one-to-many child of core **Dynamic Link** rows (each row: `link_doctype` + `link_name`) — model as `[]LinkRow`. `receiver`/`caller` are mutually exclusive based on `type`.

---

# 7. CRM Product

| Property | Value |
|---|---|
| name | `CRM Product` |
| module | FCRM |
| istable | 0 |
| autoname | `field:product_code` → **PK = product_code** (naming_rule "By fieldname") |
| title_field | `product_name` |
| track_changes | 1 |
| quick_entry | 1 | search_fields | `product_name,description` |
| default sort | `creation DESC` |

### Fields

| fieldname | fieldtype | label | options | reqd | default | in_list_view | unique |
|---|---|---|---|---|---|---|---|
| naming_series | Select | Naming Series | `CRM-PROD-.YYYY.-` | | | | |
| product_code | Data | Product Code | | **1** | | 1 | **1** |
| product_name | Data | Product Name | | | | | |
| **column_break_bpdj** | Column Break | | | | | | |
| disabled | Check | Disabled | | | 0 | | |
| standard_rate | Currency | Standard Selling Rate | | | | | |
| image | Attach Image | Image | | | | | |
| **section_break_rtwm** | Section Break | | | | | | |
| description | Text Editor | Description | | | | | |

### Links / Permissions
`links: []`. Permissions: same 3-role full matrix.

### Controller logic (`crm_product.py`, class `CRMProduct`)
- **validate()** → `set_product_name()`: if `product_name` empty, copy from `product_code`; else `.strip()`.

### Go note
PK = `product_code` (string). `standard_rate` feeds the `CRM Products` child default rate (via a form script when a product is picked in a Lead/Deal product line). This is a CRM-local product master, **distinct** from ERPNext core `Item`.

---

# 8. CRM Estimation

| Property | Value |
|---|---|
| name | `CRM Estimation` |
| module | FCRM |
| istable | 0 |
| autoname | **controller** `EST/{counter}/CMI/{yy}` (per-year), also written to `estimation_no` |
| title_field | `estimation_no` |
| track_changes | 1 |
| default sort | `modified DESC` |

### Autoname (controller)
`EST/{counter}/CMI/{yy}` via `make_autoname("EST-{yy}-.####.")`; sets both `self.name` and `self.estimation_no`.

### Fields (full, in layout order)

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | in_std_filter | depends_on | unique |
|---|---|---|---|---|---|---|---|---|---|---|
| **main_tab** | Tab Break | Main | | | | | | | | |
| estimation_no | Data | Number | | | 1 | | 1 | | | **1** |
| customer_id | Data | Customer | | | | | 1 | | | |
| **column_break_1** | Column Break | | | | | | | | | |
| effective_date | Date | Effective Date | | | | | 1 | | | |
| expired_date | Date | Expired Date | | | | | | | | |
| quo_date | Date | Quotation Date | | | | | | | | |
| quo_no | Link | Quotation No | **CRM Quotation** | | | | | | | |
| **section_break_status** | Section Break | | | | | | | | | |
| purpose | Select | Purpose | `Customer / Agent / Quotation` | | | | | | | |
| estimation_type | Select | Estimation Type | `Expedition / Trading` | | | | | | | |
| job_type | Data | Job Type | | | | | | | | |
| size | Data | Size | | | | | | | | |
| **column_break_status** | Column Break | | | | | | | | | |
| estimation_counter | Int | Estimation Counter | | | | | | | | |
| disabled | Check | Disabled | | | | 0 | | 1 | | |
| disabled_date | Datetime | Disabled Date | | | | | | | `disabled` | |
| disabled_reason | Small Text | Disabled Reason | | | | | | | `disabled` | |
| disabled_fleet | Data | Disabled Fleet | | | | | | | | |
| **remarks_section** | Section Break | Remarks | | | | | | | | |
| remarks | Text | Remarks | | | | | | | | |
| **details_tab** | Tab Break | Details (Income / Expense) | | | | | | | | |
| **revenue_section** | Section Break | Revenue | | | | | | | | |
| revenue_items | Table | Revenue | **CRM Estimation Detail** | | | | | | | |
| **expense_section** | Section Break | Expense | | | | | | | | |
| expense_items | Table | Expense | **CRM Estimation Detail** | | | | | | | |
| **approval_tab** | Tab Break | Approval & Profit | | | | | | | | |
| req_approval | Check | Request Approval | | | | 0 | | | | |
| approved_by | Link | Approved By | User | | | | | | | |
| approved_datetime | Datetime | Approved Datetime | | | | | | | | |
| **column_break_approval** | Column Break | | | | | | | | | |
| rev_inc_tax | Currency | Revenue Including Tax | IDR | | | | | | | |
| est_profit | Currency | Estimated Profit | IDR | | | | | | | |
| est_profit_date | Datetime | Est. Profit Date | | | | | | | | |
| est_profit_by | Link | Est. Profit By | User | | | | | | | |
| **kam_section** | Section Break | Account Manager | | | | | | | | |
| acc_manager | Data | Account Manager | | | | | | | | |
| kam_type | Data | KAM Type | | | | | | | | |
| cs | Data | CS | | | | | | | | |
| cs2 | Data | CS 2 | | | | | | | | |
| **column_break_kam** | Column Break | | | | | | | | | |
| kam_remarks | Small Text | KAM Remarks | | | | | | | | |
| e_department | Data | E-Department | | | | | | | | |
| **route_tab** | Tab Break | Route | | | | | | | | |
| route_type | Data | Route Type | | | | | | | | |
| route1..route4 | Data | Route 1..4 | | | | | | | | |
| **column_break_route** | Column Break | | | | | | | | | |
| route5..route8 | Data | Route 5..8 | | | | | | | | |
| **est_section** | Section Break | Estimated Distance | | | | | | | | |
| est_km | Float | Estimated KM | | | | | | | | |
| est_days | Int | Estimated Days | | | | | | | | |
| **audit_tab** | Tab Break | Audit | | | | | | | | |
| created_by | Data | Created By | | | 1 | | | | | |
| create_date | Datetime | Create Date | | | 1 | | | | | |
| **column_break_audit** | Column Break | | | | | | | | | |
| last_mod_by | Data | Last Modified By | | | 1 | | | | | |
| last_mod | Datetime | Last Modified | | | 1 | | | | | |

(`route1`–`route8` are eight separate Data fields.)

### Links / Permissions
`links: []`. Permissions: same 3-role full matrix.

### Controller logic (`crm_estimation.py`, class `CRMEstimation`)
- **autoname()** — `EST/{counter}/CMI/{yy}`, also sets `estimation_no`.
- **validate()** — unless flag `from_convert` is set, `purpose` MUST be `Customer` or `Agent` (else throw). The `from_convert` path allows `purpose = "Quotation"`.
- **before_save()**:
  - Tag child rows: every `revenue_items` row → `is_expense = 0`; every `expense_items` row → `is_expense = 1` (the **same child doctype `CRM Estimation Detail` is reused for both tables**, distinguished by `is_expense`).
  - `income = Σ revenue_items.amount`; `expense = Σ expense_items.amount`; set `rev_inc_tax = income`; `est_profit = income − expense`.
  - On insert: set `created_by`, `create_date`. Always: set `last_mod_by`, `last_mod`.
- Static `default_list_data()`.

### Go note
Two one-to-many relations point at the **same** child table `CRM Estimation Detail`, differentiated by `parentfield` (`revenue_items` vs `expense_items`) and the `is_expense` flag. In Go either (a) one child table with `parentfield`/`is_expense` discriminators, or (b) two slices `RevenueItems`/`ExpenseItems` of the same struct. `quo_no` → FK CRM Quotation (set when converted from a quotation). `rev_inc_tax`/`est_profit` currency is hard-wired to `IDR`.

---

# 9. CRM Quotation

| Property | Value |
|---|---|
| name | `CRM Quotation` |
| module | FCRM |
| istable | 0 |
| autoname | `format:QT/{####}/CMI/{YYYY}` (naming_rule "By fieldname") — **PK pattern** `QT/0001/CMI/2026` |
| allow_rename | 0 |
| title_field | `subject` |
| track_changes | 1 |
| default sort | `modified DESC` |

### Fields (full, in layout order — note several fields exist in JSON but are NOT in `field_order`, flagged below)

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | in_std_filter | fetch_from / notes | unique |
|---|---|---|---|---|---|---|---|---|---|---|
| **main_tab** | Tab Break | Main | | | | | | | | |
| number | Data | Number | | | | | 1 | 1 | | **1** |
| subject | Data | Subject | | | | | 1 | | fetch_from `inquiry.subject` (fetch_if_empty) | |
| **column_break_1** | Column Break | | | | | | | | | |
| state | Select | State | `Draft / Created / Sent / Approved / Rejected / Expired / Converted` | | 1 | `Draft` | | 1 | | |
| date | Date | Date | | | | `Today` | 1 | | | |
| disabled | Check | Disabled | | | | 0 | | | | |
| **section_break_customer** | Section Break | Customer | | | | | | | | |
| account | Link | Account | **CRM Organization** | | 1 | | 1 | | fetch_from `inquiry.organization` (fetch_if_empty) | |
| account_name | Data | Account Name | | | | | | | fetch_from `account.organization_name` | |
| contact_name | Link | Contact | Contact (core) | | | | | | | |
| **column_break_customer** | Column Break | | | | | | | | | |
| attention | Data | Attention | | | | | | | | |
| inquiry | Link | Inquiry | **CRM Deal** | | | | | | link_filters `{"status":"Won"}` | **1** |
| inquiry_details | HTML | Inquiry Details | | | | | | | | |
| **section_break_company** | Section Break | Company & Currency | | | | | | | | |
| company *(not in field_order)* | Link | Company | Company | | | | | | defined but unwired | |
| branch *(not in field_order)* | Data | Branch | | | | | | | defined but unwired | |
| cost_center | Link | Cost Center | Cost Center | | | | | | | |
| **column_break_company** | Column Break | | | | | | | | | |
| currency | Link | Currency | Currency | | | `IDR` | | | | |
| rate | Float | Exchange Rate | | | | `1.0` (precision 6) | | | | |
| **cargo_tab** | Tab Break | Cargo & Logistics | | | | | | | | |
| cargo | Data | Cargo | | | | | | | | |
| packaging | Data | Packaging | | | | | | | | |
| loading | Small Text | Loading | | | | | | | | |
| unloading | Small Text | Unloading | | | | | | | | |
| **products_tab** | Tab Break | Products | | | | | | | | |
| products | Table | Products | **CRM Quotation Product** | | | | | | | |
| **section_break_total** | Section Break | | | | | | | | | |
| net_total | Currency | Net Total | (curr: currency) | | 1 | | 1 | | | |
| additional1_title | Data | Additional Title | | | | | | | | |
| additional1_detail *(in field_order but field def missing; see additional1_item)* | — | — | | | | | | | layout references `additional1_detail`; JSON defines `additional1_item` (Small Text) | |
| additional1_amount | Data | Additional Amount | | | | | | | | |
| additional2_title | Data | Additional Title 2 | | | | | | | | |
| additional2_detail / additional2_item | Small Text | Additional Item 2 | | | | | | | | |
| additional2_amount | Data | Additional Amount 2 | | | | | | | | |
| **terms_tab** | Tab Break | (terms) | | | | | | | | |
| term_title *(in field_order, no field def)* | — | — | | | | | | | layout-only reference | |
| term_detail | Text | Terms Detail | | | | | | | | |
| TaC *(not in field_order)* | Data | Terms and Conditions Title | | | | `Terms and Conditions` | | | unwired | |
| TaC_detail *(not in field_order)* | Text Editor | Terms and Conditions Detail | | | | | | | unwired | |
| **column_break_terms** | Column Break | | | | | | | | | |
| validity | Data | Validity | | | | | | | | |
| payterm | Data | Payment Term | | | | | | | | |
| rates_tab *(not in field_order)* | Tab Break | Rate Info | | | | | | | unwired | |
| rate_include *(not in field_order)* | Text | Rate Include | | | | | | | unwired | |
| rate_exclude *(not in field_order)* | Text | Rate Exclude | | | | | | | unwired | |
| remark | Small Text | Remark | | | | | | | | |
| **section_print** | Section Break | Print | | | | | | | | |
| printed_by | Link | Printed By | User | | | | | | | |
| **void_section** | Section Break | Void | | | | | | | | |
| is_void | Check | Void | | | 1 | 0 | | 1 | | |
| void_reason | Small Text | Void Reason | | | 1 | | | | | |
| void_at | Datetime | Voided At | | | 1 | | | | | |
| void_by | Link | Voided By | User | | 1 | | | | | |

> **Data-integrity caveats for the rebuild:** The JSON `field_order` references some names with no field definition (`additional1_detail`, `term_title`) and the field defs include some names not in `field_order` (`company`, `branch`, `TaC`, `TaC_detail`, `rates_tab`, `rate_include`, `rate_exclude`, `additional1_item`, `additional2_item`). When rebuilding, treat the **union** of all `fields[]` definitions as the real column set; the layout (`field_order`) is best-effort UI only. The `CRM Quotation Additional` child table (below) is the cleaner intended model for the `additional*` data but is **not wired** into this doctype.

### Links / Permissions
`links: []`. Permissions: same 3-role full matrix.

### Controller logic (`crm_quotation.py`, class `CRMQuotation`)
- **validate()**:
  - If `inquiry` set, enforce **one quotation per inquiry** (throw if another quotation already uses it).
  - If existing and DB `state == "Converted"`, block edits (throw — converted quotations are final/locked).
- **before_save()**:
  - For each product: `amount = qty * price`; `net_total = Σ products.amount`.
  - Audit: on insert set `create_uid`/`create_date`; always set `write_uid`/`write_date`. (Note: these audit fields aren't in the doctype JSON — they'd be created as custom/extra columns; include them in the Go schema.)
  - Default `printed_by = owner or create_uid or session user` if empty.
- **after_insert()** — if from an inquiry, copy the inquiry's assignees (ToDo) onto the quotation (access inheritance via `_copy_assignees`).
- **Whitelisted module function** `convert_to_estimation(quotation)`:
  - Permission + row-lock (`for_update`) to prevent double conversion; block if already `Converted`, if `is_void`, or if an estimation already references `quo_no`.
  - Creates a new `CRM Estimation`: `customer_id = account_name or account`, `quo_no`, `quo_date`, `effective_date = today`, `purpose = "Quotation"`, `remarks = remark`.
  - Copies each quotation product into estimation `revenue_items` (`type_id = product`, `qty`, `amount`, `remarks`, `currency`). **Each product must be a valid core `Item`** (throws otherwise).
  - Sets `est.flags.from_convert = True` (so estimation `validate` accepts `purpose="Quotation"`), inserts, then locks the quotation: `state = "Converted"`, and copies assignees quotation→estimation.

### Go relationship implications
- `account` → FK CRM Organization. `inquiry` → FK CRM Deal (unique, filtered to status Won). `contact_name` → FK core Contact. `cost_center`/`company` → FK ERPNext core.
- `products` → one-to-many `CRM Quotation Product`.
- **State machine:** `Draft → Created → Sent → Approved/Rejected/Expired → Converted`. `Converted` is terminal & read-only. Converting spawns a `CRM Estimation` (1:1 via `quo_no`).
- Conversion chain for access control: **CRM Deal (inquiry) → CRM Quotation → CRM Estimation**, with assignees (ToDo) propagated at each step.

---

# 10. CRM Transportation Mode (master / lookup)

| Property | Value |
|---|---|
| name | `CRM Transportation Mode` |
| module | FCRM |
| istable | 0 |
| autoname | `field:mode_name` → **PK = mode_name** (naming_rule "By fieldname") |
| quick_entry | 1 |
| default sort | `modified DESC` |

### Fields

| fieldname | fieldtype | label | reqd | in_list_view | unique |
|---|---|---|---|---|---|
| mode_name | Data | Transportation Mode | **1** | 1 | **1** |

### Permissions
| role | read | write | create | delete | email | print | export | report | share |
|---|---|---|---|---|---|---|---|---|---|
| System Manager | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| Sales Manager | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| Sales User | 1 | **0** | **0** | **0** | 1 | 1 | 1 | 1 | 1 |

> Sales User has **read-only** access here (no write/create/delete) — different from the other doctypes.

### Controller logic
`crm_transportation_mode.py` — empty (`pass`). No logic.

### Go note
A simple lookup table. PK = `mode_name`. Referenced by `CRM Deal Transportation Mode.mode`.

---

# 11. CRM Contacts (child of CRM Deal)

| Property | Value |
|---|---|
| name | `CRM Contacts` |
| module | FCRM | istable | **1** |
| parent | CRM Deal (`contacts` field) | editable_grid | 1 |

### Fields

| fieldname | fieldtype | label | options | read_only | in_list_view | default | fetch_from |
|---|---|---|---|---|---|---|---|
| contact | Link | Contact | **Contact** (core) | | 1 | | |
| full_name | Data | Full Name | | 1 | 1 | | `contact.full_name` |
| email | Data | Email | | 1 | 1 | | `contact.email_id` |
| **column_break_uvny** | Column Break | | | | | | |
| gender | Link | Gender | Gender | 1 | | | `contact.gender` |
| mobile_no | Data | Mobile No. | Phone | 1 | 1 | | `contact.mobile_no` |
| phone | Data | Phone | Phone | 1 | | | `contact.phone` |
| is_primary | Check | Is Primary | | | 1 | 0 | |

Permissions: `[]` (inherits from parent). Controller `crm_contacts.py`: empty (`pass`).

### Go note
Junction between CRM Deal and core `Contact`. `contact` is the FK; the other display fields are denormalized (fetched from Contact at edit time). Exactly one row should have `is_primary = 1` (enforced by `CRMDeal.set_primary_email_mobile_no`). Standard child cols: `parent, parenttype, parentfield, idx`.

---

# 12. CRM Products (child of CRM Lead & CRM Deal)

| Property | Value |
|---|---|
| name | `CRM Products` |
| module | FCRM | istable | **1** | editable_grid | 1 |
| parents | CRM Lead (`products`), CRM Deal (`products`) |

### Fields

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view | depends_on |
|---|---|---|---|---|---|---|---|---|
| product_code | Link | Product | **CRM Product** | | | | 1 | |
| **column_break_gvbc** | Column Break | | | | | | | |
| product_name | Data | Product Name | | **1** | | | | |
| **section_break_fnvf** | Section Break | | | | | | | |
| qty | Float | Quantity | | | | 1 | | |
| **column_break_ajac** | Column Break | | | | | | | |
| rate | Currency | Rate | (curr: currency) | **1** | | | 1 | |
| **section_break_olqb** | Section Break | | | | | | | |
| discount_percentage | Percent | Discount % | | | | | | |
| **column_break_uvra** | Column Break | | | | | | | |
| discount_amount | Currency | Discount Amount | (curr: currency) | | 1 | | | |
| **section_break_cnpb** | Section Break | | | | | | | |
| **column_break_pozr** | Column Break | | | | | | | |
| amount | Currency | Amount | (curr: currency) | | 1 | | | |
| **column_break_ejqw** | Column Break | | | | | | | |
| net_amount | Currency | Net Amount (after discount) | (curr: currency) | | 1 | | | `discount_percentage` |
| autocomplete | Autocomplete | Autocomplete | `A..Z` | | | | | |

Permissions: `[]`. Controller `crm_products.py`: class is `pass`, but the module defines `create_product_details_script(doctype)` / `get_product_details_script(doctype)` which **generate a client-side CRM Form Script** that does the line math on the parent:
- `qty/rate` → `amount = qty * rate`
- `discount_percentage` → `discount_amount = discount% * amount`; `net_amount = amount − discount_amount`
- parent `total = Σ amount`; parent `net_total = Σ net_amount (or total)`
- picking `product_code` fetches `product_name` + default `rate` from `CRM Product`.

### Go note
Implement the line/total math **server-side** in Go (the original does it in JS form scripts). Child of either CRM Lead or CRM Deal — distinguish by `parenttype`/`parentfield`. `product_code` → FK CRM Product.

---

# 13. CRM Estimation Detail (child of CRM Estimation — used twice)

| Property | Value |
|---|---|
| name | `CRM Estimation Detail` |
| module | FCRM | istable | **1** | editable_grid | 1 | track_changes | 1 |
| parent | CRM Estimation, via **both** `revenue_items` and `expense_items` |

### Fields

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view |
|---|---|---|---|---|---|---|---|
| type_id | Link | Type | **Item** (ERPNext core) | **1** | | | 1 |
| qty | Float | Qty | | | | 1 | 1 |
| jalur | Data | Jalur | | | | | 1 |
| csize | Data | Cont. Size | | | | | 1 |
| area_id | Data | Area | | | | | 1 |
| jenis_karantina | Data | Karantina | | | | | 1 |
| dest_id | Data | Destination | | | | | 1 |
| amount | Currency | Amount | (curr: currency) | **1** | | | 1 |
| per_doc | Check | Per Doc | | | | 0 | |
| by_qty | Check | By Qty | | | | 0 | |
| uom | Data | UOM | | | | | 1 |
| remarks | Small Text | Remarks | | | | | 1 |
| currency | Link | Currency | Currency | | | `IDR` | 1 |
| **section_break_more** | Section Break | More | | | | | |
| is_expense | Check | Is Expense | | | 1 | 0 | |
| supplier_id | Data | Supplier | | | | | |
| shipping_line_id | Data | Shipping Line | | | | | |
| **column_break_more** | Column Break | | | | | | |
| port_id | Data | Port | | | | | |
| sandaran_id | Data | Sandaran | | | | | |

Permissions: `[]`. Controller `crm_estimation_detail.py`: `pass`.

### Go note
Single struct serving two parent slices. `is_expense` (set by parent's `before_save`) marks revenue (0) vs expense (1). `type_id` → FK ERPNext core `Item`. Indonesian logistics fields: `jalur` (lane), `csize` (container size), `jenis_karantina` (quarantine type), `sandaran_id` (berth). `per_doc`/`by_qty` are pricing-basis flags.

---

# 14. CRM Quotation Product (child of CRM Quotation)

| Property | Value |
|---|---|
| name | `CRM Quotation Product` |
| module | FCRM | istable | **1** | editable_grid | 1 | track_changes | 1 |
| parent | CRM Quotation (`products`) |

### Fields

| fieldname | fieldtype | label | options | reqd | read_only | default | in_list_view |
|---|---|---|---|---|---|---|---|
| product | Link | Product | **Item** (core), link_filters `{"item_category":"Revenue"}` | **1** | | | 1 |
| remark | Data | Remark | | | | | 1 |
| **column_break_1** | Column Break | | | | | | |
| qty | Float | Qty | | | | 1 | 1 |
| price | Currency | Price | | | | | 1 |
| amount | Currency | Amount | | | 1 | | 1 |

Permissions: `[]`. Controller `crm_quotation_product.py`: **validate()** → `amount = qty * price` (per-row). Parent also recomputes `amount` + `net_total` in its `before_save`.

### Go note
`product` → FK ERPNext core `Item` (filtered to `item_category = Revenue`). On convert-to-estimation each row must reference a valid Item or the conversion throws. `amount` is derived; compute server-side.

---

# 15. CRM Quotation Additional (child table — defined, not wired)

| Property | Value |
|---|---|
| name | `CRM Quotation Additional` |
| module | FCRM | istable | **1** | track_changes | 1 |
| parent | (intended for CRM Quotation, but **not referenced** in Quotation's field_order/fields) |

### Fields

| fieldname | fieldtype | label | options | reqd | in_list_view |
|---|---|---|---|---|---|
| type | Select | Type | `additional1 / additional2` | **1** | 1 |
| title | Data | Title | | | 1 |
| item_name | Data | Item Name | | **1** | 1 |
| price | Currency | Price | | | 1 |

Permissions: `[]`. Controller `crm_quotation_additional.py`: `pass`.

### Go note
A clean child-table model for quotation "additional charges". The current Quotation doctype instead uses flat `additional1_*`/`additional2_*` fields, so this table is **orphaned** in the current schema. For a Go rebuild, prefer this child table over the flat fields and wire it to CRM Quotation.

---

# 16. CRM Deal Transportation Mode (Table MultiSelect junction child of CRM Deal)

| Property | Value |
|---|---|
| name | `CRM Deal Transportation Mode` |
| module | FCRM | istable | **1** | editable_grid | 1 |
| parent | CRM Deal (`transportation_mode`, fieldtype **Table MultiSelect**) |

### Fields

| fieldname | fieldtype | label | options | reqd | in_list_view |
|---|---|---|---|---|---|
| mode | Link | Transportation Mode | **CRM Transportation Mode** | **1** | 1 |

Permissions: `[]`. Controller `crm_deal_transportation_mode.py`: `pass`.

### Go note
Pure junction table: `CRM Deal` ↔ `CRM Transportation Mode` many-to-many. Each row holds just `mode` (FK) + standard child cols. Model as `[]string` (mode names) on CRM Deal, or as a join table `deal_transportation_mode(parent, mode)`.

---

## Cross-cutting patterns for the Go rebuild

1. **Custom numbering (per-year reset counters):** CRM Lead `LD/####/CMI/YY`, CRM Deal `INQ/####/CMI/YY`, CRM Estimation `EST/####/CMI/YY`, CRM Quotation `QT/####/CMI/YYYY`, CRM Product `CRM-PROD-YYYY-`. Counters reset each year. Implement an atomic per-(prefix,year) sequence generator.
2. **Void soft-delete block** (`is_void`, `void_reason`, `void_at`, `void_by`) appears on CRM Lead, CRM Deal, CRM Quotation — a uniform soft-cancel pattern (all read-only, set by a void action, not plain delete).
3. **SLA / response tracking** (`sla`, `sla_status`, `response_by`, `first_response_time`, `first_responded_on`, `last_response_time`, `last_responded_on`, `rolling_responses`, `communication_status`) is shared by CRM Lead and CRM Deal — drive it from a `CRM Service Level Agreement` engine.
4. **Status change log** (`status_change_log` → `CRM Status Change Log` child) records every status transition on Lead & Deal.
5. **Polymorphic references** (`reference_doctype` + `reference_docname` Dynamic Link) on CRM Task, FCRM Note, CRM Call Log — model as a (`ref_type`, `ref_name`) pair, app-enforced FK.
6. **Multi-currency** (`currency` + `exchange_rate`, captured once) on CRM Deal & CRM Organization; system base currency from `FCRM Settings.currency` (default USD). CRM Quotation/Estimation default `IDR`.
7. **Conversion chain:** Lead → Deal (`convert_to_deal`), Deal(Won) → Quotation (manual, 1:1), Quotation → Estimation (`convert_to_estimation`, 1:1, locks quotation to `Converted`). Assignees (ToDo) propagate down the chain.
8. **Currency `options` fields** like `"currency"` or `"IDR"` name the currency field controlling the money column's display currency; store amounts as decimal plus the currency code.
9. **Permissions** are uniform (System Manager / Sales Manager / Sales User, full) for the main doctypes; the only exception is **CRM Transportation Mode** where Sales User is read-only.
```
```
