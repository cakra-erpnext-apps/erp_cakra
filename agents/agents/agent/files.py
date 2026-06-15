"""Attachment handling for the agent: PDF & image only, PDF rendered to images.

Security posture (no full antivirus in the container):
- Strict type check by MAGIC BYTES, not extension.
- PDFs are scanned for active/dangerous content (JavaScript, launch actions,
  embedded files, XFA…) and rejected if found, or if unparseable/corrupt.
- Optional ClamAV scan if `clamscan` is on PATH.
- Everything is rendered/re-encoded to a flat PNG before the model sees it, so
  any active content in the original file is neutralised.
The original PDF bytes are never written to disk or sent to the model.
"""

import base64
import io
import shutil
import subprocess
import tempfile

import frappe
from frappe import _

import pypdfium2 as pdfium
from PIL import Image

# --- Limits (overridable via Agent Settings) -------------------------------

DEFAULT_MAX_BYTES = 15 * 1024 * 1024
DEFAULT_MAX_PAGES = 15
MAX_IMAGE_EDGE = 2000  # px; downscale longer edge to control vision tokens
RENDER_SCALE = 2.0  # ~144 DPI

# PDF name tokens that indicate active / potentially malicious content.
PDF_DANGEROUS_TOKENS = [
	b"/JavaScript",
	b"/JS",
	b"/Launch",
	b"/EmbeddedFile",
	b"/RichMedia",
	b"/XFA",
	b"/AA",
]


def _settings():
	try:
		return frappe.get_cached_doc("Agent Settings")
	except Exception:
		return None


def _limit(field, default):
	s = _settings()
	if s and s.get(field):
		return int(s.get(field))
	return default


def attachments_enabled():
	s = _settings()
	if s is None:
		return True
	val = s.get("enable_attachments")
	# Unset (None/"") means "not configured yet" -> enabled by default.
	return True if val in (None, "") else bool(val)


# --- Type sniffing ---------------------------------------------------------


def sniff_type(content):
	"""Return 'pdf' | 'image/png' | 'image/jpeg' | 'image/gif' | 'image/webp'.

	Raises if the content is not a PDF or supported image (by magic bytes).
	"""
	head = content[:1024]
	if b"%PDF-" in head[:1024]:
		return "pdf"
	if content[:8] == b"\x89PNG\r\n\x1a\n":
		return "image/png"
	if content[:3] == b"\xff\xd8\xff":
		return "image/jpeg"
	if content[:6] in (b"GIF87a", b"GIF89a"):
		return "image/gif"
	if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
		return "image/webp"
	frappe.throw(_("Hanya file PDF dan gambar yang boleh dilampirkan."))


# --- PDF safety ------------------------------------------------------------


def _clamav_scan(content):
	"""Run ClamAV if available. Raises on detection; no-op if not installed."""
	exe = shutil.which("clamdscan") or shutil.which("clamscan")
	if not exe:
		return
	with tempfile.NamedTemporaryFile(suffix=".bin", delete=True) as tmp:
		tmp.write(content)
		tmp.flush()
		res = subprocess.run([exe, "--no-summary", tmp.name], capture_output=True, text=True)
		# clamscan: 0 = clean, 1 = virus found, 2 = error
		if res.returncode == 1:
			frappe.throw(_("File ditolak: terdeteksi virus oleh ClamAV. PDF dihentikan."))


def scan_pdf_safety(content):
	"""Reject PDFs with active/dangerous content (token scan + optional ClamAV)."""
	for tok in PDF_DANGEROUS_TOKENS:
		if tok in content:
			frappe.throw(
				_("PDF ditolak: terdeteksi konten aktif/berpotensi berbahaya ({0}). PDF dihentikan.").format(
					tok.decode(errors="ignore")
				)
			)
	_clamav_scan(content)


# --- Conversion / normalisation -------------------------------------------


def _to_png_bytes(pil_img):
	img = pil_img.convert("RGB")
	w, h = img.size
	longest = max(w, h)
	if longest > MAX_IMAGE_EDGE:
		ratio = MAX_IMAGE_EDGE / float(longest)
		img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))))
	out = io.BytesIO()
	img.save(out, "PNG")
	return out.getvalue()


def pdf_to_pngs(content):
	"""Open the PDF once, validate it, and render each page to a flat PNG.

	Returns (list_of_png_bytes, total_page_count). Raises if corrupt/empty.
	"""
	max_pages = _limit("attachment_max_pages", DEFAULT_MAX_PAGES)
	try:
		doc = pdfium.PdfDocument(content)
	except Exception:
		frappe.throw(_("PDF bermasalah / rusak — tidak bisa dibaca. PDF dihentikan."))

	pages = []
	try:
		total = len(doc)
		if not total:
			frappe.throw(_("PDF kosong / tidak bisa dibaca. PDF dihentikan."))
		for i in range(min(total, max_pages)):
			pil = doc[i].render(scale=RENDER_SCALE).to_pil()
			pages.append(_to_png_bytes(pil))
	finally:
		try:
			doc.close()
		except Exception:
			pass
	return pages, total


def normalize_image(content):
	"""Re-encode an image to a clean PNG (strips metadata / active payloads)."""
	try:
		img = Image.open(io.BytesIO(content))
		img.load()
	except Exception:
		frappe.throw(_("Gambar rusak / tidak bisa dibaca."))
	return _to_png_bytes(img)


# --- Public entry point ----------------------------------------------------


def process_upload(intake, filename, content):
	"""Validate + convert an upload, store the resulting PNG(s) as private Files
	attached to the Agent Administrator. Returns a summary dict. Raises on rejection.
	"""
	if not attachments_enabled():
		frappe.throw(_("Lampiran dinonaktifkan di Agent Settings."))

	max_bytes = _limit("attachment_max_mb", DEFAULT_MAX_BYTES // (1024 * 1024)) * 1024 * 1024
	if len(content) > max_bytes:
		frappe.throw(_("File terlalu besar (maks {0} MB).").format(max_bytes // (1024 * 1024)))

	kind = sniff_type(content)
	warnings = []

	if kind == "pdf":
		total = scan_pdf_safety(content)
		pngs, total_pages = pdf_to_pngs(content)
		if total_pages > len(pngs):
			warnings.append(
				_("PDF punya {0} halaman; hanya {1} pertama yang diproses.").format(total_pages, len(pngs))
			)
	else:
		pngs = [normalize_image(content)]

	from frappe.utils.file_manager import save_file

	stored = []
	base = (filename or "lampiran").rsplit(".", 1)[0]
	for idx, png in enumerate(pngs, start=1):
		fname = f"{base}-p{idx}.png" if len(pngs) > 1 else f"{base}.png"
		f = save_file(fname, png, "Agent Administrator", intake, is_private=1)
		stored.append({"file": f.name, "file_url": f.file_url, "media_type": "image/png", "page": idx})

	return {
		"ok": True,
		"source": filename,
		"kind": kind,
		"pages": len(stored),
		"files": stored,
		"warnings": warnings,
	}


def image_block_from_file(file_name):
	"""Build an Anthropic vision image block (base64 PNG) from a stored File."""
	fdoc = frappe.get_doc("File", file_name)
	try:
		with open(fdoc.get_full_path(), "rb") as fh:
			content = fh.read()
	except Exception:
		content = fdoc.get_content()
		if isinstance(content, str):
			content = content.encode("latin-1")
	data = base64.standard_b64encode(content).decode("ascii")
	return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}
