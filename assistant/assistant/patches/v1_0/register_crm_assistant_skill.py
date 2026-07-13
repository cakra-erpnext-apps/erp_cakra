"""Daftarkan skill CRM Assistant di Assistant Settings, dan buang baris CRM yang salah.

Baris skill hidup di DB (child table `Assistant Settings.skills`), bukan di file, jadi
deploy kode saja tidak membawanya. Tanpa patch ini, agent CRM di server tetap memakai
baris lamanya.

Baris CRM lama menunjuk file skill EXPEDITION:
  Lead      -> bl_to_shipping_list.skill
  Inquiry   -> vendor_invoice_to_expense_note.skill
  Quotation -> (tanpa file)
Akibatnya agent CRM membaca playbook konversi BL dan invoice vendor -- bukan CRM.
Ketiganya diganti satu baris yang menunjuk crm_assistant.skill.

Aman dijalankan berulang: baris CRM lama dibuang lalu baris kanonik ditulis ulang.
"""

import frappe

SKILL_FILE = "crm_assistant.skill"
SKILL_LABEL = "CRM Assistant"

# Modul yang dianggap milik surface CRM. Baris lama dengan modul ini dibuang.
CRM_MODULES = {
	"CRM",
	"CRM Lead",
	"CRM Inquiry",
	"CRM Quotation",
	"CRM Estimation",
	"CRM Dashboard",
	"CRM Contact",
	"CRM Account",
}

RESTRICTIONS = (
	"JANGAN membuat transaksi apa pun (Lead/Inquiry/Quotation/Shipping List/"
	"Packing List/Expense Note/Invoice). JANGAN menyentuh modul di luar CRM. "
	"Ubah status HANYA untuk CRM Inquiry & CRM Quotation, HANYA dokumen milik user "
	"sendiri, dan HANYA setelah user menyetujui."
)

DESCRIPTION = (
	"Baca & analisis data CRM (lintas cabang, termasuk produk & harga). Tidak boleh "
	"membuat transaksi. Ubah status Inquiry/Quotation hanya milik sendiri + persetujuan user."
)


def execute():
	if not frappe.db.exists("DocType", "Assistant Settings"):
		return

	settings = frappe.get_doc("Assistant Settings")
	rows = list(settings.get("skills") or [])

	for row in rows:
		if (row.module or "").strip() in CRM_MODULES:
			settings.remove(row)

	settings.append(
		"skills",
		{
			"enabled": 1,
			"skill_label": SKILL_LABEL,
			"module": "CRM",
			"file": SKILL_FILE,
			"description": DESCRIPTION,
			"restrictions": RESTRICTIONS,
		},
	)
	settings.save(ignore_permissions=True)
