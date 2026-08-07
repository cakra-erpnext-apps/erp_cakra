import frappe
from frappe import _
from frappe.model.document import Document


class Mutation(Document):
    def _party(self):
        """(doctype, name) yang dimutasi — Vehicle atau Driver, dua-duanya punya field branch."""
        if self.mutation_type == "Driver":
            return "Driver", self.driver
        return "Vehicle", self.vehicle

    def validate(self):
        dt, name = self._party()
        if not name:
            frappe.throw(_("Pilih {0} yang dimutasi.").format(dt))
        # from_branch selalu posisi SAAT INI (nilai form bisa basi kalau lama terbuka)
        self.from_branch = frappe.db.get_value(dt, name, "branch")
        if not self.to_branch:
            frappe.throw(_("Pilih branch tujuan."))
        if self.to_branch == self.from_branch:
            frappe.throw(_("Branch tujuan sama dengan posisi sekarang ({0}).").format(self.from_branch or "-"))

    def on_submit(self):
        dt, name = self._party()
        current = frappe.db.get_value(dt, name, "branch")
        if (current or None) != (self.from_branch or None):
            frappe.throw(
                _("Posisi {0} sudah berubah (sekarang di {1}, dokumen ini mencatat dari {2}). "
                  "Amend/buat mutation baru.").format(name, current or "-", self.from_branch or "-")
            )
        frappe.db.set_value(dt, name, "branch", self.to_branch)

    def on_cancel(self):
        dt, name = self._party()
        current = frappe.db.get_value(dt, name, "branch")
        if current != self.to_branch:
            frappe.throw(
                _("Tidak bisa cancel: {0} sudah tidak di {1} (sekarang di {2}) — "
                  "sudah dipindah mutation lain.").format(name, self.to_branch, current or "-")
            )
        frappe.db.set_value(dt, name, "branch", self.from_branch)
