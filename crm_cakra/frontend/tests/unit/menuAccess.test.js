import { afterEach, describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { menuAllowed, firstAllowedRoute } from '@/utils/menuAccess'

afterEach(() => {
  delete window.crm_menus
})

describe('menuAccess', () => {
  it('tanpa grup (null) semua menu tampil', () => {
    window.crm_menus = null
    expect(menuAllowed('Leads')).toBe(true)
    expect(firstAllowedRoute()).toBe('Assistant')
  })

  it('grup menyaring route desktop dan list mobile', () => {
    window.crm_menus = ['quotations', 'accounts']
    expect(menuAllowed('Quotations')).toBe(true)
    expect(menuAllowed('Organizations')).toBe(true)
    expect(menuAllowed('accounts')).toBe(true)
    expect(menuAllowed('Leads')).toBe(false)
    expect(menuAllowed('leads')).toBe(false)
    expect(menuAllowed('Dashboard')).toBe(false)
    expect(firstAllowedRoute()).toBe('Quotations')
  })

  it('halaman yang bukan menu selalu boleh', () => {
    window.crm_menus = []
    expect(menuAllowed('Quotation')).toBe(true)
    expect(menuAllowed('ManualBook')).toBe(true)
    expect(firstAllowedRoute()).toBeUndefined()
  })

  it('kunci menu sama dengan MENUS di server', () => {
    // cwd vitest = folder frontend
    const py = readFileSync('../crm_cakra/fcrm/doctype/crm_menu_access/crm_menu_access.py', 'utf8')
    const serverKeys = py.match(/MENUS = \(([\s\S]*?)\)/)[1].match(/"(\w+)"/g).map((k) => k.slice(1, -1))
    // Tiap kunci server harus membuka minimal satu route; kalau salah ketik, menu itu tak pernah tampil.
    for (const key of serverKeys) {
      window.crm_menus = [key]
      expect(firstAllowedRoute(), key).toBeDefined()
    }
  })
})
