import { ref } from 'vue'

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
        prefill: typeof obj === 'string' ? obj : obj?.name || '',
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
