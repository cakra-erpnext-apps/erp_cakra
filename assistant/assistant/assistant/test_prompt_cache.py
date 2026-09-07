"""Cek cepat penanda prompt-cache. Jalankan:

	bench --site erp.localhost execute assistant.assistant.test_prompt_cache.run
"""

from assistant.assistant.llm import _with_cache_marks

MARK = {"type": "ephemeral"}


def run():
	system = [{"type": "text", "text": "skill A"}, {"type": "text", "text": "skill B"}]
	messages = [
		{"role": "user", "content": [{"type": "image", "source": {}}, {"type": "text", "text": "nota"}]},
		{"role": "assistant", "content": [{"type": "text", "text": "oke"}]},
	]

	sys2, msg2 = _with_cache_marks(system, messages)

	# Breakpoint hanya di ujung system dan ujung percakapan.
	assert sys2[-1]["cache_control"] == MARK
	assert "cache_control" not in sys2[0]
	assert msg2[-1]["content"][-1]["cache_control"] == MARK
	assert "cache_control" not in msg2[0]["content"][0]

	# Yang dikirim ke API tidak boleh mengotori list milik pemanggil — kalau bocor,
	# cache_control ikut tersimpan ke transcript dan terkirim lagi turn berikutnya.
	assert "cache_control" not in system[-1]
	assert "cache_control" not in messages[-1]["content"][-1]

	# Content berupa string mentah tetap dapat breakpoint (dibungkus jadi blok teks).
	_, msg3 = _with_cache_marks(system, [{"role": "user", "content": "halo"}])
	assert msg3[-1]["content"] == [{"type": "text", "text": "halo", "cache_control": MARK}]

	# Tidak ada input = tidak meledak.
	assert _with_cache_marks([], []) == ([], [])

	print("prompt cache marks OK")
