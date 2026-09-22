import { describe, expect, it, vi } from 'vitest'

// vitest jalan tanpa plugin vue, jadi ikon .vue yang di-import lists.js dipalsukan.
// vi.mock di-hoist, jadi pemanggilannya harus literal (tidak boleh dalam loop).
vi.mock('@/components/Icons/LeadsIcon.vue', () => ({ default: {} }))
vi.mock('@/components/Icons/InquiriesIcon.vue', () => ({ default: {} }))
vi.mock('@/components/Icons/QuotationIcon.vue', () => ({ default: {} }))
vi.mock('@/components/Icons/MeetingIcon.vue', () => ({ default: {} }))
vi.mock('@/components/Icons/ContactsIcon.vue', () => ({ default: {} }))
vi.mock('@/components/Icons/OrganizationsIcon.vue', () => ({ default: {} }))

const { lists } = await import('@/mobile/lists')

// Kolom yang dibaca title/subtitle/badge TAPI tidak ikut diminta ke server akan
// selalu undefined -- kartu kosong tanpa satu pun error. Proxy ini mencatat
// kolom apa saja yang benar-benar dibaca lalu membandingkannya dengan cfg.fields.
function spyRow() {
  const read = new Set()
  const row = new Proxy(
    {},
    {
      get(_target, key) {
        if (typeof key !== 'string') return undefined
        read.add(key)
        return key === 'name' ? 'DOC-1' : `v-${key}`
      },
    },
  )
  return { row, read }
}

const statuses = {
  getLeadStatus: () => ({ color: 'text-ink-gray-5' }),
  getInquiryStatus: () => ({ color: 'text-ink-gray-5' }),
}

describe('mobile list config', () => {
  for (const [key, cfg] of Object.entries(lists)) {
    it(`${key}: hanya membaca kolom yang diminta ke server`, () => {
      const { row, read } = spyRow()
      cfg.title(row)
      cfg.subtitle(row)
      cfg.badge?.(row, statuses)
      if (cfg.dateField) row[cfg.dateField]

      expect([...read].filter((f) => !cfg.fields.includes(f))).toEqual([])
    })

    it(`${key}: punya cara membuka baris`, () => {
      const { row } = spyRow()
      // Tanpa route, baris HARUS punya modal -- kalau tidak, kartunya mati saat disentuh.
      if (cfg.route) {
        const to = cfg.route(row)
        expect(Object.values(to.params)).toEqual(['DOC-1'])
      } else {
        expect(cfg.modal).toBeTruthy()
      }
    })
  }
})
