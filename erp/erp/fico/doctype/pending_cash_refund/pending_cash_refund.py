"""Refund Pending Cash — pengembalian uang muka ke bank, dokumen SENDIRI bernomor.

Kuncinya PARTY, bukan satu kasbon: yang dikembalikan supplier/customer sering menutup
beberapa kasbon sekaligus dalam SATU transfer. User memilih kasbonnya sendiri di tabel
`allocations`, satu baris per kasbon; Refund Amount di kepala dokumen adalah TURUNAN dari
jumlah baris itu, bukan ketikan — dengan begitu angka "sudah direfund" per kasbon selalu
punya barisnya sendiri dan tidak pernah bisa berbeda dari totalnya.

Dua arah, dibedakan Party Type:
  Supplier — kasbon Cash Outflow (uang muka kita serahkan). Refund = uang balik ke bank.
  Customer — kasbon Cash Inflow (uang muka diterima). Refund = uang kita kembalikan.

Jurnalnya jurnal BARU bertanggal refund, kebalikan jurnal Paid tiap kasbon yang terpotong —
jurnal Paid TIDAK pernah disentuh, jadi refund di bulan lain aman walau bulan pembayarannya
sudah tutup periode. Itu sebabnya refund bukan Unpaid/Void di kasbon induknya.

Alur dokumennya sama dengan Pending Cash: Draft -> Validated (jurnal terbit) -> Void.
SIMPAN TIDAK MENERBITKAN JURNAL — draft boleh diperbaiki berkali-kali tanpa mengotori GL;
jurnalnya baru lahir saat Validate. Invalidate membatalkan lalu MENGHAPUS jurnalnya
(salah input tidak meninggalkan sampah cancelled), sedangkan Void menyimpannya sebagai
jejak bahwa refund itu pernah dicatat — itu bedanya dua aksi yang sekilas mirip.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import flt, formatdate, getdate, now_datetime

# Party Type -> field party di Pending Cash. Sekaligus penentu ARAH: kasbon ber-`pay_to`
# selalu Cash Outflow dan ber-`receive_from` selalu Cash Inflow (lihat _sync_party di
# pending_cash.py), jadi arah tidak perlu field sendiri di sini.
PARTY_FIELD = {"Supplier": "pay_to", "Customer": "receive_from"}

# Field yang terkunci begitu jurnalnya terbentuk.
LOCKED = ("party_type", "party", "bank_account", "refund_date", "amount", "currency", "exchange_rate")


class PendingCashRefund(Document):
    def validate(self):
        self._defaults()
        self._guard_locked_fields()
        self._sync_state()
        self._allocate()
        # Kolom PC di list view: nomor kasbon yang dipotong refund ini. Diisi di sini
        # (bukan disinkron dari luar) karena sumbernya tabel dokumen ini sendiri.
        self.pending_cash_no = (
            ", ".join(sorted({r.pending_cash for r in self.allocations if r.pending_cash})) or None
        )

    def before_save(self):
        # Kasbon yang rollup-nya perlu dihitung ulang sesudah simpan — termasuk yang
        # BARU SAJA dilepas dari alokasi, kalau tidak angka Refunded-nya tertinggal tinggi.
        before = self.get_doc_before_save()
        self._touched = {r.pending_cash for r in self.allocations}
        if before:
            self._touched |= {r.pending_cash for r in before.allocations}

    def _defaults(self):
        if not self.company:
            self.company = frappe.defaults.get_user_default(
                "Company"
            ) or frappe.defaults.get_global_default("company")
        company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
        if not self.currency:
            self.currency = company_currency
        # Kurs != 1 pada mata uang yang sama membuat nilai company-currency-nya salah tanpa
        # ada yang menyadari — dipaksa di server, sama seperti di Pending Cash.
        if self.currency == company_currency:
            self.exchange_rate = 1
        elif flt(self.exchange_rate) <= 0:
            frappe.throw(f"Exchange Rate wajib diisi untuk mata uang selain {company_currency}.")
        if not self.refund_date:
            self.refund_date = getdate()

    def _guard_locked_fields(self):
        """Begitu jurnalnya terbentuk, isi refund terkunci: mengubah nominal/party/tanggal
        di sini membuat dokumen tidak lagi cocok dengan jurnal yang sudah diposting. Salah
        input = Void, lalu buat refund baru."""
        before = self.get_doc_before_save()
        if not before or not before.validated:
            return
        changed = [self.meta.get_label(f) for f in LOCKED if self.get(f) != before.get(f)]
        # Dibandingkan ISINYA saja: as_dict() ikut membawa modified/idx/creation yang
        # selalu berbeda antar-muatan, dan `outstanding`/`paid_date` cuma angka turunan.
        def rows(doc):
            return sorted((r.pending_cash, flt(r.amount)) for r in doc.allocations)

        if rows(self) != rows(before):
            changed.append("Pending Cash")
        if changed:
            frappe.throw(
                f"Refund <b>{self.name}</b> sudah Validated, isinya tidak bisa diubah "
                f"(<b>{', '.join(changed)}</b>). <b>Invalidate</b> dulu untuk memperbaikinya."
            )

    def _sync_state(self):
        if self.validated:
            if not self.validated_date:
                self.validated_by = frappe.session.user
                self.validated_date = now_datetime()
        else:
            self.validated_by = None
            self.validated_date = None
        if self.void:
            if not self.void_datetime:
                self.void_by = frappe.session.user
                self.void_datetime = now_datetime()
        else:
            self.void_by = None
            self.void_datetime = None

    # ---- alokasi FIFO ---------------------------------------------------
    def open_pending_cash(self):
        """Kasbon party ini yang masih punya sisa, URUT TERTUA DULU (itu arti FIFO-nya).

        Disaring per company + currency: jurnal refund menjumlah beberapa kasbon jadi satu
        baris bank, dan itu cuma benar kalau semuanya satu mata uang & satu perusahaan.
        """
        from erp.fico.doctype.pending_cash.pending_cash import refund_available

        if not (self.party_type and self.party and self.company and self.currency):
            return []
        rows = frappe.get_all(
            "Pending Cash",
            filters={
                PARTY_FIELD[self.party_type]: self.party,
                "company": self.company,
                "currency": self.currency,
                "paid": 1,
                "void": 0,
                # Kasbon "Don't Post to GL" tidak punya jurnal, jadi tidak ada baris uang
                # muka yang bisa dikembalikan — merefundnya berarti mengkredit uang muka
                # yang tidak pernah didebit. Sama alasannya dengan pengecualiannya di
                # Payment Entry (lihat _pending_cash_used di erpnext_custom).
                "dont_post_to_gl": 0,
            },
            fields=["name", "total", "paid_date", "date"],
            order_by="paid_date asc, date asc, name asc",
            ignore_permissions=True,
        )
        out = []
        for r in rows:
            # Refund yang sedang disimpan ini dikecualikan: angka lamanya jangan
            # mengurangi sisa yang justru sedang dihitung ulang.
            r.available = refund_available(r, exclude=self.name)
            if r.available > 0.005:
                out.append(r)
        return out

    def _allocate(self):
        if self.void:
            return
        if not self.allocations:
            frappe.throw("Pilih dulu Pending Cash-nya di tabel <b>Refund Pending Cash Item</b>.")
        self._check_allocations({r.name: r for r in self.open_pending_cash()})
        self._assert_not_before_paid()

    def _assert_not_before_paid(self):
        """Refund tidak boleh bertanggal sebelum kasbon terakhir dibayar.

        Bukan sekadar kerapian tanggal: jurnal refund membalik jurnal Paid, dan mendahului
        tanggalnya berarti membukukan pengembalian uang muka yang pada tanggal itu belum
        pernah keluar — saldo uang mukanya jadi minus di antara dua tanggal itu.
        """
        dates = [getdate(r.paid_date) for r in self.allocations if r.paid_date]
        if not dates:
            return
        last = max(dates)
        if getdate(self.refund_date) < last:
            frappe.throw(
                f"Refund Date <b>{formatdate(self.refund_date)}</b> lebih awal dari Paid Date "
                f"terakhir di tabel (<b>{formatdate(last)}</b>)."
            )

    def _check_allocations(self, available):
        """Baris yang dipilih user (atau datang dari tombol Refund di kasbonnya) diperiksa
        ulang di sini: server tidak boleh percaya baris dari luar form.

        Amount induk MENGIKUTI jumlah baris, bukan sebaliknya — begitu barisnya ada,
        merekalah faktanya, dan menolak simpan cuma karena angka di atas belum diperbarui
        adalah error yang tidak menolong siapa pun.
        """
        total = 0
        seen = set()
        for row in self.allocations:
            pc = available.get(row.pending_cash)
            if not pc:
                frappe.throw(
                    f"Pending Cash <b>{row.pending_cash}</b> tidak punya sisa yang bisa "
                    f"direfund untuk {self.party_type} <b>{self.party}</b>."
                )
            if row.pending_cash in seen:
                # Dua baris untuk kasbon yang sama lolos cek sisa satu-satu tapi
                # gabungannya bisa melebihi — dilarang saja, tidak ada gunanya.
                frappe.throw(f"Pending Cash <b>{row.pending_cash}</b> dipilih lebih dari sekali.")
            seen.add(row.pending_cash)
            if flt(row.amount) <= 0:
                frappe.throw(f"Nominal refund untuk {row.pending_cash} harus lebih dari 0.")
            if flt(row.amount) > pc.available + 0.005:
                frappe.throw(
                    f"Refund {flt(row.amount):,.0f} melebihi sisa Pending Cash "
                    f"{row.pending_cash} ({pc.available:,.0f})."
                )
            row.paid_date = pc.paid_date
            row.outstanding = pc.available
            total = flt(total + flt(row.amount), 2)
        self.amount = total

    # ---- jurnal ---------------------------------------------------------
    def on_update(self):
        self._sync_journal()
        self._sync_parents()

    def on_trash(self):
        # Dokumen dibuang sama sekali (bukan void): jurnalnya ikut dibuang, bukan
        # ditinggal menggantung tanpa dokumen yang menjelaskannya.
        self._touched = {r.pending_cash for r in self.allocations}
        if self.journal_entry:
            je = self.journal_entry
            self.db_set("journal_entry", None)  # link check menolak cancel/delete selama masih ditaut
            self._cancel_journal_entry(je, delete=True)

    def after_delete(self):
        self._sync_parents()

    def _sync_journal(self):
        """Jurnal ADA persis selama dokumennya Validated dan tidak Void. Simpan biasa
        (draft) tidak menerbitkan apa pun."""
        should_post = bool(self.validated) and not bool(self.void)
        je = self.journal_entry
        if should_post and not je:
            self.db_set("journal_entry", self._create_journal_entry())
        elif (not should_post) and je:
            self.db_set("journal_entry", None)  # link check: lepas dulu, baru cancel
            # Invalidate = salah input, jurnalnya dibuang sekalian. Void = jejak, jurnal
            # cancel-nya sengaja disimpan sebagai bukti refund itu pernah dicatat.
            delete = bool(self.flags.get("delete_journal"))
            self._cancel_journal_entry(je, delete=delete)
            if not delete:
                self.db_set("journal_entry", je)

    def _bank_gl_account(self):
        acc = frappe.db.get_value("Bank Account", self.bank_account, "account")
        if not acc:
            frappe.throw(
                f"Bank Account <b>{self.bank_account}</b> belum tertaut ke akun GL "
                "(field <b>Account</b> di Bank Account)."
            )
        return acc

    def _create_journal_entry(self):
        """SATU jurnal untuk seluruh refund: sebaris uang muka per kasbon yang terpotong,
        plus SATU baris bank sejumlah totalnya — uangnya memang satu kali transfer, dan
        rekonsiliasi bank mencari satu angka, bukan pecahan per kasbon.

        Akun uang muka, cost center, dan kurs diambil dari kasbon masing-masing: membalik
        jurnal Paid harus pakai akun & kurs BUKU-nya, bukan yang berlaku hari ini.
        """
        masuk_bank = self.party_type == "Supplier"
        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.company = self.company
        je.posting_date = self.refund_date
        je.user_remark = f"Refund Pending Cash {self.name}" + (
            f" - {self.remark}" if self.remark else ""
        )

        side = "credit" if masuk_bank else "debit"
        total = 0
        cost_center = None
        for row in self.allocations:
            pc = frappe.get_doc("Pending Cash", row.pending_cash)
            base = flt(flt(row.amount) * (flt(pc.exchange_rate) or 1.0), 2)
            total = flt(total + base, 2)
            cost_center = cost_center or pc.cost_center
            account = pc._advance_account()
            je.append(
                "accounts",
                {
                    "account": account,
                    **pc._advance_party(account),
                    f"{side}_in_account_currency": base,
                    side: base,
                    "cost_center": pc.cost_center,
                    "user_remark": row.pending_cash,
                },
            )

        # Bank menerima/mengeluarkan uang pada kurs HARI REFUND, sedangkan uang mukanya
        # dihapus pada kurs BUKU-nya. Selisihnya nyata (untung/rugi kurs) dan harus
        # dibukukan, kalau tidak jurnalnya tidak seimbang.
        bank_side = "debit" if masuk_bank else "credit"
        bank_base = flt(flt(self.amount) * (flt(self.exchange_rate) or 1.0), 2)
        je.append(
            "accounts",
            {
                "account": self._bank_gl_account(),
                f"{bank_side}_in_account_currency": bank_base,
                bank_side: bank_base,
                "cost_center": cost_center,
            },
        )
        self._append_exchange_difference(je, flt(bank_base - total, 2), masuk_bank, cost_center)
        je.flags.ignore_permissions = True
        je.insert()
        # Judul diisi SESUDAH insert: JournalEntry.validate menimpa title dengan
        # get_title() selama dokumennya masih baru. Submit tidak menimpanya lagi.
        je.title = f"{self.name} - {self.party}"
        je.submit()
        return je.name

    def _append_exchange_difference(self, je, diff, masuk_bank, cost_center):
        """Selisih antara nilai bank (kurs refund) dan uang muka (kurs buku)."""
        if abs(diff) <= 0.005:
            return
        account = frappe.get_cached_value("Company", self.company, "exchange_gain_loss_account")
        if not account:
            frappe.throw(
                "Kurs refund berbeda dari kurs Pending Cash-nya, tapi "
                "<b>Exchange Gain / Loss Account</b> di Company "
                f"<b>{self.company}</b> belum di-set."
            )
        # diff > 0: sisi bank lebih besar, jadi sisi lawannya yang perlu ditambah.
        side = ("credit" if masuk_bank else "debit") if diff > 0 else ("debit" if masuk_bank else "credit")
        je.append(
            "accounts",
            {
                "account": account,
                f"{side}_in_account_currency": abs(diff),
                side: abs(diff),
                "cost_center": cost_center,
            },
        )

    def _cancel_journal_entry(self, je_name, delete=False):
        if not frappe.db.exists("Journal Entry", je_name):
            return
        je = frappe.get_doc("Journal Entry", je_name)
        if je.docstatus == 1:
            je.flags.ignore_permissions = True
            je.cancel()
        if delete:
            # Baris GL/Payment Ledger sisa cancel dibuang dulu — link check delete_doc
            # menolak selama baris itu masih ada (sama seperti di Pending Cash).
            for ledger in ("GL Entry", "Payment Ledger Entry"):
                frappe.db.delete(ledger, {"voucher_type": "Journal Entry", "voucher_no": je_name})
            frappe.delete_doc("Journal Entry", je_name, ignore_permissions=True)

    def _sync_parents(self):
        from erp.fico.doctype.pending_cash.pending_cash import sync_refunded

        touched = getattr(self, "_touched", None) or {r.pending_cash for r in self.allocations}
        for name in touched:
            sync_refunded(name)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def open_pending_cash_query(doctype, txt, searchfield, start, page_len, filters):
    """Isi dropdown Pending Cash di tabel refund: HANYA kasbon yang sudah Paid, belum Void,
    dan sisanya masih ada — plus yang belum dipilih di baris lain dokumen ini.

    Dihitung lewat `open_pending_cash` yang sama dengan validate, bukan disalin jadi SQL
    sendiri: dropdown yang menawarkan kasbon lalu ditolak saat simpan (atau sebaliknya)
    persis lahir dari dua rumus kembar yang lama-lama berbeda.
    """
    filters = filters or {}
    doc = frappe.new_doc("Pending Cash Refund")
    doc.party_type = filters.get("party_type")
    doc.party = filters.get("party")
    doc.company = filters.get("company")
    doc.currency = filters.get("currency")
    doc._defaults()
    if filters.get("exclude"):
        doc.name = filters["exclude"]

    taken = set(filters.get("chosen") or [])
    txt = (txt or "").lower()
    rows = [
        r for r in doc.open_pending_cash() if r.name not in taken and txt in r.name.lower()
    ]
    # Sisa & tanggal bayar ikut ditampilkan di daftar — itu yang dipakai user memilih,
    # percuma kalau harus buka kasbonnya satu-satu dulu.
    return [
        [r.name, frappe.format_value(r.available, {"fieldtype": "Currency"}), str(r.paid_date or "")]
        for r in rows[start : start + page_len]
    ]


@frappe.whitelist()
def row_info(pending_cash, exclude=None):
    """Tanggal bayar + sisa satu kasbon, untuk mengisi baris begitu user memilihnya."""
    from erp.fico.doctype.pending_cash.pending_cash import refund_available

    pc = frappe.db.get_value(
        "Pending Cash", pending_cash, ["name", "total", "paid_date"], as_dict=True
    )
    if not pc:
        return {}
    return {"paid_date": pc.paid_date, "available": refund_available(pc, exclude=exclude)}


@frappe.whitelist()
def bulk_validate(names):
    """Terbitkan jurnalnya. Isi dokumen terkunci sesudah ini — perbaikan lewat Invalidate."""
    from erp.fico.doctype.pending_cash.pending_cash import _run_bulk

    def handler(doc):
        if doc.void:
            frappe.throw(f"Refund {doc.name} sudah Void.")
        if doc.validated:
            frappe.throw(f"Refund {doc.name} sudah Validated.")
        doc.validated = 1
        doc.save()

    return _run_bulk(names, handler, doctype="Pending Cash Refund")


@frappe.whitelist()
def bulk_invalidate(names):
    """Batalkan Validate yang salah: jurnal di-cancel lalu DIHAPUS, dokumen balik ke Draft.

    Beda dengan Void yang menyimpan jurnal cancel-nya sebagai jejak — Invalidate memang
    untuk salah input, dan salah input tidak layak meninggalkan bekas di daftar jurnal.
    """
    from erp.fico.doctype.pending_cash.pending_cash import _run_bulk

    def handler(doc):
        if doc.void:
            frappe.throw(f"Refund {doc.name} sudah Void.")
        if not doc.validated:
            frappe.throw(f"Refund {doc.name} belum Validated.")
        doc.validated = 0
        doc.flags.delete_journal = True
        doc.save()

    return _run_bulk(names, handler, doctype="Pending Cash Refund")


@frappe.whitelist()
def bulk_void(names):
    """Batalkan refund: jurnalnya di-cancel (tetap disimpan sebagai jejak), nomornya tetap
    terpakai sehingga refund berikutnya lanjut ke urutan sesudahnya."""
    from erp.fico.doctype.pending_cash.pending_cash import _run_bulk

    def handler(doc):
        if doc.void:
            frappe.throw(f"Refund {doc.name} sudah Void.")
        doc.void = 1
        doc.save()

    return _run_bulk(names, handler, doctype="Pending Cash Refund")
