"""Baris alokasi refund: berapa dari satu Pending Cash yang ikut dikembalikan.

Diisi SERVER (FIFO di controller Pending Cash Refund), bukan diketik user — itu sebabnya
semua fieldnya read-only. Baris inilah satu-satunya sumber angka "sudah direfund" per
kasbon (lihat refunded_total di pending_cash.py).
"""

from frappe.model.document import Document


class PendingCashRefundAllocation(Document):
    pass
