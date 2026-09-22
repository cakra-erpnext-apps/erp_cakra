import { ref } from 'vue'
import { call, toast } from 'frappe-ui'

export const showCreateDocumentModal = ref(false)
export const createDocumentDoctype = ref('')
export const createDocumentData = ref({})
export const createDocumentCallback = ref(null)

export const showFleetLocationModal = ref(false)
export const fleetLocationProps = ref({})

export function createDocument(doctype, obj, close, callback) {
  if (doctype) {
    close?.()
    // Fleet Location punya modalnya sendiri: butuh peta untuk nge-pin koordinat,
    // dan is_route dikunci. Dicabang di sini supaya semua pemanggil createDocument
    // (Field, Grid, TableMultiselectInput) ikut tanpa diubah satu-satu.
    if (doctype === 'Fleet Location') {
      fleetLocationProps.value = {
        // Field.vue mengirim {code: <teks yang diketik>}; tanpa `code` di sini
        // teks yang barusan diketik hilang dan modalnya terbuka kosong, jadi
        // orang harus mengetik ulang nama lokasinya.
        prefill: typeof obj === 'string' ? obj : obj?.code || obj?.name || '',
        callback: callback || null,
      }
      showFleetLocationModal.value = true
      return
    }
    createDocumentDoctype.value = doctype
    createDocumentData.value = obj || {}
    createDocumentCallback.value = callback || null
    showCreateDocumentModal.value = true
  }
}

// Jalur cepat Origin/Destination: teks yang diketik di dropdown langsung jadi
// master rute begitu Enter ditekan, tanpa modal. Koordinat sengaja dibiarkan
// kosong -- yang butuh hitungan KM memakai tombol Create New (modal berpeta)
// atau melengkapi koordinatnya di master Fleet Location.
export async function createFleetLocation(value, callback) {
  const code = (value || '').trim()
  if (!code) return
  try {
    const d = await call('frappe.client.insert', {
      doc: { doctype: 'Fleet Location', code, is_route: 1 },
    })
    callback?.(d)
    toast.success(__('Lokasi {0} dibuat', [code]))
  } catch (e) {
    // Nama sama berarti lokasinya memang sudah ada (autoname field:code, jadi
    // nama dokumen = teksnya); pakai yang sudah ada, jangan menolak isian orang.
    if (String(e.exc_type || '').includes('Duplicate')) {
      callback?.({ name: code })
      return
    }
    toast.error(e.messages?.[0] || e.message || __('Gagal membuat lokasi'))
  }
}
