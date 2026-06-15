"""Deterministic tools the expedition agent is allowed to call.

The LLM never writes to the database directly. It can only invoke these
whitelisted functions, which validate input, resolve free text to real Link
records, and create *draft* documents for a human to review.
"""

import difflib

import frappe
from frappe import _

# --- Master resolution -----------------------------------------------------

# Only these doctypes may be resolved by the agent (free text -> Link value).
RESOLVABLE = {
	"Expedition",
	"Vessel",
	"Voyage",
	"Location",
	"Depo",
	"Shipment Type",
	"Container Size",
	"Cargo",
	"Route",
	"Sandaran",
	"Jenis Karantina",
	"Cost Center",
	"CRM Organization",
	"Supplier",
	"Currency",
	# Expense Note / Invoice + the Type masters that drive numbering.
	"Customer",
	"Company",
	"Account",
	"Item",
	"UOM",
	"Packing List Type",
	"Invoice Type",
	"Expense Note Type",
	"Expense Class",
}

# Confidence thresholds.
_ACCEPT = 0.5  # below this we return no "best" match
_AMBIGUOUS_GAP = 0.1  # top two within this gap -> flag as ambiguous


def _title_field(doctype):
	return frappe.get_meta(doctype).get_title_field() or "name"


def _score(q, candidate):
	c = (candidate or "").lower()
	if not c:
		return 0.0
	if q == c:
		return 1.0
	if c.startswith(q) or q.startswith(c):
		return 0.9
	if q in c or c in q:
		return 0.75
	return difflib.SequenceMatcher(None, q, c).ratio()


@frappe.whitelist()
def resolve_master(doctype, query, limit=5):
	"""Resolve free text to a Link record. Returns the best match + candidates.

	Use this before putting any value into a Link field. If ``best`` is null or
	``ambiguous`` is true, ask the user instead of guessing.
	"""
	doctype = (doctype or "").strip()
	query = (query or "").strip()
	limit = int(limit or 5)

	# Batasan allowlist RESOLVABLE dihapus — agent boleh resolve master doctype apa pun
	# yang ada (cukup pastikan doctype-nya valid agar get_meta tidak error).
	if not frappe.db.exists("DocType", doctype):
		frappe.throw(_("Doctype '{0}' tidak ditemukan.").format(doctype))
	if not query:
		return {"query": query, "best": None, "candidates": [], "ambiguous": False}

	title_field = _title_field(doctype)
	meta = frappe.get_meta(doctype)

	filters = {}
	if meta.has_field("disabled"):
		filters["disabled"] = 0

	fields = ["name"]
	if title_field != "name":
		fields.append(title_field)

	rows = frappe.get_all(doctype, filters=filters, fields=fields, limit_page_length=0)

	q = query.lower()
	scored = []
	for r in rows:
		name = r["name"]
		title = r.get(title_field) or ""
		s = max(_score(q, str(name)), _score(q, str(title)))
		scored.append({"value": name, "label": title or name, "score": round(s, 3)})

	scored.sort(key=lambda x: x["score"], reverse=True)
	top = scored[:limit]
	best = top[0] if top and top[0]["score"] >= _ACCEPT else None
	ambiguous = bool(
		len(top) >= 2
		and top[0]["score"] - top[1]["score"] < _AMBIGUOUS_GAP
		and top[0]["score"] < 0.95
	)
	return {"query": query, "best": best, "candidates": top, "ambiguous": ambiguous}


# --- Field catalog ---------------------------------------------------------

_LAYOUT = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading"}

PL_DOCTYPE = "Packing List"
PL_ITEM_DOCTYPE = "Packing List Item"
SL_DOCTYPE = "Shipping List"
SL_BL_DOCTYPE = "Shipping List BL"
SL_CONTAINER_DOCTYPE = "Shipping List Container"
EXP_DOCTYPE = "Expense Note"
EXP_ITEM_DOCTYPE = "Expense Note Item"
INV_DOCTYPE = "Sales Invoice"

# Sales Invoice has ~150 fields; expose only the ones the agent should set.
INV_HEADER_FIELDS = {
	"customer": "Link:Customer*",
	"custom_type": "Link:Invoice Type (drives the number)",
	"company": "Link:Company",
	"posting_date": "Date",
	"due_date": "Date",
	"currency": "Link:Currency",
	"po_no": "Data",
	"remarks": "Small Text",
}


def _settable_fields(doctype, include_readonly=False):
	"""Map of fieldname -> meta for fields the agent is allowed to set.

	Child-table rows (BL/Container/Item) are read_only in the UI on purpose (edited
	via modal), but the agent must still populate them programmatically, so callers
	pass include_readonly=True for those.
	"""
	out = {}
	for df in frappe.get_meta(doctype).fields:
		if df.fieldtype in _LAYOUT or df.fieldtype == "Table" or df.hidden:
			continue
		if df.read_only and not include_readonly:
			continue
		out[df.fieldname] = {
			"label": df.label,
			"type": df.fieldtype,
			"options": df.options,
			"reqd": bool(df.reqd),
		}
	return out


def _compact_fields(doctype, include_readonly=False):
	"""Compact `fieldname -> "Type[:LinkTarget][*]"` map (token-efficient).

	`*` marks required. `Link:X` means resolve via resolve_master against X.
	"""
	out = {}
	for fn, meta in _settable_fields(doctype, include_readonly).items():
		t = meta.get("type")
		if t == "Link" and meta.get("options"):
			s = f"Link:{meta['options']}"
		else:
			s = t
		if meta.get("reqd"):
			s += "*"
		out[fn] = s
	return out


def _missing_mandatory(doc):
	"""Daftar field WAJIB (reqd) yang masih kosong di draft — header + per baris child.

	Agent membaca ini setelah membuat draft, lalu memberitahu user apa yang harus
	dilengkapi sebelum Save/Confirm (saat itulah penomoran diberikan). Field reqd
	tetap ditegakkan saat user menyimpan; draft sengaja dibuat dengan ignore_mandatory.
	"""
	missing = []
	for df in doc.meta.fields:
		if df.fieldtype in _LAYOUT or df.fieldtype == "Table":
			continue
		if df.reqd and not doc.get(df.fieldname):
			missing.append(df.label or df.fieldname)
	for df in doc.meta.fields:
		if df.fieldtype != "Table":
			continue
		rows = doc.get(df.fieldname) or []
		if not rows:
			continue
		cmeta = frappe.get_meta(df.options)
		for c in cmeta.fields:
			if c.fieldtype in _LAYOUT or c.fieldtype == "Table" or not c.reqd:
				continue
			if any(not r.get(c.fieldname) for r in rows):
				missing.append(f"{df.label}: {c.label or c.fieldname}")
	return missing


@frappe.whitelist()
def get_field_catalog():
	"""Compact, ground-truth list of fields the agent may set on a Packing List
	or Shipping List draft (and their line tables).

	Call this first so you never invent a fieldname. Format per field:
	"Type" or "Link:Doctype" (feed Doctype into resolve_master); "*" = required.
	"""
	return {
		"packing_list": _compact_fields(PL_DOCTYPE),
		"packing_list_item": _compact_fields(PL_ITEM_DOCTYPE, include_readonly=True),
		"shipping_list": _compact_fields(SL_DOCTYPE),
		"shipping_list_bl": _compact_fields(SL_BL_DOCTYPE, include_readonly=True),
		"shipping_list_container": _compact_fields(SL_CONTAINER_DOCTYPE, include_readonly=True),
		"expense_note": _compact_fields(EXP_DOCTYPE),
		"expense_note_item": _compact_fields(EXP_ITEM_DOCTYPE, include_readonly=True),
		# Sales Invoice: curated header fields only + how items are built.
		"sales_invoice": INV_HEADER_FIELDS,
		"sales_invoice_items_note": (
			"Don't hand-build invoice items. Pass source_doctype+source_name "
			"(Shipping List/Packing List) to create_invoice_draft and it makes one "
			"row per container. Optional item_code bills them as that Item."
		),
	}


# --- Duplicate guard -------------------------------------------------------


@frappe.whitelist()
def check_duplicate(packing_list_no=None, external_ref=None, shipping_list_no=None):
	"""Check whether a Packing List / Shipping List already exists before creating one."""
	hits = []
	if packing_list_no and frappe.db.exists(PL_DOCTYPE, {"packing_list_no": packing_list_no}):
		hits.append({"field": "packing_list_no", "value": packing_list_no, "name": packing_list_no})
	if shipping_list_no and frappe.db.exists(SL_DOCTYPE, {"shipping_list_no": shipping_list_no}):
		hits.append({"field": "shipping_list_no", "value": shipping_list_no, "name": shipping_list_no})
	if external_ref:
		for dt in (PL_DOCTYPE, SL_DOCTYPE):
			for n in frappe.get_all(dt, filters={"external_ref": external_ref}, pluck="name"):
				hits.append({"field": "external_ref", "value": external_ref, "name": n, "doctype": dt})
	return {"duplicate": bool(hits), "matches": hits}


# --- Draft creation --------------------------------------------------------


def _draft_pl_no():
	base = "PLD-" + frappe.utils.now_datetime().strftime("%Y%m%d-%H%M%S")
	no, i = base, 1
	while frappe.db.exists(PL_DOCTYPE, {"packing_list_no": no}):
		no = f"{base}-{i}"
		i += 1
	return no


@frappe.whitelist()
def create_packing_list_draft(fields):
	"""Create a *draft* Packing List from already-resolved field values.

	``fields`` is a dict of Packing List fieldnames -> values; Link fields must
	already hold resolved record names (use resolve_master first). An optional
	``items`` key may carry a list of Packing List Item rows. Returns the new
	document name + which fields were applied/skipped. The document is saved in
	draft for a human to review — it is never submitted.
	"""
	if isinstance(fields, str):
		fields = frappe.parse_json(fields)
	fields = dict(fields or {})
	items = fields.pop("items", None)

	allowed = _settable_fields(PL_DOCTYPE)
	doc = frappe.new_doc(PL_DOCTYPE)

	set_fields, skipped = [], []
	for k, v in fields.items():
		if k in allowed and v not in (None, ""):
			doc.set(k, v)
			set_fields.append(k)
		else:
			skipped.append(k)

	# packing_list_no is auto-generated by the doctype autoname (read-only field).
	auto_no = True

	if items:
		if isinstance(items, str):
			items = frappe.parse_json(items)
		item_allowed = _settable_fields(PL_ITEM_DOCTYPE)
		for raw in items:
			row = {k: v for k, v in dict(raw).items() if k in item_allowed and v not in (None, "")}
			if row:
				doc.append("items", row)

	if not set_fields and not (doc.items or []):
		frappe.throw(
			_(
				"create_packing_list_draft dipanggil tanpa data (tidak ada field header "
				"maupun item). Susun 'fields' lengkap dulu lalu panggil lagi. JANGAN buat draft kosong."
			)
		)

	# Draft agent: tunda penomoran + draft boleh belum lengkap (field wajib dipaksa
	# saat USER Save/Confirm). missing_mandatory dilaporkan agar agent memberitahu user.
	doc.flags.agent_draft = True
	doc.insert(ignore_permissions=False, ignore_mandatory=True)

	return {
		"name": doc.name,
		"packing_list_no": doc.packing_list_no,
		"auto_generated_no": auto_no,
		"url": f"/app/packing-list/{doc.name}",
		"fields_set": set_fields,
		"skipped": skipped,
		"item_count": len(doc.items or []),
		"missing_mandatory": _missing_mandatory(doc),
	}


def _draft_sl_no():
	base = "SLD-" + frappe.utils.now_datetime().strftime("%Y%m%d-%H%M%S")
	no, i = base, 1
	while frappe.db.exists(SL_DOCTYPE, {"shipping_list_no": no}):
		no = f"{base}-{i}"
		i += 1
	return no


def _append_rows(doc, table, rows, doctype):
	if isinstance(rows, str):
		rows = frappe.parse_json(rows)
	allowed = _settable_fields(doctype, include_readonly=True)
	for raw in rows or []:
		row = {k: v for k, v in dict(raw).items() if k in allowed and v not in (None, "")}
		if row:
			doc.append(table, row)


@frappe.whitelist()
def create_shipping_list_draft(fields):
	"""Create a *draft* Shipping List from already-resolved field values.

	Use this (not create_packing_list_draft) when the shipment has several BLs,
	each holding multiple containers. ``fields`` is the header; optional ``bls``
	is a list of BL rows (each with ``bl_no``); optional ``containers`` is a list
	of container rows, each with a ``bl`` field naming the BL it belongs to
	(1 BL → many containers). Saved in draft for human review.
	"""
	if isinstance(fields, str):
		fields = frappe.parse_json(fields)
	fields = dict(fields or {})
	bls = fields.pop("bls", None)
	containers = fields.pop("containers", None)

	allowed = _settable_fields(SL_DOCTYPE)
	doc = frappe.new_doc(SL_DOCTYPE)

	set_fields, skipped = [], []
	for k, v in fields.items():
		if k in allowed and v not in (None, ""):
			doc.set(k, v)
			set_fields.append(k)
		else:
			skipped.append(k)

	# shipping_list_no is auto-generated by the doctype autoname (read-only field).
	auto_no = True

	if bls:
		_append_rows(doc, "bls", bls, SL_BL_DOCTYPE)
	if containers:
		_append_rows(doc, "containers", containers, SL_CONTAINER_DOCTYPE)

	if not set_fields and not (doc.bls or []) and not (doc.containers or []):
		frappe.throw(
			_(
				"create_shipping_list_draft dipanggil tanpa data (tidak ada field header, "
				"BL, maupun container). Susun 'fields' lengkap dulu — header + 'bls' + "
				"'containers' dari dokumen — lalu panggil lagi. JANGAN buat draft kosong."
			)
		)

	# Draft agent: tunda penomoran (nama sementara DRAFT-...; nomor asli saat user Save/Confirm).
	# ignore_mandatory: draft boleh belum lengkap; field wajib (type/date/cost_center/vessel/
	# origin/destination + consignee/size/customer per baris) dipaksa saat USER Save/Confirm.
	doc.flags.agent_draft = True
	doc.insert(ignore_permissions=False, ignore_mandatory=True)

	return {
		"name": doc.name,
		"shipping_list_no": doc.shipping_list_no,
		"auto_generated_no": auto_no,
		"url": f"/app/shipping-list/{doc.name}",
		"fields_set": set_fields,
		"skipped": skipped,
		"bl_count": len(doc.bls or []),
		"container_count": len(doc.containers or []),
		"missing_mandatory": _missing_mandatory(doc),
	}


@frappe.whitelist()
def create_expense_note_draft(fields):
	"""Create a *draft* Expense Note (a cost you PAY a vendor).

	``fields`` = header values (Link fields already resolved). Requires `vendor`
	(Supplier), `company`, and an `items` list — each item row needs
	`expense_account` (Account) + `description` + `price`. Optionally link
	`packing_list` / `shipping_list` (+ `container_no`) and set `expense_note_type`
	(resolve "Expense Note Type"). Saved as a draft (status Draft) for review.
	"""
	if isinstance(fields, str):
		fields = frappe.parse_json(fields)
	fields = dict(fields or {})
	items = fields.pop("items", None)

	allowed = _settable_fields(EXP_DOCTYPE)
	doc = frappe.new_doc(EXP_DOCTYPE)
	set_fields, skipped = [], []
	for k, v in fields.items():
		if k in allowed and v not in (None, ""):
			doc.set(k, v)
			set_fields.append(k)
		else:
			skipped.append(k)

	if items:
		_append_rows(doc, "items", items, EXP_ITEM_DOCTYPE)

	if not set_fields and not (doc.items or []):
		frappe.throw(
			_(
				"create_expense_note_draft dipanggil tanpa data (tidak ada field header "
				"maupun item). Beri minimal 'vendor', 'company', dan 'items', lalu panggil lagi."
			)
		)

	# Draft agent: tunda penomoran + draft boleh belum lengkap (wajib dipaksa saat user Save/Confirm).
	doc.flags.agent_draft = True
	doc.insert(ignore_permissions=False, ignore_mandatory=True)
	return {
		"name": doc.name,
		"url": f"/app/expense-note/{doc.name}",
		"fields_set": set_fields,
		"skipped": skipped,
		"item_count": len(doc.items or []),
		"missing_mandatory": _missing_mandatory(doc),
	}


@frappe.whitelist()
def create_invoice_draft(fields):
	"""Create a *draft* Sales Invoice (what you BILL a customer).

	``fields`` keys:
	- header (curated): `customer` (resolved Customer, required), `custom_type`
	  (Invoice Type — drives the number), `company`, `posting_date`, `due_date`,
	  `currency`, `po_no`, `remarks`.
	- `source_doctype` + `source_name`: a Shipping List / Packing List to pull one
	  invoice row per container from.
	- `item_code` (optional): bill all pulled rows as this Item (Sales Invoice rows
	  normally need an Item — resolve "Item" and pass it here).
	- `shipping_lists` (optional list): Shipping List names to link under the
	  invoice's Shipping List tab.
	- `items` (optional): explicit rows if no source is given.
	Saved as a draft (docstatus 0) for review — never submitted.
	"""
	if isinstance(fields, str):
		fields = frappe.parse_json(fields)
	fields = dict(fields or {})
	source_doctype = fields.pop("source_doctype", None)
	source_name = fields.pop("source_name", None)
	item_code = fields.pop("item_code", None)
	shipping_lists = fields.pop("shipping_lists", None)
	items = fields.pop("items", None)

	doc = frappe.new_doc(INV_DOCTYPE)
	set_fields, skipped = [], []
	for k, v in fields.items():
		if k in INV_HEADER_FIELDS and v not in (None, ""):
			doc.set(k, v)
			set_fields.append(k)
		else:
			skipped.append(k)

	# Item rows: from a source document (1 per container) or explicit rows.
	rows = []
	if source_doctype and source_name:
		from erp_cmi.expedition.get_items import get_container_invoice_items

		rows = get_container_invoice_items(source_doctype, source_name, item_code)
	elif items:
		if isinstance(items, str):
			items = frappe.parse_json(items)
		rows = items
	for r in rows or []:
		doc.append("items", r)

	if not set_fields and not (doc.items or []):
		frappe.throw(
			_(
				"create_invoice_draft dipanggil tanpa data (tidak ada header maupun item). "
				"Beri minimal 'customer' + sumber (source_doctype/source_name) atau 'items', "
				"lalu panggil lagi."
			)
		)

	# Link Shipping Lists under the custom Shipping List tab, if the field exists.
	linked = 0
	if shipping_lists:
		if isinstance(shipping_lists, str):
			shipping_lists = frappe.parse_json(shipping_lists)
		if doc.meta.get_field("custom_shipping_lists"):
			for sl in shipping_lists:
				if sl:
					doc.append("custom_shipping_lists", {"shipping_list": sl})
					linked += 1

	# Draft agent: tunda penomoran + draft boleh belum lengkap (wajib dipaksa saat user Save/Confirm).
	doc.flags.agent_draft = True
	doc.insert(ignore_permissions=False, ignore_mandatory=True)
	return {
		"name": doc.name,
		"url": f"/app/sales-invoice/{doc.name}",
		"fields_set": set_fields,
		"skipped": skipped,
		"item_count": len(doc.items or []),
		"shipping_lists_linked": linked,
		"missing_mandatory": _missing_mandatory(doc),
	}
