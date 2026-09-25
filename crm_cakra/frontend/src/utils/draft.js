// Isian form yang belum tersimpan dititipkan ke localStorage, supaya refresh
// (mis. setelah internet putus waktu Save) tidak menghapusnya. Kunci per user
// dan per dokumen; dibuang begitu dokumennya tersimpan atau orang menekan
// Cancel/Discard. Dokumen yang sudah ada diurus data/document.js, form "New"
// lewat startNewDoc di bawah.
import { sessionStore } from '@/stores/session'
import { popDuplicate } from '@/utils/duplicate'
import { toast } from 'frappe-ui'
import { watch, onMounted, nextTick } from 'vue'

const key = (doctype, name) =>
  `crm_draft:${sessionStore().user}:${doctype}:${name || 'new'}`

export function getDraft(doctype, name) {
  try {
    return JSON.parse(localStorage.getItem(key(doctype, name)))
  } catch {
    return null
  }
}

export function setDraft(doctype, name, value) {
  try {
    if (value) localStorage.setItem(key(doctype, name), JSON.stringify(value))
    else localStorage.removeItem(key(doctype, name))
  } catch (e) {
    // Penyimpanan penuh/diblokir browser: form tetap jalan, cuma tanpa titipan.
    console.error('[draft]', e)
  }
}

const isBlank = (v) =>
  v == null || v === '' || v === 0 || v === false || (Array.isArray(v) && !v.length)

// Form "New": doc awal = salinan Duplicate, atau titipan dari sesi sebelumnya,
// atau `blank`. Default yang dipasang halaman saat mount (tanggal hari ini,
// currency) bukan ketikan orang -- baru dititipkan kalau ada isian lain, supaya
// membuka lalu meninggalkan form kosong tidak memunculkan "draft" basi.
export function startNewDoc(document, doctype, blank) {
  const duplicate = popDuplicate(doctype)
  const restored = !duplicate && getDraft(doctype)
  document.doc = duplicate || restored || blank

  let baseline = null
  onMounted(() =>
    nextTick(() => {
      // Titipan yang dipulihkan seluruhnya dianggap isian orang.
      baseline = restored ? {} : JSON.parse(JSON.stringify(document.doc))
      if (restored) {
        toast.info(
          __('Isian yang belum tersimpan dipulihkan. Tekan Cancel untuk membuangnya.'),
        )
      }
    }),
  )

  watch(
    () => document.doc,
    (doc) => {
      if (!baseline || !doc) return
      const typed = Object.keys(doc).some(
        (k) => !isBlank(doc[k]) && JSON.stringify(doc[k]) !== JSON.stringify(baseline[k]),
      )
      setDraft(doctype, null, typed ? doc : null)
    },
    { deep: true },
  )

  // Panggil setelah insert berhasil dan saat Cancel.
  return function discard() {
    baseline = null
    setDraft(doctype, null, null)
  }
}
