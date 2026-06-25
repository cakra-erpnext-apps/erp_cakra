import frappe
from frappe.model.document import Document

from erp.expedition import numbering


def _company_currency():
	company = frappe.defaults.get_global_default("company")
	if company:
		cur = frappe.get_cached_value("Company", company, "default_currency")
		if cur:
			return cur
	return frappe.db.get_default("currency") or "IDR"


@frappe.whitelist()
def summary_data(shipping_list):
	"""View-only ringkasan finansial sebuah Shipping List untuk tab Summary.

	- Expense  : Expense Note (void != 1) yang terhubung, beserta baris expense class.
	- Revenue  : Sales Invoice (non-cancelled) yang menarik container dari Shipping List
	             ini (lewat child 'Invoice Container'), beserta baris item.
	- Margin   : Revenue(DPP) - Expense(DPP), semua dalam mata uang perusahaan (base).

	erp tetap steril: Sales Invoice / Invoice Container dibaca lewat nama (string) saja.
	"""
	currency = _company_currency()
	out = {"currency": currency, "expenses": [], "revenues": [], "totals": {}}
	if not shipping_list:
		return out

	# ---- EXPENSE — 1 baris per Expense Class; pajak diprorata per note (by amount share) ----
	class_amt, class_tax, class_notes = {}, {}, {}
	ens = frappe.get_all(
		"Expense Note",
		filters={"shipping_list": shipping_list, "void": ["!=", 1], "is_reimburse": ["!=", 1]},
		fields=["name", "conversion_rate", "total_amount", "tax_amount"],
		order_by="date asc, name asc",
	)
	for e in ens:
		rate = e.conversion_rate or 1
		note_total = e.total_amount or 0
		tax_rate = (e.tax_amount or 0) / note_total if note_total else 0
		lines = frappe.get_all(
			"Expense Note Item",
			filters={"parent": e.name, "parenttype": "Expense Note"},
			fields=["expense_class", "description", "amount"],
			order_by="idx",
		)
		for l in lines:
			cls = l.expense_class or l.description or "-"
			amt = (l.amount or 0) * rate
			class_amt[cls] = class_amt.get(cls, 0) + amt
			class_tax[cls] = class_tax.get(cls, 0) + amt * tax_rate
			class_notes.setdefault(cls, set()).add(e.name)
	for cls in sorted(class_amt, key=lambda k: -class_amt[k]):
		a, tx = class_amt[cls], class_tax[cls]
		out["expenses"].append({
			"expense_class": cls,
			"expense_no": ", ".join(sorted(class_notes[cls])),
			"amount": a, "tax": tx, "net": a + tx,
		})
	total_expense = sum(class_amt.values())
	total_expense_tax = sum(class_tax.values())

	# ---- REVENUE — 1 baris per item invoice; pajak diprorata per invoice (by amount share) ----
	total_revenue = 0.0
	total_revenue_tax = 0.0
	ic = frappe.get_all(
		"Invoice Container",
		filters={"source_name": shipping_list, "source_doctype": "Shipping List", "parenttype": "Sales Invoice"},
		fields=["parent"],
	)
	inv_names = list({r.parent for r in ic if r.parent})
	if inv_names:
		invs = frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", inv_names], "docstatus": 1},  # hanya Submitted
			fields=["name", "base_total", "base_total_taxes_and_charges"],
			order_by="posting_date asc, name asc",
		)
		for iv in invs:
			base_total = iv.base_total or 0
			tax_rate = (iv.base_total_taxes_and_charges or 0) / base_total if base_total else 0
			lines = frappe.get_all(
				"Sales Invoice Item",
				filters={"parent": iv.name, "parenttype": "Sales Invoice"},
				fields=["item_name", "description", "base_amount"],
				order_by="idx",
			)
			for l in lines:
				a = l.base_amount or 0
				tx = a * tax_rate
				total_revenue += a
				total_revenue_tax += tx
				out["revenues"].append({
					"item": l.item_name or l.description or "-",
					"invoice": iv.name,
					"amount": a, "tax": tx, "net": a + tx,
				})

	margin = total_revenue - total_expense
	out["totals"] = {
		"revenue": total_revenue,
		"revenue_tax": total_revenue_tax,
		"revenue_net": total_revenue + total_revenue_tax,
		"expense": total_expense,
		"expense_tax": total_expense_tax,
		"expense_net": total_expense + total_expense_tax,
		"margin": margin,
		"margin_pct": round(margin / total_revenue * 100, 1) if total_revenue else None,
	}
	out["reimbursements"] = _reimbursements(shipping_list)
	return out


class ShippingList(Document):
	def autoname(self):
		# Draft buatan agent: nama sementara, nomor seri belum dipakai (lihat
		# numbering.assign_number — nomor asli diberikan saat user Save/Confirm).
		if self.flags.get("agent_draft"):
			self.name = numbering.draft_name()
			return
		# SH/{type}/{number}/{company}/{year}
		self.shipping_list_no = self.make_real_number()
		self.name = self.shipping_list_no

	def make_real_number(self):
		return numbering.make_number("SH", self.type, "Packing List Type", date=self.date)

	def validate(self):
		# Denormalised counts.
		self.bl_count = len(self.bls or [])
		self.container_count = len(self.containers or [])

		# Per-BL container counts (group containers by their BL no).
		counts = {}
		for c in self.containers or []:
			if c.bl:
				counts[c.bl] = counts.get(c.bl, 0) + 1
		for b in self.bls or []:
			b.no_containers = counts.get(b.bl_no, 0)

		# Warn about containers pointing at a BL that isn't in the BLs table.
		bl_nos = {b.bl_no for b in self.bls or [] if b.bl_no}
		orphans = sorted({c.bl for c in self.containers or [] if c.bl and c.bl not in bl_nos})
		if orphans:
			frappe.msgprint(
				frappe._("Containers reference BL(s) not in the BLs table: {0}").format(", ".join(orphans)),
				indicator="orange",
				alert=True,
			)


def _reimbursements(shipping_list):
    """Reimbursement (pass-through — TIDAK masuk Expense/Revenue/Margin) untuk tab Summary.

    - Expense Note ber-flag reimburse (is_reimburse=1) di Shipping List ini = biaya yang
      akan ditagih balik ke customer (Paid).
    - Sales Invoice tipe 'Reimburse' yang menagih EN-EN itu lewat Reimburse Item = Billed.
    """
    out = {"expenses": [], "invoices": [], "paid": 0.0, "billed": 0.0, "net": 0.0}
    if not shipping_list:
        return out
    paid = 0.0
    ens = frappe.get_all(
        "Expense Note",
        filters={"shipping_list": shipping_list, "void": ["!=", 1], "is_reimburse": 1},
        fields=["name", "vendor", "date", "net_total", "conversion_rate", "reimburse_to_customer"],
        order_by="date asc, name asc",
    )
    for e in ens:
        amt = (e.net_total or 0) * (e.conversion_rate or 1)
        paid += amt
        out["expenses"].append({
            "name": e.name, "vendor": e.vendor, "customer": e.reimburse_to_customer,
            "date": str(e.date or ""), "amount": amt,
        })
    billed = 0.0
    en_names = [e["name"] for e in out["expenses"]]
    if en_names:
        ris = frappe.get_all(
            "Reimburse Item",
            filters={"expense_note": ["in", en_names], "parenttype": "Sales Invoice"},
            fields=["parent", "line_amount"],
        )
        inv_amt = {}
        for r in ris:
            inv_amt[r.parent] = inv_amt.get(r.parent, 0) + (r.line_amount or 0)
        if inv_amt:
            invs = frappe.get_all(
                "Sales Invoice",
                filters={"name": ["in", list(inv_amt)], "docstatus": ["!=", 2], "custom_invoice_type": "Reimburse"},
                fields=["name", "customer", "posting_date", "docstatus"],
                order_by="posting_date asc, name asc",
            )
            for iv in invs:
                amt = inv_amt.get(iv.name, 0)
                billed += amt
                out["invoices"].append({
                    "name": iv.name, "customer": iv.customer,
                    "date": str(iv.posting_date or ""), "amount": amt,
                    "draft": iv.docstatus == 0,
                })
    out["paid"] = paid
    out["billed"] = billed
    out["net"] = billed - paid
    return out
