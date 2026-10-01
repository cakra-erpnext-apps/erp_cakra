import unittest

from crm_cakra.patches.v1_0.tender_quotations_and_totals import quotation_layout, tender_layout


class TestTenderQuotationsPatch(unittest.TestCase):
	def test_tender_layout(self):
		layout = [{"label": "Client", "columns": [{"fields": ["issue_date", "inquiry", "quotation"]}]}]
		tender_layout(layout)
		tender_layout(layout)  # patch boleh jalan dua kali
		self.assertEqual(layout[0]["columns"][0]["fields"], ["issue_date", "document_date", "inquiry"])

	def test_quotation_layout(self):
		layout = [
			{
				"sections": [
					{"columns": [{"fields": ["inquiry"]}]},
					{"columns": [{"fields": ["products", "net_total"]}]},
				]
			}
		]
		quotation_layout(layout)
		quotation_layout(layout)
		sections = layout[0]["sections"]
		self.assertEqual(sections[0]["columns"][0]["fields"], ["inquiry", "tender"])
		self.assertEqual(sections[1]["columns"][0]["fields"], ["products"])
		self.assertEqual(
			[c["fields"][0] for c in sections[2]["columns"]], ["net_total", "estimation_costing", "margin"]
		)
		self.assertEqual(len(sections), 3)
