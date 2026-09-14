import { call } from 'frappe-ui'

// Cetak quotation lewat Print Format Frappe, tapi tanyakan dulu ke server apakah
// boleh (before_print: price floor, persetujuan margin, kunci status). Tanpa ini
// penolakannya muncul sebagai halaman traceback di tab baru -- tidak ada yang tahu
// harga baris mana yang salah.
//
// Mengembalikan pesan error (string HTML) kalau ditolak, null kalau tab cetak dibuka.
export async function printQuotation(name) {
  // Tab dibuka SEKARANG, selagi masih di dalam gesture klik. Kalau window.open
  // dipanggil sesudah await, browser memblokirnya tanpa bunyi.
  const tab = window.open('', '_blank')
  try {
    await call('crm_cakra.api.quotation.check_printable', { quotation: name })
  } catch (e) {
    tab?.close()
    return e.messages?.join('<br>') || e.message || __('Quotation ini tidak bisa dicetak.')
  }
  const params = new URLSearchParams({
    doctype: 'CRM Quotation',
    name,
    format: 'Quotation Print Out',
    trigger_print: '1',
  })
  if (tab) tab.location = `/printview?${params.toString()}`
  else window.open(`/printview?${params.toString()}`, '_blank')
  return null
}
