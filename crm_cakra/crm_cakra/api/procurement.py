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
	jejak = _("mengirim permintaan harga ke procurement ({0})").format(doc.requested_to)
	# Catatan yang diketik pengirim ikut dibawa: tanpa itu baris timeline cuma
	# bilang "sudah dikirim" dan orang harus membuka dokumen procurement untuk
	# tahu apa yang sebenarnya diminta.
	if doc.remark:
		jejak += ' -- "' + doc.remark + '"'
	frappe.get_doc("CRM Inquiry", doc.inquiry).add_comment("Info", jejak)

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
	_email_approval(doc)

	return {"status": doc.status, "approved_on": doc.approved_on, "approved_by": doc.approved_by}


def _email_approval(doc):
	"""Email ke pembuat inquiry: costing-nya sudah final.

	Dia yang menunggu angka ini untuk menyusun penawaran; tanpa email dia harus
	rajin membuka CRM untuk tahu. Terkirim tiap kali status masuk ke Approve --
	costing yang dibuka lalu disetujui ulang ikut memberi kabar lagi.
	"""
	owner = frappe.db.get_value("CRM Inquiry", doc.inquiry, "owner")
	# Inquiry impor lama milik Administrator; emailnya bukan kotak masuk siapa pun.
	if not owner or owner in ("Administrator", "Guest", frappe.session.user):
		return
	email = frappe.db.get_value("User", {"name": owner, "enabled": 1}, "email")
	if not email:
		return

	def uang(v):
		return frappe.format_value(v, {"fieldtype": "Currency"})

	message = (
		"<p>"
		+ get_fullname(frappe.session.user)
		+ " "
		+ _("approved procurement costing on")
		+ " <b>"
		+ doc.inquiry
		+ "</b>.</p><p>"
		+ _("Fixed Cost")
		+ ": "
		+ uang(doc.total_fixed_cost)
		+ "<br>"
		+ _("Variable Cost")
		+ ": "
		+ uang(doc.total_variable_cost)
		+ "</p>"
		+ '<p><a href="'
		+ _procurement_link(doc.name)
		+ '">'
		+ _("Buka di CRM")
		+ "</a></p>"
	)
	_sendmail_now(
		doc, [email], _("Costing Approved") + ": " + doc.inquiry, message, error_title="Approve Cost email gagal"
	)


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

	subject, message = _render_request_email(doc, body, owner_name)
	# fid = nama dokumen File; berkasnya sudah menempel di dokumen ini.
	_sendmail_now(
		doc,
		recipients,
		subject,
		message,
		[{"fid": f} for f in attachments],
		error_title="Submit to Procurement email gagal",
	)


def _sendmail_now(doc, recipients, subject, message, attachments=None, error_title=""):
	"""Antrekan email lalu kirim segera lewat worker."""
	try:
		antrean = frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=message,
			reference_doctype="CRM Procurement",
			reference_name=doc.name,
			attachments=attachments or [],
		)
		# Antrean email hanya dikuras penjadwal, dan pengurasannya sengaja
		# melewati email yang umurnya belum 10 detik (jendela undo milik Frappe).
		# Terukur di site ini: 60 sampai 215 detik sebelum email benar-benar
		# berangkat. Permintaan harga itu menunggu orang, jadi barisnya dikirim
		# langsung lewat worker -- tombol Kirim tetap tidak ikut menunggu SMTP,
		# dan jendela undo tidak berlaku karena barisnya ditunjuk per nama.
		#
		# enqueue_after_commit wajib: tanpa itu worker membuka baris antrean yang
		# belum ter-commit dan tidak menemukan apa-apa.
		baris = antrean if isinstance(antrean, (list, tuple)) else [antrean]
		for b in baris:
			if b:
				frappe.enqueue_doc(
					"Email Queue", b.name, "send", queue="short", enqueue_after_commit=True
				)
	except Exception:
		frappe.log_error(title=error_title, message=frappe.get_traceback())


def _procurement_link(name: str) -> str:
	"""Tautan ke dokumen procurement di CRM.

	Nama dokumen mengandung garis miring (PRC/0002/CMI/26), jadi harus di-encode --
	tanpa itu tautannya terbaca sebagai beberapa segmen path dan mendarat di
	halaman yang salah. Yang menuntut login dan menyaring peran adalah CRM-nya
	sendiri; di sini cuma alamatnya.
	"""
	from urllib.parse import quote

	return frappe.utils.get_url("/crm/procurement/" + quote(name, safe=""))


def _render_request_email(doc, body, owner_name):
	"""(subjek, isi) email permintaan.

	Memakai Email Template yang ditunjuk FCRM Settings > Group Template >
	Procurement kalau ada, supaya isinya bisa diubah orang tanpa menyentuh kode.
	Kalau templatenya dihapus atau kosong, jatuh ke susunan bawaan -- permintaan
	yang sudah tercatat tidak boleh gagal terkirim gara-gara template.
	"""
	inquiry = frappe.db.get_value(
		"CRM Inquiry", doc.inquiry, ["organization", "origin", "destination", "inquiry_date"], as_dict=True
	) or frappe._dict()

	rute = " - ".join(x for x in (inquiry.origin, inquiry.destination) if x)
	konteks = {
		"doc": doc,
		"procurement": doc.name,
		"inquiry": doc.inquiry,
		"account": inquiry.organization,
		"route": rute,
		"inquiry_date": frappe.utils.formatdate(inquiry.inquiry_date) if inquiry.inquiry_date else "",
		"requester": owner_name,
		"remark": body,
		"link": _procurement_link(doc.name),
	}

	nama_template = frappe.db.get_single_value("FCRM Settings", "procurement_email_template")
	if nama_template and frappe.db.exists("Email Template", nama_template):
		template = frappe.get_doc("Email Template", nama_template)
		isi = template.response_html if template.use_html else template.response
		try:
			return (
				frappe.render_template(template.subject or "", konteks),
				frappe.render_template(isi or "", konteks),
			)
		except Exception:
			# Template diketik orang; salah tulis Jinja jangan sampai menelan
			# emailnya. Dicatat, lalu pakai susunan bawaan.
			frappe.log_error(title="Template email procurement gagal dirender", message=frappe.get_traceback())

	pesan = "<p>" + owner_name + " " + _("requested procurement on") + " <b>" + doc.inquiry + "</b>.</p>"
	if body:
		pesan += "<p>" + body + "</p>"
	pesan += '<p><a href="' + konteks["link"] + '">' + _("Buka di CRM") + "</a></p>"
	return _("Request Procurement") + ": " + doc.inquiry, pesan


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

	link = _procurement_link(doc.name)
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
