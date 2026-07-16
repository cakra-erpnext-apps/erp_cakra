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
        # series `EXP/.cmi_type_code./.ABBR./.YY./.#####` (dikelola di Document Naming
        # Settings; counter reset per tipe+company+tahun).

    def make_real_number(self):
        # Draft agent di-Confirm (assign_number): pakai naming series yang sama persis
        # dengan simpan biasa → format & counter konsisten.
        return numbering.make_from_series(self)

    def validate(self):
        self._guard_locked()
        self._guard_invoiced()
        if self.void and not (self.void_reason or "").strip():
            frappe.throw("Alasan Void wajib diisi.")

    def _guard_invoiced(self):
        """EN yang SUDAH ditarik ke Reimburse Invoice = TERKUNCI: tak bisa diedit/
        validate/void. Untuk revisi, hapus dulu EN ini dari invoice-nya (atau void/
        revisi invoice). Bypass internal: doc.flags.ignore_invoiced_guard."""
        if self.flags.get("ignore_invoiced_guard"):
            return
        invs = _reimburse_invoices(self.name)
        if invs:
            frappe.throw(
                "Expense Note ini sudah ditarik ke invoice reimburse: <b>{0}</b>. "
                "Untuk revisi/void, hapus dulu Expense Note ini dari invoice tersebut "
                "(atau Void/Revisi invoice-nya).".format(", ".join(invs))
            )
        self._default_company()
        self._set_source_no()
        self._sync_cost_items()
        self._resolve_expense_accounts()
        self._require_accounts_if_validating()
        self._calculate_totals()
        self._sync_state()

    def _require_accounts_if_validating(self):
        """Saat Validate (validated & bukan void): SETIAP baris biaya WAJIB punya Expense
        Account. Cegah tervalidasi dgn akun kosong — cek di sini (bukan cuma saat jurnal),
        supaya jalur form maupun BULK sama-sama diblokir dgn pesan jelas."""
        if not self.validated or self.void:
            return
        # EN Reimburse: debit memakai Expense Class.reimburse_account (dicek saat
        # membuat jurnal), bukan expense_account — jangan blokir karena Account 1 kosong.
        if self.is_reimburse:
            return
        missing = []
        for it in (self.items or []):
            if flt(it.amount) and not it.expense_account:
                missing.append(it.expense_class or it.description or it.container_no or "?")
        if missing:
            frappe.throw(
                "Belum bisa divalidasi — baris berikut belum punya <b>Expense Account</b> "
                "(set <b>Account 1</b> di Expense Class terkait): <b>{0}</b>.".format(
                    ", ".join(dict.fromkeys(missing))
                )
            )

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
        is_reimb = bool(self.is_reimburse)
        # Debit per item:
        # - EN biasa    : expense_account (dari Expense Class.account_1, wajib root Expense).
        # - EN reimburse: Expense Class.reimburse_account (akun titipan, biasanya Asset
        #   "Reimbursement") — biaya titipan customer TIDAK masuk laba rugi. Kredit tetap
        #   Hutang Usaha supplier di kedua kasus (pembayaran via PE tidak berubah).
        debit = {}
        root_cache = {}
        reimb_cache = {}
        for it in (self.items or []):
            label = it.expense_class or it.description or it.container_no
            if is_reimb and it.expense_class:
                if it.expense_class not in reimb_cache:
                    reimb_cache[it.expense_class] = frappe.db.get_value(
                        "Expense Class", it.expense_class, "reimburse_account"
                    )
                acc = reimb_cache[it.expense_class]
                if not acc:
                    frappe.throw(
                        f"Baris '{label}': Expense Note ini <b>Reimburse</b>, tapi Expense Class "
                        f"<b>{it.expense_class}</b> belum punya <b>Account Reimbursement</b>. "
                        "Set di master Expense Class."
                    )
            else:
                acc = it.expense_account
                if not acc:
                    frappe.throw(
                        f"Baris '{label}' belum punya <b>Expense Account</b>. "
                        "Set <b>Account 1</b> di Expense Class terkait."
                    )
                # account_1 (= akun biaya) harus bertipe Expense — hanya untuk EN biasa.
                # (Reimburse memakai akun titipan yang memang bukan Expense.) Kalau bukan,
                # jurnal men-debit akun yang salah tanpa ketahuan. Akun Hutang/Payable
                # tempatnya di sisi KREDIT (Hutang Supplier), bukan di Expense Class.
                if not is_reimb:
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

        # Reimburse TIDAK punya jalur jurnal terpisah lagi: bedanya hanya akun DEBIT
        # (Expense Class.reimburse_account, di-set di loop atas). Kredit selalu Hutang
        # Supplier di bawah — jadi EN reimburse tetap muncul & terbayar normal di PE.

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


# ---- Reuse Master Job (expense) — container dianggap "sudah di-expense" kalau
# container_no-nya sudah ada di Expense Note lain (non-void), apa pun Expense Class-nya.
def _reimburse_invoices(en_name):
    """Sales Invoice reimburse (belum cancelled) yang menarik EN ini via custom_reimburse_items."""
    if not en_name:
        return []
    parents = frappe.get_all(
        "Reimburse Item", filters={"expense_note": en_name, "parenttype": "Sales Invoice"}, pluck="parent"
    )
    if not parents:
        return []
    return frappe.get_all(
        "Sales Invoice", filters={"name": ["in", list(set(parents))], "docstatus": ["!=", 2]}, pluck="name"
    )


@frappe.whitelist()
def reimburse_invoices(expense_note):
    """UI: daftar invoice reimburse yang menarik EN ini (untuk lock form + banner)."""
    return _reimburse_invoices(expense_note)


@frappe.whitelist()
def bulk_set_state(names, action, reason=None):
    """Bulk Validate / Void dari list view. action = 'validate' | 'void'.

    Tiap dokumen lewat save() -> validate() (cek Expense Account tetap berlaku), jadi
    yang akunnya kosong akan GAGAL (tidak divalidasi), bukan dilewati diam-diam.
    Return {ok:[...], failed:[{name, error}]}.
    """
    import json

    if isinstance(names, str):
        names = json.loads(names)
    ok, failed = [], []
    for name in names or []:
        try:
            doc = frappe.get_doc("Expense Note", name)
            if action == "validate":
                if doc.void:
                    frappe.throw("Sudah Void — tidak bisa divalidasi.")
                if doc.validated:
                    ok.append(name)
                    continue
                doc.validated = 1
            elif action == "invalidate":
                if not doc.validated:
                    ok.append(name)  # sudah tidak tervalidasi
                    continue
                if doc.get("paid"):
                    frappe.throw("Sudah Paid — batalkan status Paid dulu.")
                doc.validated = 0  # _sync_journal membatalkan JE-nya
            elif action == "void":
                if doc.void:
                    ok.append(name)
                    continue
                doc.void = 1
                doc.void_reason = (reason or "").strip() or doc.void_reason
            elif action == "unvoid":
                if not doc.void:
                    ok.append(name)  # sudah tidak void
                    continue
                doc.void = 0
            else:
                frappe.throw("Aksi tidak dikenal.")
            doc.save()
            frappe.db.commit()
            ok.append(name)
        except Exception as e:
            frappe.db.rollback()
            failed.append({"name": name, "error": str(e)[:200]})
    return {"ok": ok, "failed": failed}


def _expensed_container_map(exclude_en=None):
    """Map shipping_list -> set(container_no) yang sudah dipakai di Expense Note lain (non-void)."""
    ens = frappe.get_all(
        "Expense Note",
        filters={"void": ["!=", 1], "shipping_list": ["is", "set"]},
        fields=["name", "shipping_list"],
    )
    en_sl = {e.name: e.shipping_list for e in ens if e.name != exclude_en}
    if not en_sl:
        return {}
    items = frappe.get_all(
        "Expense Note Item",
        filters={"parent": ["in", list(en_sl)], "parenttype": "Expense Note", "container_no": ["is", "set"]},
        fields=["parent", "container_no"],
    )
    out = {}
    for it in items:
        sl = en_sl.get(it.parent)
        if sl and it.container_no:
            out.setdefault(sl, set()).add(it.container_no)
    return out


def _sl_container_map():
    out = {}
    for r in frappe.get_all(
        "Shipping List Container", filters={"parenttype": "Shipping List"}, fields=["parent", "container_no"]
    ):
        if r.container_no:
            out.setdefault(r.parent, set()).add(r.container_no)
    return out


def _expensed_pl_container_map(exclude_en=None):
    """Map packing_list -> set(container_no) yang sudah dipakai di Expense Note lain (non-void)."""
    ens = frappe.get_all(
        "Expense Note",
        filters={"void": ["!=", 1], "packing_list": ["is", "set"]},
        fields=["name", "packing_list"],
    )
    en_pl = {e.name: e.packing_list for e in ens if e.name != exclude_en}
    if not en_pl:
        return {}
    items = frappe.get_all(
        "Expense Note Item",
        filters={"parent": ["in", list(en_pl)], "parenttype": "Expense Note", "container_no": ["is", "set"]},
        fields=["parent", "container_no"],
    )
    out = {}
    for it in items:
        pl = en_pl.get(it.parent)
        if pl and it.container_no:
            out.setdefault(pl, set()).add(it.container_no)
    return out


def _pl_container_map():
    out = {}
    for r in frappe.get_all(
        "Packing List Item", filters={"parenttype": "Packing List"}, fields=["parent", "container_no"]
    ):
        cno = (r.container_no or "").strip()
        if cno:
            out.setdefault(r.parent, set()).add(cno)
    return out


@frappe.whitelist()
def expense_shipping_lists(doctype, txt, searchfield, start, page_len, filters):
    """Link query shipping_list di Expense Note. Aturan (mirror invoice):
    - Reuse OFF: sembunyikan SL yang SEMUA container-nya sudah di-expense (di EN lain).
    - Reuse ON : tampilkan HANYA SL yang sudah pernah di-expense (>=1 container).
    """
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    reuse = int(filters.get("reuse") or 0)
    txt = (txt or "").strip()
    used = _expensed_container_map()
    allc = _sl_container_map()
    fully = {sl for sl, conts in allc.items() if conts and conts <= used.get(sl, set())}

    conds = []
    if reuse:
        allow = list(used.keys())
        conds.append(["name", "in", allow or [""]])  # kalau belum ada, tampilkan kosong
    elif fully:
        conds.append(["name", "not in", list(fully)])
    if txt:
        conds.append(["name", "like", f"%{txt}%"])
    rows = frappe.get_all(
        "Shipping List", filters=conds or None, fields=["name"],
        limit_start=int(start or 0), limit_page_length=int(page_len or 20), order_by="modified desc",
    )
    return [[r.name] for r in rows]


@frappe.whitelist()
def expense_packing_lists(doctype, txt, searchfield, start, page_len, filters):
    """Link query packing_list di Expense Note (mirror expense_shipping_lists):
    - Reuse OFF: sembunyikan PL yang SEMUA container-nya sudah di-expense (di EN lain).
    - Reuse ON : tampilkan HANYA PL yang sudah pernah di-expense (>=1 container).
    """
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    reuse = int(filters.get("reuse") or 0)
    txt = (txt or "").strip()
    used = _expensed_pl_container_map()
    allc = _pl_container_map()
    fully = {pl for pl, conts in allc.items() if conts and conts <= used.get(pl, set())}

    conds = []
    if reuse:
        allow = list(used.keys())
        conds.append(["name", "in", allow or [""]])
    elif fully:
        conds.append(["name", "not in", list(fully)])
    if txt:
        conds.append(["name", "like", f"%{txt}%"])
    rows = frappe.get_all(
        "Packing List", filters=conds or None, fields=["name"],
        limit_start=int(start or 0), limit_page_length=int(page_len or 20), order_by="modified desc",
    )
    return [[r.name] for r in rows]


@frappe.whitelist()
def get_shipping_list_bls(shipping_list, reuse=0, current_en=None):
    """BLs of a Shipping List, for the Expense Note BL picker.

    Reuse OFF: BL yang SEMUA container-nya sudah di-expense (di EN lain) disembunyikan.
    Reuse ON : hanya BL yang sudah pernah di-expense (>=1 container terpakai).
    """
    if not shipping_list:
        return []
    bls = frappe.get_all(
        "Shipping List BL",
        filters={"parent": shipping_list, "parenttype": "Shipping List"},
        fields=["bl_no", "consignee"],
        order_by="idx",
    )
    conts = frappe.get_all(
        "Shipping List Container",
        filters={"parent": shipping_list, "parenttype": "Shipping List"},
        fields=["bl", "container_no"],
    )
    per_bl = {}
    for c in conts:
        if c.bl and c.container_no:
            per_bl.setdefault(c.bl, set()).add(c.container_no)
    used = _expensed_container_map(exclude_en=current_en).get(shipping_list, set())
    if int(reuse or 0):
        return [b for b in bls if per_bl.get(b.bl_no, set()) & used]
    # BL tanpa data container tetap tampil (tidak bisa dinilai "habis").
    return [b for b in bls if not per_bl.get(b.bl_no) or (per_bl[b.bl_no] - used)]


@frappe.whitelist()
def get_bl_containers(shipping_list, bl_no, reuse=0, current_en=None):
    """Containers of one BL within a Shipping List — untuk auto-fill tabel Connection
    Expense Note saat user pilih BL. Container yang SUDAH di-expense di EN lain (non-void)
    disembunyikan, kecuali reuse=1 ("Re Use Master Job")."""
    if not shipping_list or not bl_no:
        return []
    rows = frappe.get_all(
        "Shipping List Container",
        filters={"parent": shipping_list, "parenttype": "Shipping List", "bl": bl_no},
        fields=["container_no", "seal_no", "container_size", "customer"],
        order_by="idx",
    )
    if not int(reuse or 0):
        expensed = _expensed_container_map(exclude_en=current_en).get(shipping_list, set())
        rows = [r for r in rows if r.container_no not in expensed]
    return rows


@frappe.whitelist()
def get_packing_containers(packing_list, reuse=0, current_en=None):
    """Distinct containers of a Packing List (from its items) — alternative container
    source for the Expense Note when the user links a Packing List instead of a BL.
    Container yang SUDAH di-expense di EN lain (non-void) disembunyikan, kecuali
    reuse=1 ("Re Use Master Job")."""
    if not packing_list:
        return []
    rows = frappe.get_all(
        "Packing List Item",
        filters={"parent": packing_list, "parenttype": "Packing List"},
        fields=["container_no", "seal_no", "container_size", "customer"],
        order_by="idx",
    )
    expensed = set()
    if not int(reuse or 0):
        expensed = _expensed_pl_container_map(exclude_en=current_en).get(packing_list, set())
    seen, out = set(), []
    for r in rows:
        cno = (r.container_no or "").strip()
        if not cno or cno in seen or cno in expensed:
            continue
        seen.add(cno)
        out.append(r)
    return out
