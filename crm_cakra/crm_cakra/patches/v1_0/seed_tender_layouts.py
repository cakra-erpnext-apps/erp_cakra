from crm_cakra.install import add_default_fields_layout


def execute():
	"""Pasang layout Tab Data & Side Panel CRM Tender di site yang sudah terlanjur terinstall.

	add_default_fields_layout() default-nya force=False alias insert-if-missing, jadi layout
	doctype lain yang sudah dikustom pengguna tidak ikut ditimpa. Dipakai lewat patch (bukan
	fixtures) supaya `bench migrate` tidak mengembalikan layout ke bawaan tiap kali jalan.
	"""
	add_default_fields_layout()
