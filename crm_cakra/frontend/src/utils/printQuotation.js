import { call } from 'frappe-ui'

// Cetak quotation lewat Print Format Frappe, tapi tanyakan dulu ke server apakah
// boleh (before_print: price floor, persetujuan margin, kunci status). Tanpa ini
// penolakannya muncul sebagai halaman traceback di tab baru -- tidak ada yang tahu
// harga baris mana yang salah.
//
// Mengembalikan { error, state }: `error` pesan HTML kalau ditolak, dan `state`
// status quotation SESUDAH server menaikkannya -- menekan Print berarti penawaran
// beredar ke customer, jadi Inquired/Follow Up naik ke Negotiation. Statusnya
// dipakai apa adanya oleh pemanggil; aturannya tidak boleh dihitung ulang di layar.
//
// `before` (opsional) jalan sesudah tab dibuka: tempat menyimpan perubahan yang
// belum di-Save (server mencetak isi DB). Balik `false` = batal, tab ditutup,
// hasilnya { cancelled: true }.
export async function printQuotation(name, before) {
  // Tab dibuka SEKARANG, selagi masih di dalam gesture klik. Kalau window.open
  // dipanggil sesudah await, browser memblokirnya tanpa bunyi.
  const tab = window.open('', '_blank')
  let state
  try {
    if (before && (await before()) === false) {
      tab?.close()
      return { cancelled: true }
    }
    const res = await call('crm_cakra.api.quotation.check_printable', { quotation: name })
    state = res?.state || null
  } catch (e) {
    tab?.close()
    return {
      error: e.messages?.join('<br>') || e.message || __('Quotation ini tidak bisa dicetak.'),
    }
  }
  const params = new URLSearchParams({
    doctype: 'CRM Quotation',
    name,
    format: 'Quotation Print Out',
    trigger_print: '1',
  })
  if (tab) tab.location = `/printview?${params.toString()}`
  else window.open(`/printview?${params.toString()}`, '_blank')
  return { state }
}
