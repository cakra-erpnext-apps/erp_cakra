/**
 * Override kolom grid Revenue & Expense di Estimation.
 *
 * Tiga halaman memakai grid yang sama (Estimation, EstimationNew, MobileEstimation),
 * jadi aturannya ditaruh di satu tempat -- sebelumnya disalin tiga kali dan sudah
 * mulai melenceng satu sama lain.
 */
export function applyEstimationGridOverrides(doc) {
  if (!doc.fieldPropertyOverrides) doc.fieldPropertyOverrides = {}
  const ov = doc.fieldPropertyOverrides

  // Item TIDAK lagi difilter per-grid. Filternya dulu {item_category: Revenue/Expense},
  // tapi custom field Item.item_category sudah dihapus erpnext_custom (lingkup item kini
  // ditentukan Item Group) -- memfilter field yang tidak ada lagi bikin setiap pencarian
  // item gagal dengan "You do not have permission to access field: Item.item_category".
  // CRM Product cuma dipakai di Revenue; di Expense kolomnya disembunyikan.
  ov['expense_items.product_id'] = { hidden: 1 }
  // Status (Per Doc / By Qty) hanya dipakai baris Expense -- di Revenue kolomnya
  // selalu kosong dan cuma memakan lebar.
  ov['revenue_items.status'] = { hidden: 1 }

  // Kolom Item dibatasi Item Group yang diatur di ERPNext Custom Setting > Expedition
  // ("Item in Revenue/Expense always use Item Group"); daftarnya ikut boot. Kosong =
  // semua item boleh. Form desk CRM Estimation memakai daftar yang sama.
  const scopes = window.cmi_item_groups || {}
  for (const [table, scope] of [
    ['revenue_items', 'revenue'],
    ['expense_items', 'expense'],
  ]) {
    const groups = scopes[scope] || []
    ov[`${table}.type_id`] = {
      link_filters: groups.length
        ? JSON.stringify({ item_group: ['in', groups] })
        : '',
    }
  }

  // Baris baru ikut mata uang default sistem. Server memang punya jaring pengaman
  // yang sama di before_save, tapi itu baru terlihat setelah disimpan; ini supaya
  // kolomnya sudah terisi sejak barisnya muncul.
  const currency = window.sysdefaults?.currency || 'IDR'
  ov['revenue_items.currency'] = { default: currency }
  ov['expense_items.currency'] = { default: currency }
}
