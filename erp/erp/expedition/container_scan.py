"""Scan nomor container (ISO 6346) dari attachment BL: PDF digital, PDF scan, atau gambar.

PDF ber-teks dibaca langsung (pypdfium2, cepat & eksak). PDF hasil scan dan file
gambar dirender lalu di-OCR (RapidOCR, ONNX/CPU, pip-only — recreate-safe via
ensure-apps.sh). Semua kandidat divalidasi check digit ISO 6346; kandidat OCR yang
gagal validasi dikembalikan sebagai "rejected" agar bisa dicek manual di UI.
"""

import base64
import io
import json
import re
import string

import frappe
from frappe import _

import pypdfium2 as pdfium

MAX_PAGES = 30
# ponytail: OCR ~2-5 dtk/halaman di CPU; BL + rider nyatanya <= 3 halaman.
# Naikkan kalau ada BL scan berhalaman banyak.
MAX_OCR_PAGES = 10
OCR_SCALE = 3.0  # ~216 DPI; scale lebih tinggi terbukti tidak menambah akurasi
PREVIEW_SCALE = 1.5  # preview dialog "Scan Containers" (cukup buat menarik kotak)

# ISO 6346: 3 huruf owner + kategori (U/J/Z) + 6 digit serial + 1 check digit.
# Spasi / titik / strip di antaranya (umum di layout BL) ditoleransi.
_RX = re.compile(r"\b([A-Z]{3}[UJZ])[ .-]?(\d{6})[ .-]?(\d)\b")
# Varian longgar untuk teks OCR: digit yang biasa salah baca sebagai huruf ikut
# ditangkap (O->0, I/L->1, S->5, B->8) lalu dinormalisasi sebelum cek check digit.
_RX_OCR = re.compile(r"\b([A-Z]{3}[UJZ])[ .-]{0,2}([0-9OILSB]{6})[ .-]{0,2}([0-9OILSB])\b")
_OCR_FIX = str.maketrans("OILSB", "01158")

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


# Ukuran container di BL: "20GP", "40'HQ", "20 TK", "20TANK", dst.
_SIZE_RX = re.compile(r"(20|40|45)\s*'?\s*(GP|HQ|HC|FR|TK|TANK|OT|RF|DV|DC)\b")
# Ukuran level-dokumen: "26x20'TK", "9X20'GP", "11 X 20 TK" — fallback bila baris
# container tidak menulis size satu-satu (umum di BL isotank).
_DOC_SIZE_RX = re.compile(r"\b\d+\s*X\s*(20|40|45)\s*'?\s*(GP|HQ|HC|FR|TK|TANK|OT|RF|DV|DC)\b")
# Seal no: token huruf+angka menempel setelah nomor container (SF0862766, 126601, 004577).
_SEAL_RX = re.compile(r"^[A-Z]{0,4}\d{4,10}$")


def _size_link(feet, typ):
	"""Petakan size BL ke record master Container Size (20 FEET / 40 FEET / ISOTANK)."""
	names = getattr(frappe.local, "_cmi_container_sizes", None)
	if names is None:
		names = set(frappe.get_all("Container Size", pluck="name"))
		frappe.local._cmi_container_sizes = names
	if typ in ("TK", "TANK") and "ISOTANK" in names:
		return "ISOTANK"
	cand = f"{feet} FEET"
	return cand if cand in names else None


def _parse_context(ctx):
	"""Seal & size dari potongan teks setelah satu nomor container (sampai nomor
	berikutnya). Seal dikumpulkan sampai ketemu token size (maks 3, digabung '/')."""
	seals, size = [], None
	for tok in re.split(r"[\s/\\(),;:.\-]+", ctx)[:8]:
		if not tok:
			continue
		sm = _SIZE_RX.fullmatch(tok)
		if sm:
			size = _size_link(sm.group(1), sm.group(2))
			break
		if _SEAL_RX.fullmatch(tok) and len(seals) < 3:
			seals.append(tok)
	return "/".join(seals) or None, size


def _extract(text, loose=False):
	"""Ambil (valid, rejected, details) dari sebuah teks.

	rejected = lolos pola tapi gagal check digit — di jalur OCR itu biasanya salah
	baca 1 digit, layak dicek manual. details[code] = {"seal", "size"}.
	"""
	text = text.upper()
	rx = _RX_OCR if loose else _RX
	matches = []
	for m in rx.finditer(text):
		code = m.group(1) + (m.group(2) + m.group(3)).translate(_OCR_FIX)
		matches.append((code, m.end()))
	valid, rejected, details, seen = [], [], {}, set()
	for i, (code, end) in enumerate(matches):
		if code in seen:
			continue
		seen.add(code)
		if not _check_digit_ok(code):
			rejected.append(code)
			continue
		valid.append(code)
		nxt = matches[i + 1][1] - 11 if i + 1 < len(matches) else len(text)
		ctx = text[end:min(nxt, end + 200)]
		# Teks OCR: satu baris = satu kotak teks hasil deteksi; baris berikutnya bisa
		# berasal dari kolom lain di halaman (PO No, HS Code) — jangan ikut terbaca
		# sebagai seal. Teks PDF digital urutannya benar, biarkan lintas-baris.
		if loose:
			ctx = ctx.split("\n", 1)[0]
		seal, size = _parse_context(ctx)
		details[code] = {"seal": seal, "size": size}
	# Fallback: BL yang menulis size hanya di header ("26x20'TK") — berlaku untuk
	# semua container HANYA bila ukuran di dokumen cuma satu macam.
	doc_sizes = {(m.group(1), m.group(2)) for m in _DOC_SIZE_RX.finditer(text)}
	if len(doc_sizes) == 1:
		feet, typ = next(iter(doc_sizes))
		fallback = _size_link(feet, typ)
		if fallback:
			for det in details.values():
				det["size"] = det["size"] or fallback
	return valid, rejected, details


_ocr_engine = None


def _ocr(pil_images):
	"""OCR daftar PIL image -> satu string teks."""
	global _ocr_engine
	import numpy as np
	from rapidocr_onnxruntime import RapidOCR

	if _ocr_engine is None:
		_ocr_engine = RapidOCR()
	lines = []
	for img in pil_images:
		res, _elapsed = _ocr_engine(np.asarray(img.convert("RGB")))
		lines.extend(r[1] for r in (res or []))
	return "\n".join(lines)


def _load_file(file_url):
	f = frappe.get_doc("File", {"file_url": file_url})
	if f.is_private and not f.has_permission("read"):
		frappe.throw(_("Tidak punya akses ke file ini."))
	content = f.get_content()
	if isinstance(content, str):
		content = content.encode("latin-1")
	return f, content


def _open_image(content, f):
	from PIL import Image

	try:
		img = Image.open(io.BytesIO(content))
		img.load()
	except Exception:
		frappe.throw(_("File {0} bukan PDF / gambar yang bisa dibaca.").format(f.file_name or f.file_url))
	return img


@frappe.whitelist()
def scan_containers(file_url):
	"""Ekstrak semua nomor container valid dari satu attachment (PDF / gambar).

	Returns {"containers": [...], "rejected": [...], "method": "text"|"ocr"}.
	"""
	f, content = _load_file(file_url)

	if b"%PDF-" in content[:1024]:
		try:
			doc = pdfium.PdfDocument(content)
		except Exception:
			frappe.throw(_("PDF rusak / tidak bisa dibaca."))
		try:
			text = "\n".join(
				doc[i].get_textpage().get_text_range() for i in range(min(len(doc), MAX_PAGES))
			)
			if len(text.strip()) >= 100:
				valid, rejected, details = _extract(text)
				return {"containers": valid, "rejected": rejected, "details": details, "method": "text"}
			# Nyaris tanpa teks = PDF hasil scan -> render halaman lalu OCR.
			pages = [doc[i].render(scale=OCR_SCALE).to_pil() for i in range(min(len(doc), MAX_OCR_PAGES))]
		finally:
			try:
				doc.close()
			except Exception:
				pass
	else:
		pages = [_open_image(content, f)]

	valid, rejected, details = _extract(_ocr(pages), loose=True)
	return {"containers": valid, "rejected": rejected, "details": details, "method": "ocr"}


@frappe.whitelist()
def render_pages(file_url):
	"""Halaman attachment sebagai gambar (data URL) untuk dialog pemilihan area."""

	def data_url(pil):
		buf = io.BytesIO()
		pil.convert("RGB").save(buf, "JPEG", quality=80)
		return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

	f, content = _load_file(file_url)
	if b"%PDF-" in content[:1024]:
		try:
			doc = pdfium.PdfDocument(content)
		except Exception:
			frappe.throw(_("PDF rusak / tidak bisa dibaca."))
		try:
			pages = [
				data_url(doc[i].render(scale=PREVIEW_SCALE).to_pil())
				for i in range(min(len(doc), MAX_OCR_PAGES))
			]
			truncated = len(doc) > MAX_OCR_PAGES
		finally:
			try:
				doc.close()
			except Exception:
				pass
	else:
		pages = [data_url(_open_image(content, f))]
		truncated = False
	return {"pages": pages, "truncated": truncated}


@frappe.whitelist()
def scan_regions(file_url, regions):
	"""Seperti scan_containers, tapi hanya memproses area (kotak) yang dipilih user.

	regions = [{"page": idx, "x0","y0","x1","y1"}] — fraksi 0..1 dari kiri-atas halaman.
	PDF ber-teks: ambil teks di dalam kotak (get_text_bounded). Scan/gambar: crop
	render halaman lalu OCR crop-nya saja.
	"""
	if isinstance(regions, str):
		regions = json.loads(regions or "[]")
	if not regions:
		frappe.throw(_("Tidak ada area yang dipilih."))

	f, content = _load_file(file_url)
	exact_text = []
	ocr_crops = []

	if b"%PDF-" in content[:1024]:
		try:
			doc = pdfium.PdfDocument(content)
		except Exception:
			frappe.throw(_("PDF rusak / tidak bisa dibaca."))
		try:
			full_text = "\n".join(
				doc[i].get_textpage().get_text_range() for i in range(min(len(doc), MAX_PAGES))
			)
			is_text_pdf = len(full_text.strip()) >= 100
			rendered = {}  # page idx -> PIL, biar 2 kotak di halaman sama tidak render 2x
			for r in regions:
				p = int(r.get("page") or 0)
				if p >= len(doc):
					continue
				page = doc[p]
				if is_text_pdf:
					w, h = page.get_size()  # koordinat PDF: origin kiri-BAWAH
					exact_text.append(
						page.get_textpage().get_text_bounded(
							left=float(r["x0"]) * w,
							right=float(r["x1"]) * w,
							bottom=h - float(r["y1"]) * h,
							top=h - float(r["y0"]) * h,
						)
					)
				else:
					if p not in rendered:
						rendered[p] = page.render(scale=OCR_SCALE).to_pil()
					pil = rendered[p]
					W, H = pil.size
					ocr_crops.append(
						pil.crop((
							int(float(r["x0"]) * W), int(float(r["y0"]) * H),
							int(float(r["x1"]) * W), int(float(r["y1"]) * H),
						))
					)
		finally:
			try:
				doc.close()
			except Exception:
				pass
	else:
		img = _open_image(content, f)
		W, H = img.size
		for r in regions:
			ocr_crops.append(
				img.crop((
					int(float(r["x0"]) * W), int(float(r["y0"]) * H),
					int(float(r["x1"]) * W), int(float(r["y1"]) * H),
				))
			)

	valid, rejected, details, seen = [], [], {}, set()
	for text, loose in ((("\n".join(exact_text)), False), ((_ocr(ocr_crops) if ocr_crops else ""), True)):
		v, rej, det = _extract(text, loose=loose)
		for c in v:
			if c not in seen:
				seen.add(c)
				valid.append(c)
				details[c] = det.get(c) or {}
		for c in rej:
			if c not in seen:
				seen.add(c)
				rejected.append(c)
	return {"containers": valid, "rejected": rejected, "details": details, "method": "text" if exact_text else "ocr"}


if __name__ == "__main__":
	assert _check_digit_ok("CSQU3054383")
	assert not _check_digit_ok("CSQU3054380")
	assert _RX.findall("MSKU 123456-7 CSQU3054383 TEMU.305438.3") == [
		("MSKU", "123456", "7"), ("CSQU", "305438", "3"), ("TEMU", "305438", "3"),
	]
	# Jalur OCR: salah baca umum ternormalisasi (O->0, S->5), gagal check digit -> rejected.
	# (_size_link butuh frappe/DB — self-check ini fokus ke pola regex & check digit.)
	v, rej, det = _extract("CSQU3O5438-3/126601 KMCU8913552", loose=True)
	assert (v, rej) == (["CSQU3054383"], ["KMCU8913552"])
	assert det["CSQU3054383"]["seal"] == "126601"
	print("ok")
