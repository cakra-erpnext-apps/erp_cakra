"""Expense Note — expedition / AP vendor cost note.

Mirrors the legacy ``exp_expensenote`` + ``ap_expense_note`` (see erp-blueprint.md):
a vendor cost document with item lines, optional link to a Packing List, an
optional reimburse-to-customer flag, and Indonesian tax fields (PPN / PPh).

This app does not (yet) post to a GL, so state is tracked with the same manual
``validated`` / ``closed`` / ``void`` triplet pattern used by Packing List rather
than the Frappe submit (docstatus) workflow.
"""

from frappe.model.document import Document
from frappe.utils import flt, now_datetime

import frappe

from erp.expedition import numbering


class ExpenseNote(Document):
    def autoname(self):
        self._default_company()
        # Draft buatan agent: nama sementara, nomor seri belum dipakai (lihat
        # numbering.assign_number — nomor asli diberikan saat user Save/Confirm).
        if self.flags.get("agent_draft"):
            self.name = numbering.draft_name()
            return
        # Dokumen normal: JANGAN set name di sini — biarkan Frappe memakai naming
        # series `EXP/.cmi_type_code./.cmi_company_code./.YY./.#####` (native, dikelola
        # di Document Naming Settings; counter reset per tipe+company+tahun).

    def make_real_number(self):
        # Dipakai saat draft agent di-Confirm (assign_number). Counter-nya BERBAGI
        # key yang sama dengan naming series di atas, jadi konsisten.
        return numbering.make_number_suffix(
            "EXP", self.expense_note_type, "Expense Note Type", company=self.company, date=self.date
        )

    def validate(self):
        self._guard_locked()
        if self.void and not (self.void_reason or "").strip():
            frappe.throw("Alasan Void wajib diisi.")
        self._default_company()
        self._set_source_no()
        self._sync_cost_items()
        self._resolve_expense_accounts()
        self._calculate_totals()
        self._sync_state()

    # Tipe JOB / NO-JOB: tanpa Connection & Expense Class — biaya diisi lewat tabel
    # Cost (description/note/qty/price/account). Baris Cost jadi sumber kebenaran:
    # items dibangun ulang darinya supaya total, Journal Entry (Dr akun per baris),
    # dan alur pembayaran tetap jalan tanpa perubahan.
    COST_TYPES = ("JOB", "NO-JOB")

    def _is_cost_type(self):
        return (self.expense_note_type or "") in self.COST_TYPES

    def _sync_cost_items(self):
        if not self._is_cost_type():
            return
        self.set("items", [])
        for c in self.costs or []:
            qty = flt(c.qty) or 1
            c.amount = qty * flt(c.price)
            self.append("items", {
                "description": (c.description or "") + (f" - {c.note}" if c.note else ""),
                "qty": qty,
                "price": c.price,
                "amount": c.amount,
                "expense_account": c.account,
                "cost_center": self.cost_center,
            })

    def _set_source_no(self):
        """Source No untuk list view: nomor Shipping List ATAU Packing List terkait."""
        self.source_no = self.shipping_list or self.packing_list or ""

    def _resolve_expense_accounts(self):
        """Selalu sinkronkan item.expense_account dari Expense Class.account_1.

        Akun biaya baris memang mirror Expense Class (diisi modal "Biaya per Expense
        Class"; tabel items disembunyikan, tak diedit manual). Dulu hanya mengisi yang
        KOSONG — jadi kalau Account 1 di Expense Class diubah *setelah* baris dibuat,
        akun lama "nyangkut" di baris (mis. sisa akun Liability yang salah set) dan
        bikin Validate gagal. Sekarang di-resolve ulang setiap kali agar mengganti
        Account 1 langsung memperbaiki semua baris (kosong maupun stale)."""
        cache = {}
        for it in self.items or []:
            if not it.expense_class:
                continue
            if it.expense_class not in cache:
                cache[it.expense_class] = frappe.db.get_value(
                    "Expense Class", it.expense_class, "account"
                )
            # Hanya timpa kalau Expense Class punya Account 1; kalau kosong, biarkan
            # nilai lama (jangan dikosongkan).
            if cache[it.expense_class]:
                it.expense_account = cache[it.expense_class]

    def _guard_locked(self):
        """Setelah Validate atau Void, dokumen terkunci: isi tidak boleh diubah.
        Transisi yang diizinkan hanya un-validate / un-void oleh Accounts Manager /
        System Manager. (Untuk meng-Void dokumen yang masih tervalidasi: batalkan
        validasi dulu.)"""
        if self.is_new():
            return
        before = self.get_doc_before_save()
        if not before:
            return
        is_mgr = bool(set(frappe.get_roles()) & {"Accounts Manager", "System Manager"})
        if before.validated:
            if self.validated:
                frappe.throw(
                    "Expense Note ini sudah <b>Tervalidasi</b> dan terkunci. "
                    "Batalkan validasi dulu untuk mengubah."
                )
            if not is_mgr:
                frappe.throw("Hanya Accounts Manager / System Manager yang boleh membatalkan validasi.")
        if before.void:
            if self.void:
                frappe.throw(
                    "Expense Note ini sudah di-<b>Void</b> dan terkunci. "
                    "Batalkan Void dulu untuk mengubah."
                )
            if not is_mgr:
                frappe.throw("Hanya Accounts Manager / System Manager yang boleh membuka Void.")

    def _default_company(self):
        # Company di-hide di form — isi otomatis agar save & penomoran tetap jalan.
        if not self.company:
            self.company = (
                frappe.defaults.get_global_default("company")
                or (frappe.get_all("Company", pluck="name", limit_page_length=1) or [None])[0]
            )

    # ---- totals ---------------------------------------------------------
    def _calculate_totals(self):
        total = 0.0
        for item in self.items or []:
            item.amount = flt(item.qty) * flt(item.price)
            total += flt(item.amount)
        self.subtotal = total
        self.total_amount = total

        # Kolom list view: daftar Expense Class unik di note ini.
        self.expense_classes = ", ".join(
            sorted({(it.expense_class or "").strip() for it in (self.items or []) if it.get("expense_class")})
        )

        # Komponen header (mirror Sales Invoice): tiap komponen boleh persen ATAU nominal.
        # Kalau persen (*_pct) diisi, nominal (*_amount) dihitung ulang saat save agar tetap
        # benar walau subtotal berubah; kalau tidak, pakai nominal manual (*_amount).
        # Discount dihitung dari DPP (subtotal); PPN & PPh dari DPP setelah discount.
        def _amt(field, base):
            pct = flt(self.get(field + "_pct"))
            if pct:
                amount = flt(base) * pct / 100.0
                setattr(self, field + "_amount", amount)
                return amount
            return flt(self.get(field + "_amount"))

        # Komponen per Expense Class disimpan di baris items (kolom tax/pph/discount).
        # Kalau ada, jumlahnya jadi nilai komponen (menang atas input header); kalau tidak,
        # pakai header (persen/nominal). Discount dari subtotal; PPN & PPh dari DPP.
        def _comp(field, base):
            cs = sum(flt(it.get(field)) for it in (self.items or []))
            if cs:
                setattr(self, field + "_amount", cs)
                setattr(self, field + "_pct", 0)
                return cs
            return _amt(field, base)

        discount = _comp("discount", total)
        dpp = flt(total) - discount
        tax = _comp("tax", dpp)
        pph = _comp("pph", dpp)
        # Materai: nominal per class (kolom items.materai) diakumulasi; kalau tak ada, pakai header.
        materai_cs = sum(flt(it.get("materai")) for it in (self.items or []))
        if materai_cs:
            self.materai_amount = materai_cs
        materai = flt(self.materai_amount)
        self.net_total = flt(total) - discount + tax - pph + materai

    # ---- state machine (boolean + actor + timestamp triplets) -----------
    def _sync_state(self):
        user = frappe.session.user
        now = now_datetime()

        if self.validated:
            if not self.validated_by:
                self.validated_by = user
                self.validated_date = now
        else:
            self.validated_by = None
            self.validated_date = None

        if self.closed:
            if not self.closed_datetime:
                self.closed_by = user
                self.closed_datetime = now
        else:
            self.closed_by = None
            self.closed_datetime = None

        if self.void:
            if not self.void_datetime:
                self.void_by = user
                self.void_datetime = now
        else:
            self.void_by = None
            self.void_datetime = None

    # ---- Journaling: Dr akun biaya (Expense Class) — Cr Hutang Supplier --------
    def on_update(self):
        self._sync_journal()

    def _sync_journal(self):
        """JE dibuat saat Validate (validated & bukan void), di-cancel saat
        un-validate / void. Dr akun biaya (per Expense Class.account_1), Cr Hutang
        Supplier (= Net Total); selisih PPN/PPh/Discount ke akun penyesuaian."""
        should_post = bool(self.validated) and not bool(self.void)
        je = self.journal_entry
        if should_post and not je:
            self.db_set("journal_entry", self._create_journal_entry())
        elif (not should_post) and je:
            self.db_set("journal_entry", None)  # putus link dulu agar JE bisa dihapus
            self._cancel_journal_entry(je)
            # JE hilang berarti status lunas tidak berlaku lagi.
            if self.paid:
                self.db_set({"paid": 0, "paid_date": None})

    def _create_journal_entry(self):
        from erpnext.accounts.party import get_party_account

        rate = flt(self.conversion_rate) or 1.0
        # Debit: jumlahkan amount item per expense_account (dari Expense Class.account_1)
        debit = {}
        root_cache = {}
        for it in (self.items or []):
            acc = it.expense_account
            label = it.expense_class or it.description or it.container_no
            if not acc:
                frappe.throw(
                    f"Baris '{label}' belum punya <b>Expense Account</b>. "
                    "Set <b>Account 1</b> di Expense Class terkait."
                )
            # account_1 (= akun biaya) harus bertipe Expense. Kalau bukan, jurnal akan
            # men-debit akun yang salah (mis. akun Hutang/Asset) tanpa ketahuan. Tolak
            # di sini dengan pesan jelas — akun Hutang/Payable tempatnya di sisi KREDIT
            # (akun Hutang Supplier), bukan di Expense Class.
            if acc not in root_cache:
                root_cache[acc] = frappe.db.get_value("Account", acc, "root_type")
            if root_cache[acc] != "Expense":
                frappe.throw(
                    f"Akun <b>{acc}</b> (baris '{label}') bukan <b>akun biaya</b> "
                    f"(root type: {root_cache[acc] or '?'}). <b>Account 1</b> di Expense Class "
                    "harus akun bertipe <b>Expense</b>. Akun Hutang/Payable dipakai di sisi "
                    "kredit (Hutang Supplier), bukan di Expense Class."
                )
            debit[acc] = flt(debit.get(acc, 0)) + flt(it.amount) * rate
        if not debit:
            frappe.throw("Tidak ada item biaya untuk dijurnal.")
        for acc in list(debit):
            debit[acc] = flt(debit[acc], 2)
        subtotal = flt(sum(debit.values()), 2)
        net = flt(flt(self.net_total) * rate, 2)

        # Credit: Hutang Supplier (akun payable default supplier / fallback setting)
        payable = get_party_account("Supplier", self.vendor, self.company)
        if not payable:
            payable = frappe.db.get_single_value("Expense Note Settings", "default_payable_account")
        if not payable:
            frappe.throw(
                f"Supplier <b>{self.vendor}</b> belum punya akun Hutang (Payable) default, dan "
                "<b>Default Hutang</b> di Expense Note Settings juga kosong."
            )

        cc = self.cost_center
        s = frappe.get_cached_doc("Expense Note Settings")
        adj = s.get("adjustment_account")

        def comp_acc(field, label):
            """Akun komponen (PPN/PPh/PPh22/Discount); fallback ke Akun Penyesuaian."""
            acc = s.get(field) or adj
            if not acc:
                frappe.throw(
                    f"Set <b>Akun {label}</b> di <b>Expense Note Settings</b> "
                    "(atau isi Akun Pajak & Penyesuaian sebagai fallback)."
                )
            return acc

        # Komponen pajak/discount dalam mata uang perusahaan (base).
        ppn = flt(flt(self.tax_amount) * rate, 2)
        pph = flt(flt(self.pph_amount) * rate, 2)
        disc = flt(flt(self.discount_amount) * rate, 2)

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = self.date
        je.company = self.company
        je.cheque_no = self.ref or self.name
        je.cheque_date = self.date
        je.user_remark = f"Expense Note {self.name}" + (f" — {self.remark}" if self.remark else "")

        # Debit: akun biaya (DPP).
        for acc, amt in debit.items():
            je.append("accounts", {"account": acc, "debit_in_account_currency": amt, "cost_center": cc})
        # Debit: PPN (menambah yang terutang).
        if ppn > 0:
            je.append("accounts", {"account": comp_acc("tax_account", "PPN (Masukan)"),
                                   "debit_in_account_currency": ppn, "cost_center": cc})
        # Credit: PPh / Discount (mengurangi yang terutang ke supplier).
        if pph > 0:
            je.append("accounts", {"account": comp_acc("pph_account", "PPh"),
                                   "credit_in_account_currency": pph, "cost_center": cc})
        if disc > 0:
            je.append("accounts", {"account": comp_acc("discount_account", "Discount"),
                                   "credit_in_account_currency": disc, "cost_center": cc})
        # Credit: Hutang Supplier (Net Total).
        je.append("accounts", {
            "account": payable, "party_type": "Supplier", "party": self.vendor,
            "credit_in_account_currency": net,
        })
        # Sisa pembulatan -> Akun Penyesuaian (kalau ada beda kecil).
        resid = flt((subtotal + ppn) - (pph + disc + net), 2)
        if abs(resid) > 0.005:
            if not adj:
                frappe.throw(
                    "Set <b>Akun Pajak & Penyesuaian</b> di Expense Note Settings (selisih pembulatan)."
                )
            line = {"account": adj, "cost_center": cc}
            line["credit_in_account_currency" if resid > 0 else "debit_in_account_currency"] = abs(resid)
            je.append("accounts", line)
        je.flags.ignore_permissions = True
        je.insert()
        je.submit()
        frappe.msgprint(f"Journal Entry <b>{je.name}</b> dibuat.", alert=True)
        return je.name

    def _cancel_journal_entry(self, je_name):
        """Batalkan lalu HAPUS Journal Entry milik Expense Note ini.

        JE dibuat & dimiliki penuh oleh Expense Note (saat Validate). Saat un-validate
        / void, daripada meninggalkan JE 'Cancelled' menumpuk di list, langsung dihapus
        — jejak audit tetap ada di Expense Note (validated/void + actor + timestamp).
        Cancel dulu (membalik GL) baru delete (membersihkan GL Entry-nya)."""
        if not je_name or not frappe.db.exists("Journal Entry", je_name):
            return
        je = frappe.get_doc("Journal Entry", je_name)
        if je.docstatus == 1:
            je.flags.ignore_permissions = True
            je.cancel()
        frappe.delete_doc(
            "Journal Entry", je_name,
            force=1, ignore_permissions=True, delete_permanently=True,
        )


@frappe.whitelist()
def get_shipping_list_bls(shipping_list):
    """BLs of a Shipping List, for the Expense Note BL picker."""
    if not shipping_list:
        return []
    return frappe.get_all(
        "Shipping List BL",
        filters={"parent": shipping_list, "parenttype": "Shipping List"},
        fields=["bl_no", "consignee"],
        order_by="idx",
    )


@frappe.whitelist()
def get_bl_containers(shipping_list, bl_no):
    """Containers of one BL within a Shipping List — to auto-fill the Expense Note
    Connection table when the user picks a BL. The user can then delete unneeded rows."""
    if not shipping_list or not bl_no:
        return []
    return frappe.get_all(
        "Shipping List Container",
        filters={"parent": shipping_list, "parenttype": "Shipping List", "bl": bl_no},
        fields=["container_no", "seal_no", "container_size", "customer"],
        order_by="idx",
    )


@frappe.whitelist()
def get_packing_containers(packing_list):
    """Distinct containers of a Packing List (from its items) — alternative container
    source for the Expense Note when the user links a Packing List instead of a BL."""
    if not packing_list:
        return []
    rows = frappe.get_all(
        "Packing List Item",
        filters={"parent": packing_list, "parenttype": "Packing List"},
        fields=["container_no", "seal_no", "container_size", "customer"],
        order_by="idx",
    )
    seen, out = set(), []
    for r in rows:
        cno = (r.container_no or "").strip()
        if not cno or cno in seen:
            continue
        seen.add(cno)
        out.append(r)
    return out
