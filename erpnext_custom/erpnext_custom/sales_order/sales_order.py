from erpnext_custom.selling_amounts import compute_display, inject


def before_validate(doc, method=None):
	_sync_remark(doc)
	inject(doc)


def validate(doc, method=None):
	compute_display(doc)


def _sync_remark(doc):
	if doc.get("custom_remark"):
		doc.remarks = doc.custom_remark
	elif doc.get("remarks"):
		doc.custom_remark = doc.remarks
