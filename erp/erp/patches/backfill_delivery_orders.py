"""Buat Delivery Order untuk Packing List open yang sudah ada sebelum fitur DO."""

import frappe

from erp.fleet.doctype.delivery_order.delivery_order import sync_from_packing_list


def execute():
    for name in frappe.get_all("Packing List", filters={"void": 0, "closed": 0}, pluck="name"):
        sync_from_packing_list(frappe.get_doc("Packing List", name))
