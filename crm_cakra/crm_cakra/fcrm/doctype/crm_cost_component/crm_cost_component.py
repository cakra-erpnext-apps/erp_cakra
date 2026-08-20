import frappe
from frappe import _
from frappe.model.document import Document

from crm_cakra.fcrm.doctype.crm_cost_item.crm_cost_item import compute_amount
from crm_cakra.utils import apply_rename, capture_rename

FIXED = "Fixed Cost"
VARIABLE = "Variable Cost"

VALIDATED = "Validated"
INVALIDATED = "Invalidated"


class CRMCostComponent(Document):
	"""Template biaya siap pakai: satu komponen sudah memuat rincian + harganya.

	Dipanggil dari CRM Product. Yang bertipe Fixed Cost dijumlah jadi fixed cost
	per hari produk; yang Variable Cost disalin ke costing quotation supaya
	Procurement tinggal menyesuaikan, bukan mengetik dari nol.
	"""

	def before_validate(self):
		capture_rename(self, "component_name")

	def validate(self):
		self.block_edit_when_validated()
		self.total_amount = compute_amount(self.items)

	def block_edit_when_validated(self):
		"""Komponen yang sudah divalidasi terkunci dari perubahan.

		Kalau tidak, "Validated" cuma stempel sekali seumur hidup: rincian bisa
		diubah diam-diam dan quotation memakai angka yang tidak pernah disetujui.
		Status dibaca dari kondisi tersimpan, bukan dari dokumen yang dikirim
		client, supaya kuncinya tidak bisa dilewati dengan mengirim status lain.

		Tombol Validate/Invalidate sendiri memakai db_set, jadi tidak lewat sini.
		"""
		before = None if self.is_new() else self.get_doc_before_save()
		if before and before.status == VALIDATED:
			frappe.throw(
				_(
					"Cost Component {0} sudah divalidate, jadi tidak bisa disimpan. "
					"Klik Invalidate dulu kalau mau mengubahnya."
				).format(frappe.bold(self.name))
			)

	def on_update(self):
		apply_rename(self)
		refresh_linked_products(self.name)

	@staticmethod
	def default_list_data():
		columns = [
			{"label": "Component", "type": "Data", "key": "name", "width": "18rem"},
			{"label": "Type", "type": "Link", "key": "type", "width": "12rem"},
			{"label": "Total", "type": "Currency", "key": "total_amount", "width": "10rem"},
			{"label": "Date", "type": "Date", "key": "date", "width": "8rem"},
			{"label": "Valid Till", "type": "Date", "key": "validity_date", "width": "8rem"},
			{"label": "Status", "type": "Select", "key": "status", "width": "8rem"},
			{"label": "Description", "type": "Data", "key": "description", "width": "14rem"},
			{"label": "Disabled", "type": "Check", "key": "disabled", "width": "6rem"},
			{"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
		]
		rows = [
			"name",
			"component_name",
			"type",
			"total_amount",
			"date",
			"validity_date",
			"status",
			"description",
			"disabled",
			"modified",
		]
		return {"columns": columns, "rows": rows}


def behavior_of(cost_type):
	"""Peran sebuah tipe dalam rumus harga: FIXED atau VARIABLE.

	Tipe boleh ditambah user sesuka hati, tapi rumusnya cuma punya dua peran --
	yang menentukan bukan nama tipenya, melainkan field behavior di CRM Cost Type.
	Tipe yang sudah terhapus dianggap VARIABLE (peran yang tidak mengubah biaya
	tetap produk), bukan melempar error saat quotation disimpan.
	"""
	if not cost_type:
		return VARIABLE
	return frappe.get_cached_value("CRM Cost Type", cost_type, "behavior") or VARIABLE


def resolve(links, behavior=None):
	"""Ambil dokumen komponen dari baris CRM Cost Component Link, saring per peran.

	Menerima baris (bukan kode produk) supaya produk yang sedang divalidasi ikut
	terhitung dengan nilai barunya, bukan versi lama di cache.

	Gerbang pemakaian ada di sini: hanya komponen berstatus Validated yang boleh
	masuk perhitungan harga. Yang di-disable juga dilewati -- produk lama yang
	masih menautnya tidak perlu diedit satu per satu untuk menghentikannya.
	"""
	out = []
	for row in links or []:
		if not row.cost_component:
			continue
		doc = frappe.get_cached_doc("CRM Cost Component", row.cost_component)
		if doc.disabled or doc.status != VALIDATED:
			continue
		if behavior and behavior_of(doc.type) != behavior:
			continue
		out.append(doc)
	return out


def resolve_for_product(product_code, behavior=None):
	"""Komponen biaya yang dipanggil sebuah produk."""
	if not product_code:
		return []
	return resolve(frappe.get_cached_doc("CRM Product", product_code).cost_components, behavior)


def refresh_linked_products(component):
	"""Hitung ulang Fixed Cost/Day produk yang memanggil komponen ini.

	fixed_cost_per_day itu angka simpanan di produk. Tanpa ini, validate atau
	ubah harga komponen tidak terasa apa-apa sampai produknya kebetulan disimpan
	ulang -- fiturnya terlihat seperti tidak jalan.
	"""
	# Saat dipanggil dari on_update, cache dokumen ini masih berisi versi sebelum
	# save -- Frappe baru membuangnya setelah hook selesai. Tanpa baris ini,
	# perhitungan di bawah memakai status dan harga yang lama.
	frappe.clear_document_cache("CRM Cost Component", component)

	codes = frappe.get_all(
		"CRM Cost Component Link",
		filters={"cost_component": component, "parenttype": "CRM Product"},
		pluck="parent",
		distinct=True,
	)
	for code in codes:
		# Buang cache dulu: resolve() membaca produk lewat get_cached_doc, dan
		# komponen yang baru berubah masih tersimpan versi lamanya di sana.
		frappe.clear_document_cache("CRM Product", code)
		per_day = sum(
			(c.total_amount or 0) for c in resolve_for_product(code, FIXED)
		)
		if per_day != frappe.db.get_value("CRM Product", code, "fixed_cost_per_day"):
			frappe.db.set_value("CRM Product", code, "fixed_cost_per_day", per_day)
			frappe.clear_document_cache("CRM Product", code)


@frappe.whitelist()
def set_validation(name: str, action: str):
	"""Tombol Validate / Invalidate di halaman komponen."""
	if action not in ("validate", "invalidate"):
		frappe.throw(_("Unknown action {0}").format(action))

	doc = frappe.get_doc("CRM Cost Component", name)
	doc.check_permission("write")

	if action == "validate":
		if not doc.items:
			frappe.throw(_("Komponen tanpa rincian item tidak bisa divalidasi."))
		doc.status = VALIDATED
		doc.validated_by = frappe.session.user
		doc.validated_at = frappe.utils.now()
	else:
		doc.status = INVALIDATED
		doc.validated_by = None
		doc.validated_at = None

	# db_set: melewati validate() supaya invalidate_on_price_change tidak
	# langsung menarik status yang baru saja diset kembali ke Draft.
	doc.db_set(
		{
			"status": doc.status,
			"validated_by": doc.validated_by,
			"validated_at": doc.validated_at,
		}
	)
	refresh_linked_products(name)
	return {"status": doc.status, "validated_by": doc.validated_by, "validated_at": doc.validated_at}
