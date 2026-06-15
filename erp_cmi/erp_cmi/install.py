"""Setup erp_cmi.

erp_cmi STERIL terhadap core ERPNext: tidak membuat custom field / property setter
di doctype core (Sales Invoice, Company, dll). Semua itu ada di app `erpnext_custom`.
Doctype milik erp_cmi sendiri otomatis ter-sync oleh `bench migrate` dari file JSON-nya.

CATATAN: seed Role divisi + flow Agent Fleet sudah DIPINDAH ke app `agents`
(`agents.install`). erp_cmi tidak lagi mengurus Agent/Assistant.
"""


def after_install():
    after_migrate()


def after_migrate():
    # Tidak ada yang perlu di-seed dari erp_cmi (Agent Fleet pindah ke app `agents`).
    pass
