"""Scan nomor container (ISO 6346) dari PDF attachment BL.

Teks diambil langsung dari PDF (pypdfium2) — bukan OCR, jadi hanya bekerja untuk
PDF digital ber-teks. PDF hasil scan gambar dikembalikan dengan has_text=False
supaya UI bisa memberi tahu user.
"""

import re
import string

import frappe
from frappe import _

import pypdfium2 as pdfium

MAX_PAGES = 30

# ISO 6346: 3 huruf owner + kategori (U/J/Z) + 6 digit serial + 1 check digit.
# Spasi / titik / strip di antaranya (umum di layout BL) ditoleransi.
_RX = re.compile(r"\b([A-Z]{3}[UJZ])[ .-]?(\d{6})[ .-]?(\d)\b")

# Nilai huruf ISO 6346: A=10, B=12, ... (kelipatan 11 dilewati).
_LETTER_VALS = {}
_v = 10
for _ch in string.ascii_uppercase:
	while _v % 11 == 0:
		_v += 1
	_LETTER_VALS[_ch] = _v
	_v += 1


def _check_digit_ok(code):
	"""code = 11 karakter (4 huruf + 7 digit)."""
	total = sum(
		(_LETTER_VALS[c] if c.isalpha() else int(c)) * (2**i)
		for i, c in enumerate(code[:10])
	)
	return total % 11 % 10 == int(code[10])


@frappe.whitelist()
def scan_containers(file_url):
	"""Ekstrak semua nomor container valid dari satu PDF attachment.

	Returns {"containers": [...], "has_text": bool}.
	"""
	f = frappe.get_doc("File", {"file_url": file_url})
	if f.is_private and not f.has_permission("read"):
		frappe.throw(_("Tidak punya akses ke file ini."))

	content = f.get_content()
	if isinstance(content, str):
		content = content.encode("latin-1")
	if b"%PDF-" not in content[:1024]:
		frappe.throw(_("File {0} bukan PDF.").format(f.file_name or file_url))

	try:
		doc = pdfium.PdfDocument(content)
	except Exception:
		frappe.throw(_("PDF rusak / tidak bisa dibaca."))
	try:
		text = "\n".join(
			doc[i].get_textpage().get_text_range() for i in range(min(len(doc), MAX_PAGES))
		)
	finally:
		try:
			doc.close()
		except Exception:
			pass

	found = []
	seen = set()
	for m in _RX.finditer(text.upper()):
		code = "".join(m.groups())
		if code in seen:
			continue
		seen.add(code)
		if _check_digit_ok(code):
			found.append(code)
	return {"containers": found, "has_text": bool(text.strip())}


if __name__ == "__main__":
	assert _check_digit_ok("CSQU3054383")
	assert not _check_digit_ok("CSQU3054380")
	assert _RX.findall("MSKU 123456-7 CSQU3054383 TEMU.305438.3") == [
		("MSKU", "123456", "7"), ("CSQU", "305438", "3"), ("TEMU", "305438", "3"),
	]
	print("ok")
