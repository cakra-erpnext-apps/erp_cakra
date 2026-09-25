import frappe

NAMA = "Procurement Request"

# Ringkas dengan sengaja: yang dibutuhkan penerima cuma cukup untuk memutuskan
# membuka atau tidak. Rinciannya ada di CRM, dan tombol Check yang mengantar.
#
# Ditulis dengan tabel dan gaya inline, bukan div + kelas: Gmail dan Outlook
# membuang <style> dan tidak mengenal flex/grid, jadi tata letak yang rapi di
# browser bisa berantakan di kotak masuk.
ISI = """<div style="background:#f4f5f6;padding:24px 12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px">
    <tr>
      <td style="padding:20px 24px 16px;border-bottom:1px solid #f1f2f3">
        <div style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#6b7280">
          Request Procurement
        </div>
        <div style="margin-top:6px;font-size:18px;font-weight:600;color:#111827">
          {{ inquiry }}
        </div>
      </td>
    </tr>

    <tr>
      <td style="padding:18px 24px 4px">
        <p style="margin:0 0 16px;font-size:14px;line-height:20px;color:#374151">
          <b>{{ requester }}</b> meminta perhitungan harga untuk inquiry ini.
        </p>

        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size:14px">
          <tr>
            <td style="padding:7px 0;color:#6b7280;width:42%">No Procurement</td>
            <td style="padding:7px 0;color:#111827;font-weight:600">{{ procurement }}</td>
          </tr>
          {% if account %}<tr>
            <td style="padding:7px 0;border-top:1px solid #f3f4f6;color:#6b7280">Account</td>
            <td style="padding:7px 0;border-top:1px solid #f3f4f6;color:#111827;font-weight:600">{{ account }}</td>
          </tr>{% endif %}
          {% if route %}<tr>
            <td style="padding:7px 0;border-top:1px solid #f3f4f6;color:#6b7280">Rute</td>
            <td style="padding:7px 0;border-top:1px solid #f3f4f6;color:#111827;font-weight:600">{{ route }}</td>
          </tr>{% endif %}
          {% if inquiry_date %}<tr>
            <td style="padding:7px 0;border-top:1px solid #f3f4f6;color:#6b7280">Tanggal Inquiry</td>
            <td style="padding:7px 0;border-top:1px solid #f3f4f6;color:#111827;font-weight:600">{{ inquiry_date }}</td>
          </tr>{% endif %}
        </table>

        {% if remark %}
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:16px">
          <tr>
            <td style="padding:12px 14px;background:#f9fafb;border-left:3px solid #d1d5db;
                       font-size:14px;line-height:20px;color:#374151">
              {{ remark }}
            </td>
          </tr>
        </table>
        {% endif %}
      </td>
    </tr>

    <tr>
      <td style="padding:20px 24px 24px">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="background:#2563eb;border-radius:8px">
              <a href="{{ link }}"
                 style="display:inline-block;padding:11px 28px;font-size:14px;font-weight:600;
                        color:#ffffff;text-decoration:none">
                Check
              </a>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <tr>
      <td style="padding:14px 24px;border-top:1px solid #f1f2f3;background:#fcfcfd;
                 border-radius:0 0 12px 12px;font-size:12px;line-height:18px;color:#9ca3af">
        Tombol Check membuka dokumen procurement di CRM. Anda perlu login lebih dulu,
        dan dokumennya hanya terbuka untuk yang punya akses.
      </td>
    </tr>
  </table>
</div>
"""


def execute():
	"""Pasang template email Submit to Procurement dan tunjuk dari FCRM Settings.

	Lewat patch supaya site yang sudah berjalan ikut mendapatkannya saat migrate --
	template dan setelannya data, bukan kode, jadi tidak ikut terbawa git pull.

	Idempoten: template yang sudah ada tidak ditimpa (isinya boleh diedit user),
	dan setelannya hanya diisi kalau masih kosong.
	"""
	if not frappe.db.exists("Email Template", NAMA):
		frappe.get_doc(
			{
				"doctype": "Email Template",
				"name": NAMA,
				"enabled": 1,
				"reference_doctype": "CRM Procurement",
				"subject": "Request Procurement: {{ inquiry }}",
				"use_html": 1,
				"response_html": ISI,
			}
		).insert(ignore_permissions=True)

	if not frappe.db.get_single_value("FCRM Settings", "procurement_email_template"):
		frappe.db.set_single_value("FCRM Settings", "procurement_email_template", NAMA)

	frappe.db.commit()
