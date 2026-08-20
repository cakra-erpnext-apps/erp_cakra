import secrets

import frappe
from frappe.model.document import Document


class CustomerJob(Document):
    def before_insert(self):
        # 32 byte acak: ruang tebakan 2^256, tidak mungkin ditebak brute force
        self.token = secrets.token_urlsafe(32)
        self.share_url = f"{frappe.utils.get_url()}/track?t={self.token}"

    def validate(self):
        do = frappe.db.get_value(
            "Dispatch Order", self.dispatch_order, ["packing_list", "customer_list"], as_dict=True
        )
        if do:
            self.packing_list = do.packing_list
            self.customer_list = do.customer_list
