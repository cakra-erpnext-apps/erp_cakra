from frappe.model.document import Document


class FleetLocation(Document):
    def validate(self):
        self.jenis = ", ".join(
            label for flag, label in (("is_depo", "Depo"), ("is_route", "Route"), ("is_garasi", "Garasi")) if self.get(flag)
        )
