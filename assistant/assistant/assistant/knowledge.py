"""Pengetahuan sistem untuk assistant: how-to + kasus per modul di knowlagde/*.md.

Isinya tidak disuntik utuh ke prompt (terlalu besar); prompt hanya membawa daftar
topik, assistant mengambil isinya lewat tool read_knowledge. File baru di folder
itu langsung ikut terbaca, tanpa ubah kode.
"""

import os
import re

import frappe

MAX_CHARS = 12000


def _dir():
	return frappe.get_app_path("assistant", "assistant", "knowlagde")


def _files():
	try:
		names = sorted(f for f in os.listdir(_dir()) if f.endswith(".md"))
	except OSError:
		return {}
	out = {}
	for fn in names:
		with open(os.path.join(_dir(), fn), encoding="utf-8") as f:
			out[fn[:-3]] = f.read()
	return out


def _title(text, topic):
	m = re.search(r"^# (.+)$", text, re.M)
	return m.group(1).strip() if m else topic


def _sections(topic, text):
	"""Potong per heading '## '; teks sebelum heading pertama ikut section pertama."""
	parts = re.split(r"(?m)^(?=## )", text)
	head = parts[0] if parts and not parts[0].startswith("## ") else ""
	secs = [p for p in parts if p.startswith("## ")] or [text]
	if head and secs:
		secs[0] = head + secs[0]
	return [(topic, s.strip()) for s in secs]


def index_text():
	return "\n".join(f"- {t}: {_title(x, t)}" for t, x in _files().items())


def read(topic=None, query=None):
	files = _files()
	if not files:
		return {"_error": "Belum ada file knowledge."}
	topic = (topic or "").strip().lower().removesuffix(".md")
	if topic and not query:
		if topic not in files:
			return {"_error": f"Topik '{topic}' tidak ada.", "topics": list(files)}
		return {"topic": topic, "text": files[topic][:MAX_CHARS * 2]}

	words = [w for w in re.findall(r"\w+", (query or "").lower()) if len(w) >= 2]
	if not words:
		return {"topics": index_text()}
	pool = [s for t, x in files.items() if not topic or t == topic for s in _sections(t, x)]
	scored = []
	for t, sec in pool:
		low = sec.lower()
		heading = low.split("\n", 1)[0]
		score = sum(low.count(w) + 3 * heading.count(w) for w in words)
		# section yang memuat lebih banyak kata berbeda menang atas yang mengulang satu kata
		score *= sum(1 for w in words if w in low)
		if score:
			scored.append((score, t, sec))
	scored.sort(key=lambda r: -r[0])
	hits, used = [], 0
	for _s, t, sec in scored:
		if used + len(sec) > MAX_CHARS and hits:
			break
		hits.append({"topic": t, "section": sec})
		used += len(sec)
	if not hits:
		return {"result": "Tidak ada yang cocok.", "topics": index_text()}
	return {"query": query, "hits": hits}


def prompt_block():
	idx = index_text()
	if not idx:
		return ""
	return (
		"# PENGETAHUAN SISTEM ERP\n"
		"Kamu punya tool read_knowledge berisi panduan cara pakai, aturan, jurnal, dan kasus "
		"(yang pernah terjadi dan yang mungkin terjadi) untuk setiap modul ERP ini. Untuk "
		"pertanyaan 'bagaimana cara', 'kenapa', pesan error, angka/jurnal tidak sesuai, atau "
		"dokumen tidak bisa diproses: panggil read_knowledge(query=...) DULU, lalu jawab "
		"berdasarkan hasilnya. Jangan mengarang nama tombol, field, atau alur yang tidak ada di "
		"hasil. Kalau tidak ketemu, katakan terus terang dan sarankan hubungi admin/IT. "
		"Langkah bertanda 'Untuk IT/admin' jangan disuruh ke user biasa; sampaikan agar diteruskan ke IT. "
		"Panduan bergambar untuk user ada di menu desk Manual Book.\n"
		"Topik:\n" + idx
	)


TOOL_SCHEMA = {
	"name": "read_knowledge",
	"description": (
		"Cari pengetahuan sistem ERP (how-to, aturan, jurnal, kasus/troubleshoot) per modul. "
		"Isi 'query' dengan kata kunci pertanyaan user (nama dokumen, tombol, pesan error) untuk "
		"mendapat section yang paling relevan; atau isi 'topic' saja untuk membaca satu modul utuh. "
		"Daftar topik ada di blok PENGETAHUAN SISTEM ERP."
	),
	"input_schema": {
		"type": "object",
		"properties": {
			"query": {"type": "string", "description": "Kata kunci, mis. 'tarik expense note payment entry potongan'."},
			"topic": {"type": "string", "description": "Nama topik (opsional), mis. 'payment-entry'."},
		},
	},
}
