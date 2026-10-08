"""Penerjemah filter/urutan list CRM -> SQL Ascend (tanpa koneksi).

	bench --site erp.localhost execute crm_cakra.integrations.test_ascend.run
"""

from crm_cakra.integrations.ascend import _list_order, _list_where


def run():
	parts, args = _list_where({"disabled": 0, "expired_date": [">=", "2026-10-06"]}, None)
	assert parts == ["e.Disabled = %s", "e.EffectiveDate >= %s"] and args == [0, "2026-10-06"], (parts, args)

	parts, args = _list_where({"customer_id": ["in", "A, B"], "creation": ["between", ["2026-01-01", "2026-12-31"]]}, "kemira")
	assert parts[0] == "c.CustomerName in (%s, %s)" and parts[1] == "e.CreateDate BETWEEN %s AND %s", parts
	assert args[:4] == ["A", "B", "2026-01-01", "2026-12-31"] and args[4] == "%kemira%", args

	assert _list_where({"branch_office": "JKT"}, None) is None  # field khusus CRM: Ascend tidak ikut
	assert _list_where({"customer_id": ["in", []]}, None) is None
	assert _list_where({"quo_no": ["is", "set"]}, None)[0] == ["ISNULL(CAST(e.QuoNo AS varchar(100)), '') <> ''"]

	assert _list_order("modified desc") == ("modified", True)
	assert _list_order("`tabCRM Estimation`.est_profit asc") == ("est_profit", False)
	assert _list_order("branch_office desc") == ("modified", True)
	print("ok")


def roundtrip(name="ASC-47692"):
	"""Buka ASC- lalu Save tanpa perubahan: isi Ascend harus sama persis (MENULIS ke Ascend:
	LastMod & DetailID berganti, isinya tidak).

		bench --site erp.localhost execute crm_cakra.integrations.test_ascend.roundtrip --kwargs "{'name': 'ASC-47692'}"
	"""
	from frappe.client import get, save

	from crm_cakra.integrations import ascend

	def snap():
		conn = ascend._connect(ascend._conf())
		try:
			h, ds = ascend._read(conn.cursor(), ascend._est_id(name))
		finally:
			conn.close()
		h = {k: v for k, v in h.items() if k not in ("LastMod", "LastModBy")}
		return h, sorted(({k: v for k, v in d.items() if k != "DetailID"} for d in ds), key=lambda d: (d["IsExpense"], str(d)))

	before = snap()
	save(get("CRM Estimation", name))
	after = snap()
	assert before == after, "isi Ascend berubah setelah Save tanpa perubahan"
	print("ok", name)
