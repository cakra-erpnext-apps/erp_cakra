// Helper duplicate dokumen (Quotation/Inquiry) TANPA langsung simpan:
// data sumber disalin ke sessionStorage, lalu halaman "New" mengambilnya untuk
// mengisi form. Nomor baru & save hanya terjadi saat user klik Save.

const KEY = (dt) => `crm_dup_${dt}`

// Field identitas/workflow yang tidak boleh diwariskan ke dokumen baru.
const BASE_STRIP = [
  'name', 'creation', 'modified', 'owner', 'modified_by', 'docstatus', 'idx',
  '__islocal', '__unsaved', '__last_sync_on', '__onload', '__run_link_triggers',
  '_assign', '_comments', '_liked_by', '_user_tags', '_seen',
  'state', 'is_void', 'void_reason', 'void_at', 'void_by',
]
const CHILD_STRIP = [
  'name', 'creation', 'modified', 'owner', 'modified_by', 'parent',
  'parentfield', 'parenttype', 'docstatus', 'idx', '__islocal', '__unsaved',
]

export function stashDuplicate(doctype, srcDoc, extraStrip = []) {
  const doc = JSON.parse(JSON.stringify(srcDoc || {}))
  ;[...BASE_STRIP, ...extraStrip].forEach((k) => delete doc[k])
  // Bersihkan tiap child table (array of object) agar disimpan sebagai baris baru.
  Object.keys(doc).forEach((k) => {
    if (Array.isArray(doc[k])) {
      doc[k].forEach((row) => {
        if (row && typeof row === 'object') CHILD_STRIP.forEach((c) => delete row[c])
      })
    }
  })
  doc.doctype = doctype
  doc.__newDocument = true
  sessionStorage.setItem(KEY(doctype), JSON.stringify(doc))
}

export function popDuplicate(doctype) {
  const raw = sessionStorage.getItem(KEY(doctype))
  if (!raw) return null
  sessionStorage.removeItem(KEY(doctype))
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}
