// Isian form yang belum tersimpan dititipkan ke localStorage, supaya refresh
// (mis. setelah internet putus waktu Save) tidak menghapusnya. Kunci per user
// dan per dokumen; dibuang begitu dokumennya tersimpan atau orang menekan
// Cancel/Discard. Dokumen yang sudah ada diurus data/document.js, form "New"
// lewat startNewDoc di bawah.
import { sessionStore } from '@/stores/session'
import { popDuplicate } from '@/utils/duplicate'
import { getRandom } from '@/utils'
import { call, toast } from 'frappe-ui'
import { watch, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'

// Field teks baru masuk ke doc saat `change` (keluar dari field). Tab/browser
// ditutup waktu kursor masih di field = ketikan terakhir itu belum ikut
// dititipkan. visibilitychange->hidden juga jalan saat tab/browser ditutup,
// refresh, dan HP pindah aplikasi; blur memicu `change`, watcher lalu menulis
// titipan di microtask sebelum halaman benar-benar pergi.
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') document.activeElement?.blur()
})

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
  const router = useRouter()
  // ?draft=<token>: isian yang disiapkan CRM Assistant (belum tersimpan).
  const assistantToken = router.currentRoute.value.query.draft
  const duplicate = popDuplicate(doctype)
  const restored = !duplicate && !assistantToken && getDraft(doctype)
  document.doc = duplicate || restored || blank

  let baseline = null
  onMounted(() =>
    nextTick(async () => {
      if (assistantToken) {
        await loadAssistantDraft(document, assistantToken, router)
        // Dianggap isian orang: ikut dititipkan, jadi tahan refresh walau
        // ?draft= sudah dibuang dari URL.
        baseline = {}
        return
      }
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

// Halaman New menyalin route.query ke doc (draft=<token> ikut masuk); dibuang di
// sini, URL-nya dibersihkan, lalu isian dari server dipasang. Baris child perlu
// name + __islocal seperti baris yang ditambah lewat grid.
async function loadAssistantDraft(document, token, router) {
  delete document.doc.draft
  router.replace({ query: {} })
  try {
    const { values } = await call('assistant.assistant.crm.get_draft', { token })
    Object.entries(values || {}).forEach(([k, v]) => {
      document.doc[k] = Array.isArray(v)
        ? v.map((row) => ({ ...row, name: getRandom(10), __islocal: true }))
        : v
    })
    toast.info(__('Draft dari Assistant dimuat. Periksa isinya, lalu tekan Create untuk menyimpan.'))
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Draft tidak bisa dimuat'))
  }
}
