"""CMI Sales Invoice print format (Jinja HTML), created idempotently from install.py."""

CMI_SALES_INVOICE = "CMI Sales Invoice"

CMI_SALES_INVOICE_HTML = """
<div style="font-family: Arial, Helvetica, sans-serif; font-size: 11px; color:#222;">
  <table style="width:100%; border-bottom:2px solid #333; padding-bottom:6px;">
    <tr>
      <td style="vertical-align:top;">
        <div style="font-size:18px; font-weight:bold;">{{ doc.company }}</div>
        <div style="white-space:pre-line; color:#555;">{{ doc.company_address_display or "" }}</div>
      </td>
      <td style="vertical-align:top; text-align:right;">
        <div style="font-size:20px; font-weight:bold; letter-spacing:1px;">INVOICE</div>
        <div><b>No:</b> {{ doc.name }}</div>
        {% if doc.custom_tax_invoice_no %}<div><b>No. Faktur Pajak:</b> {{ doc.custom_tax_invoice_no }}</div>{% endif %}
      </td>
    </tr>
  </table>

  <table style="width:100%; margin-top:10px;">
    <tr>
      <td style="vertical-align:top; width:55%;">
        <div style="color:#777; font-size:10px;">KEPADA / BILL TO</div>
        <div style="font-weight:bold;">{{ doc.customer_name or doc.customer }}</div>
        <div style="white-space:pre-line; color:#555;">{{ doc.address_display or "" }}</div>
      </td>
      <td style="vertical-align:top;">
        <table style="width:100%;">
          <tr><td style="color:#777;">Invoice Date</td><td style="text-align:right;">{{ frappe.utils.formatdate(doc.posting_date, "dd MMM yyyy") }}</td></tr>
          <tr><td style="color:#777;">Due Date</td><td style="text-align:right;">{{ frappe.utils.formatdate(doc.due_date, "dd MMM yyyy") if doc.due_date else "-" }}</td></tr>
          {% if doc.po_no %}<tr><td style="color:#777;">PO No</td><td style="text-align:right;">{{ doc.po_no }}</td></tr>{% endif %}
          <tr><td style="color:#777;">Currency</td><td style="text-align:right;">{{ doc.currency }}</td></tr>
        </table>
      </td>
    </tr>
  </table>

  <table style="width:100%; margin-top:12px; border-collapse:collapse;">
    <thead>
      <tr style="background:#f2f2f2; border-top:1px solid #ccc; border-bottom:1px solid #ccc;">
        <th style="padding:6px; text-align:left; width:30px;">#</th>
        <th style="padding:6px; text-align:left;">Item</th>
        <th style="padding:6px; text-align:right; width:60px;">Qty</th>
        <th style="padding:6px; text-align:right; width:110px;">Price</th>
        <th style="padding:6px; text-align:right; width:120px;">Amount</th>
      </tr>
    </thead>
    <tbody>
      {% for it in doc.items %}
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:6px; vertical-align:top;">{{ loop.index }}</td>
        <td style="padding:6px; vertical-align:top;">
          <div style="font-weight:bold;">{{ it.item_code }}{% if it.item_name and it.item_name != it.item_code %} — {{ it.item_name }}{% endif %}</div>
          {% if it.custom_note %}<div style="color:#666; font-size:10px;">{{ it.custom_note }}</div>{% endif %}
          {% if it.description and it.description != it.item_name %}<div style="color:#888; font-size:10px;">{{ it.description }}</div>{% endif %}
          {% if it.custom_remark %}<div style="color:#999; font-size:10px; font-style:italic;">{{ it.custom_remark }}</div>{% endif %}
        </td>
        <td style="padding:6px; text-align:right; vertical-align:top;">{{ it.qty }}</td>
        <td style="padding:6px; text-align:right; vertical-align:top;">{{ frappe.utils.fmt_money(it.rate, currency=doc.currency) }}</td>
        <td style="padding:6px; text-align:right; vertical-align:top;">{{ frappe.utils.fmt_money(it.amount, currency=doc.currency) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <table style="width:100%; margin-top:10px;">
    <tr>
      <td style="vertical-align:top; width:55%; padding-right:10px;">
        {% if doc.remarks %}<div style="color:#777; font-size:10px;">Remark</div><div style="color:#555;">{{ doc.remarks }}</div>{% endif %}
        <div style="margin-top:10px; color:#555;"><i>Terbilang: {{ frappe.utils.money_in_words(doc.custom_grand_total or doc.grand_total, doc.currency) }}</i></div>
      </td>
      <td style="vertical-align:top;">
        <table style="width:100%;">
          <tr><td style="padding:3px; color:#555;">Subtotal</td><td style="padding:3px; text-align:right;">{{ frappe.utils.fmt_money(doc.custom_subtotal, currency=doc.currency) }}</td></tr>
          {% if doc.custom_discount_amount %}<tr><td style="padding:3px; color:#555;">Discount</td><td style="padding:3px; text-align:right;">- {{ frappe.utils.fmt_money(doc.custom_discount_amount, currency=doc.currency) }}</td></tr>{% endif %}
          {% if not doc.custom_ignore_tax and doc.custom_tax_amount %}<tr><td style="padding:3px; color:#555;">Tax (PPN)</td><td style="padding:3px; text-align:right;">{{ frappe.utils.fmt_money(doc.custom_tax_amount, currency=doc.currency) }}</td></tr>{% endif %}
          {% if doc.custom_pph23_amount %}<tr><td style="padding:3px; color:#555;">PPh 23</td><td style="padding:3px; text-align:right;">- {{ frappe.utils.fmt_money(doc.custom_pph23_amount, currency=doc.currency) }}</td></tr>{% endif %}
          {% if doc.custom_materai %}<tr><td style="padding:3px; color:#555;">Materai</td><td style="padding:3px; text-align:right;">{{ frappe.utils.fmt_money(doc.custom_materai, currency=doc.currency) }}</td></tr>{% endif %}
          <tr style="border-top:2px solid #333; font-weight:bold; font-size:13px;">
            <td style="padding:6px 3px;">GRAND TOTAL</td>
            <td style="padding:6px 3px; text-align:right;">{{ frappe.utils.fmt_money(doc.custom_grand_total or doc.grand_total, currency=doc.currency) }}</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>

  <table style="width:100%; margin-top:40px;">
    <tr>
      <td style="text-align:center; width:50%;"></td>
      <td style="text-align:center;">
        <div>Hormat kami,</div>
        <div style="height:60px;"></div>
        <div style="border-top:1px solid #333; display:inline-block; padding-top:4px; min-width:160px;">{{ doc.company }}</div>
      </td>
    </tr>
  </table>
</div>
"""
