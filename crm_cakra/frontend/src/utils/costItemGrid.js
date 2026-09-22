/**
 * Batasi pilihan Item di tabel Cost Component ke Item Group yang diatur di
 * ERPNext Custom Setting > Expedition ("Item in Expense always use Item Group") --
 * setting yang sama dengan grid Expense di Estimation. Kosong = semua item boleh.
 *
 * Daftarnya ikut boot, jadi tidak perlu watch resource settings seperti versi
 * sebelumnya (dulu FCRM Settings.use_items_group, satu group saja).
 */
export function applyItemGroupFilter(doc, key = 'items.item_name') {
  const groups = (window.cmi_item_groups || {}).expense || []
  if (!doc.fieldPropertyOverrides) doc.fieldPropertyOverrides = {}
  doc.fieldPropertyOverrides[key] = {
    ...(doc.fieldPropertyOverrides[key] || {}),
    link_filters: groups.length
      ? JSON.stringify({ item_group: ['in', groups] })
      : '',
  }
}
