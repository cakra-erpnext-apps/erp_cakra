import frappe
from frappe import _
from frappe.utils import cint, flt, get_fullname

from crm_cakra.fcrm.doctype.crm_cost_component.crm_cost_component import (
	VARIABLE,
	resolve_for_product,
)
from crm_cakra.fcrm.doctype.crm_notification.crm_notification import notify_user
from crm_cakra.fcrm.doctype.crm_procurement.crm_procurement import for_inquiry
from crm_cakra.utils import sales_user_only


@frappe.whitelist()
@sales_user_only
def add_inquiry(inquiry: str):
	"""Tombol "Add Inquiry": buka dokumen procurement milik sebuah inquiry.

	Idempoten -- satu inquiry cuma boleh punya satu dokumen (field inquiry unique),
	jadi kalau sudah ada yang menambahkan duluan yang dikembalikan dokumen itu juga,
	bukan error. Tanpa ini dua orang yang menambahkan inquiry yang sama akan saling
	melempar DuplicateEntryError.
	"""
	if not frappe.has_permission("CRM Inquiry", "read", inquiry):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	existing = for_inquiry(inquiry)
	if existing:
		return existing

	doc = frappe.get_doc({"doctype": "CRM Procurement", "inquiry": inquiry}).insert()
	return doc.name


@frappe.whitelist()
@sales_user_only
def submit_to_procurement(
	procurement: str,
	recipients: str | list,
	remark: str | None = None,
	attachments: str | list | None = None,
):
	"""Kirim permintaan harga ke tim procurement.

	Satu aksi, beberapa akibat yang memang harus jalan bersama: dokumennya
	di-assign ke orang yang dituju (muncul di daftar tugas mereka), notifikasi
	in-app, dan email berisi tautan langsung -- notifikasi in-app hanya terlihat
	kalau CRM sedang dibuka.

	Lampiran sudah lebih dulu diunggah dan menempel di dokumen ini; yang dikirim
	ke sini cuma nama File-nya, supaya berkasnya tetap tersimpan di dokumen dan
	bukan cuma lewat sekali di email.
	"""
	doc = frappe.get_doc("CRM Procurement", procurement)
	doc.check_permission("write")

	recipients = frappe.parse_json(recipients) if isinstance(recipients, str) else recipients
	recipients = [u for u in dict.fromkeys(recipients or []) if u]
	if not recipients:
		frappe.throw(_("Pilih minimal satu orang untuk dikirimi permintaan."))

	attachments = frappe.parse_json(attachments) if isinstance(attachments, str) else attachments
	attachments = [a for a in (attachments or []) if a]

	# Catatan diketik di textarea polos, sedangkan email dan kartu Teams mengirim
	# HTML. Di-escape supaya tanda < atau & pada catatan tidak merusak tampilannya,
	# lalu baris barunya dipertahankan.
	body = frappe.utils.escape_html((remark or "").strip()).replace(chr(10), "<br>")
	owner_name = get_fullname(frappe.session.user)

	from frappe.desk.form.assign_to import add as assign_to_add

	assign_to_add(
		{
			"assign_to": recipients,
			"doctype": "CRM Procurement",
			"name": doc.name,
			"description": _("Request harga untuk {0}").format(doc.inquiry),
		},
		ignore_permissions=True,
	)

	text = (
		'<div class="mb-2 leading-5 text-ink-gray-5">'
		'<span class="font-medium text-ink-gray-9">' + owner_name + "</span>"
		"<span> " + _("requested procurement on") + " </span>"
		'<span class="font-medium text-ink-gray-9">' + doc.inquiry + "</span>"
		"</div>"
	)
	for user in recipients:
		if user == frappe.session.user:
			continue
		notify_user(
			{
				"owner": frappe.session.user,
				"assigned_to": user,
				"notification_type": "Mention",
				"message": body,
				"notification_text": text,
				"reference_doctype": "CRM Procurement",
				"reference_docname": doc.name,
				"redirect_to_doctype": "CRM Procurement",
				"redirect_to_docname": doc.name,
			}
		)

	_email_request(doc, recipients, body, owner_name, attachments)
	_teams_request(doc, recipients, body, owner_name)

	doc.db_set(
		{
			"status": "Request",
			"submitted_on": frappe.utils.now(),
			"submitted_by": frappe.session.user,
			"requested_to": ", ".join(get_fullname(u) for u in recipients),
			"remark": (remark or "").strip(),
		}
	)

	# db_set melewati on_update, jadi status yang baru harus dicerminkan sendiri --
	# kalau tidak, kolom Procurement Status di Inquiry tertinggal di nilai lama.
	doc.mirror_totals_to_inquiry()
	set_inquiry_status(doc.inquiry, "Submit")

	# Jejak di timeline Inquiry. Permintaan ini tidak mengubah satu field pun di
	# inquiry, jadi tanpa catatan ini ia tidak pernah muncul di tab Activity --
	# padahal justru di sanalah orang mencari "kapan ini dikirim dan ke siapa".
	# Komentar jenis Info, bukan Comment: ini peristiwa, bukan percakapan.
	frappe.get_doc("CRM Inquiry", doc.inquiry).add_comment(
		"Info",
		_("mengirim permintaan harga ke procurement ({0})").format(doc.requested_to),
	)

	return {
		"status": doc.status,
		"submitted_on": doc.submitted_on,
		"requested_to": doc.requested_to,
		"remark": doc.remark,
	}


@frappe.whitelist()
@sales_user_only
def approve_cost(procurement: str):
	"""Tandai costing sudah disetujui: status Approve + jejak siapa dan kapan.

	Dipisah dari submit_to_procurement karena arahnya berlawanan -- submit itu
	Marketing meminta, ini Procurement menyatakan angkanya final. Disimpan lewat
	db_set supaya persetujuan tidak ikut terhalang validasi field lain.
	"""
	doc = frappe.get_doc("CRM Procurement", procurement)
	doc.check_permission("write")

	if doc.status == "Approve":
		return {"status": doc.status, "approved_on": doc.approved_on, "approved_by": doc.approved_by}

	if not (doc.fixed_cost_items or doc.variable_cost_items):
		frappe.throw(_("Belum ada baris biaya yang bisa disetujui."))

	doc.db_set(
		{
			"status": "Approve",
			"approved_on": frappe.utils.now(),
			"approved_by": frappe.session.user,
		}
	)
	doc.mirror_totals_to_inquiry()
	set_inquiry_status(doc.inquiry, "Approved")

	frappe.get_doc("CRM Inquiry", doc.inquiry).add_comment(
		"Info", _("menyetujui costing procurement ({0})").format(doc.name)
	)

	return {"status": doc.status, "approved_on": doc.approved_on, "approved_by": doc.approved_by}


def set_inquiry_status(inquiry: str, status: str) -> None:
	"""Naikkan status inquiry mengikuti alur procurement.

	Ditulis pakai db_set, bukan save(): inquiry yang sudah terkunci (Submit /
	Approved) menolak perubahan lewat validate, dan inquiry impor lama sering
	gagal field wajib -- dua-duanya bukan alasan untuk menggagalkan permintaan
	harga yang sudah tercatat.

	Status akhir tidak ditarik mundur: yang sudah Won atau Lost tetap begitu.
	"""
	if not inquiry or not frappe.db.exists("CRM Inquiry Status", status):
		return

	sekarang = frappe.db.get_value("CRM Inquiry", inquiry, "status")
	if sekarang and frappe.db.get_value("CRM Inquiry Status", sekarang, "type") in ("Won", "Lost"):
		return
	if sekarang == status:
		return

	frappe.db.set_value("CRM Inquiry", inquiry, "status", status)


def _email_request(doc, recipients, body, owner_name, attachments):
	"""Email permintaan berikut lampirannya.

	Gagal kirim tidak boleh membatalkan permintaan yang sudah tercatat -- assign
	dan notifikasi in-app-nya sudah jalan.
	"""
	recipients = [u for u in recipients if u != frappe.session.user]
	if not recipients:
		return

	link = frappe.utils.get_url("/crm/procurement/" + doc.name)
	message = "<p>" + owner_name + " " + _("requested procurement on") + " <b>" + doc.inquiry + "</b>.</p>"
	if body:
		message += "<p>" + body + "</p>"
	message += '<p><a href="' + link + '">' + _("Buka di CRM") + "</a></p>"

	try:
		frappe.sendmail(
			recipients=recipients,
			subject=_("Request Procurement") + ": " + doc.inquiry,
			message=message,
			reference_doctype="CRM Procurement",
			reference_name=doc.name,
			# fid = nama dokumen File; berkasnya sudah menempel di dokumen ini.
			attachments=[{"fid": f} for f in attachments],
		)
	except Exception:
		frappe.log_error(title="Submit to Procurement email gagal", message=frappe.get_traceback())


def _teams_request(doc, recipients, body, owner_name):
	"""Kartu permintaan ke channel Teams, kalau webhook-nya diisi.

	Webhook Teams itu per-channel, bukan per-orang: kartunya menyebut siapa yang
	diminta supaya tetap jelas permintaan ini milik siapa. Dikerjakan worker --
	Teams di luar kendali kita dan tombol Kirim tidak boleh ikut menunggu kalau
	jaringannya lambat.
	"""
	url = frappe.db.get_single_value("FCRM Settings", "teams_webhook_url")
	if not url:
		return

	link = frappe.utils.get_url("/crm/procurement/" + doc.name)
	names = ", ".join(get_fullname(u) for u in recipients)
	lines = [
		owner_name + " " + _("requested procurement on") + " " + doc.inquiry,
		_("Assign To") + ": " + names,
	]
	if body:
		lines.append(frappe.utils.strip_html(body.replace("<br>", chr(10))))

	card = {
		"type": "message",
		"attachments": [
			{
				"contentType": "application/vnd.microsoft.card.adaptive",
				"content": {
					"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
					"type": "AdaptiveCard",
					"version": "1.4",
					"body": [
						{
							"type": "TextBlock",
							"text": _("Request Procurement"),
							"weight": "Bolder",
							"size": "Medium",
						},
						{"type": "TextBlock", "text": chr(10).join(lines), "wrap": True},
					],
					"actions": [{"type": "Action.OpenUrl", "title": _("Buka di CRM"), "url": link}],
				},
			}
		],
	}
	frappe.enqueue(_post_teams, queue="short", url=url, card=card)


def _post_teams(url, card):
	import requests

	try:
		requests.post(url, json=card, timeout=15).raise_for_status()
	except Exception:
		frappe.log_error(title="Submit to Procurement Teams gagal", message=frappe.get_traceback())


@frappe.whitelist()
@sales_user_only
def preview_base_prices(rows: str | list):
	"""Base Price tiap baris untuk quotation yang belum tersimpan.

	Halaman New tidak punya panel costing, jadi kolom Base Price-nya diam di 0
	sampai simpan pertama -- padahal angka itulah lantai harganya. Di sini
	dihitung lebih awal, dengan rumus yang sama persis dengan calculate_costing().

	Ini pratinjau. Yang mengikat tetap hitungan server saat dokumennya disimpan.
	"""
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	out = []
	for row in rows or []:
		code = (row or {}).get("product_code")
		if not code or not frappe.db.exists("CRM Product", code):
			out.append(0.0)
			continue

		per_day = flt(frappe.db.get_value("CRM Product", code, "fixed_cost_per_day"))
		# Produk tanpa komponen variable tetap punya Base Price dari fixed cost-nya.
		variable_per_day = sum(
			flt(i.qty) * flt(i.rate)
			for comp in resolve_for_product(code, VARIABLE)
			for i in comp.items
		)

		dur = cint(row.get("duration")) or 1
		base_per_day = per_day + variable_per_day
		margin = base_per_day * flt(row.get("margin_percent")) / 100
		out.append((base_per_day + margin) * dur)
	return out
