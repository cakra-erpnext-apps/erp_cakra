"""Cek pencarian knowledge: bench --site erp.localhost console lalu
exec(open('apps/assistant/assistant/assistant/test_knowledge.py').read(), {})"""

import os
import tempfile

from assistant.assistant import knowledge

d = tempfile.mkdtemp()
with open(os.path.join(d, "payment-entry.md"), "w", encoding="utf-8") as f:
	f.write("# Payment Entry\nintro\n## Cara: Tarik Expense Note\nklik Tarik Expense Note\n"
	        "## Kasus nyata: potongan admin\nadmin bank didebit\n")
with open(os.path.join(d, "stock.md"), "w", encoding="utf-8") as f:
	f.write("# Stock\n## Ringkasan alur\nstok masuk lewat PR\n")
orig = knowledge._dir
knowledge._dir = lambda: d
try:
	assert "payment-entry: Payment Entry" in knowledge.index_text()
	r = knowledge.read(query="tarik expense note")
	assert "## Cara: Tarik Expense Note" in r["hits"][0]["section"], r
	assert knowledge.read(topic="stock")["text"].startswith("# Stock")
	assert "_error" in knowledge.read(topic="nope")
	assert "topics" in knowledge.read(query="zzzz")
	r = knowledge.read(topic="payment-entry", query="stok")
	assert "hits" not in r, r  # filter topik tidak bocor ke stock.md
	# intro sebelum heading pertama ikut section pertama
	assert knowledge.read(query="intro")["hits"][0]["section"].startswith("# Payment Entry")
	print("ZZ knowledge OK")
finally:
	knowledge._dir = orig
