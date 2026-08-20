from frappe import _
from frappe.model.document import Document


def wrap_longitude(lon):
	"""Kembalikan bujur ke rentang sah -180..180.

	Peta Leaflet bisa digeser terus ke samping melewati batas dunia, dan titik
	yang diklik di salinan peta sebelah mengembalikan bujur seperti -261 (yaitu
	98,7 dikurangi 360). Secara peta letaknya sama persis, tapi mesin rute dan
	Google Maps menolaknya sebagai angka di luar batas -- error-nya muncul jauh
	di kemudian hari sebagai "400 Bad Request" yang tidak menyebut-nyebut peta.
	"""
	if lon is None:
		return lon
	while lon < -180:
		lon += 360
	while lon > 180:
		lon -= 360
	return lon


class FleetLocation(Document):
	def validate(self):
		self.jenis = ", ".join(
			label
			for flag, label in (
				("is_depo", "Depo"), ("is_route", "Route"), ("is_garasi", "Garasi"),
				("is_danger", "Danger"), ("is_rest", "Istirahat"),
			)
			if self.get(flag)
		)
		self.normalize_coordinates()

	def normalize_coordinates(self):
		"""Dijaga di server, bukan cuma di peta.

		Koordinat bisa masuk lewat beberapa pintu -- form desk, modal CRM, import,
		API -- dan cukup satu pintu lupa membereskan bujurnya untuk membuat lokasi
		yang kelihatan benar di peta tapi menolak dihitung jaraknya.
		"""
		if self.longitude is not None:
			self.longitude = round(wrap_longitude(self.longitude), 6)
		if self.latitude is not None and abs(self.latitude) > 90:
			from frappe import throw

			throw(_("Latitude {0} di luar batas (-90 sampai 90).").format(self.latitude))
