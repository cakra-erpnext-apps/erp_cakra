// Kontak yang menempel di satu dokumen (§2 dan §4 Alur CRM). Lead dan Inquiry memakai
// child table yang sama, jadi pengambilan datanya juga satu.
//
// Resource-nya disimpan per dokumen: tombol tambah di kepala panel dan daftar kontak di
// badannya adalah dua komponen, dan keduanya harus melihat daftar yang SAMA -- kalau
// masing-masing membuat resource sendiri, menambah kontak hanya menyegarkan salah satunya.
import { call, createResource, toast } from 'frappe-ui'

const CONTACT_ROLES = [
  '',
  'Decision Maker',
  'Influencer',
  'Finance',
  'Procurement',
  'Operational',
]

const store = new Map()

const API = 'crm_cakra.fcrm.doctype.crm_contacts.crm_contacts.'

export function useContacts(doctype, docname) {
  const key = `${doctype}:${docname}`
  if (store.has(key)) return store.get(key)

  const contacts = createResource({
    url: API + 'get_linked_contacts',
    params: { doctype, name: docname },
    cache: ['linked_contacts', doctype, docname],
    auto: true,
    transform: (data) => {
      data.forEach((contact) => (contact.opened = false))
      return data
    },
  })

  async function run(method, args, message) {
    const ok = await call(API + method, { doctype, name: docname, ...args })
    if (ok) {
      await contacts.reload()
      if (message) toast.success(message)
    }
    return ok
  }

  const api = {
    contacts,
    CONTACT_ROLES,
    addContact: (contact) => {
      if (contacts.data?.find((c) => c.name === contact)) {
        toast.error(__('Contact Already Added'))
        return
      }
      return run('add_contact', { contact }, __('Contact Added'))
    },
    removeContact: (contact) =>
      run('remove_contact', { contact }, __('Contact Removed')),
    setPrimaryContact: (contact) =>
      run('set_primary_contact', { contact }, __('Primary Contact Set')),
    setContactRole: (contact, role) =>
      run('set_contact_role', { contact, role }),
  }

  store.set(key, api)
  return api
}
