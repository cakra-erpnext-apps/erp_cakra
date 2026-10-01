// Menu CRM per grup (config desk "CRM Menu Access"). window.crm_menus datang dari
// boot: null = semua menu, selain itu daftar kunci menu yang boleh tampil.
// Tiap baris: [kunci menu, route desktop, list mobile?]. Kunci = fieldname di
// CRM Menu Access Group. Hanya menyaring menu; izin data tetap di server.
const MENUS = [
  ['assistant', 'Assistant'],
  ['dashboard', 'Dashboard'],
  ['leads', 'Leads', 'leads'],
  ['inquiries', 'Inquiries', 'inquiries'],
  ['quotations', 'Quotations', 'quotations'],
  ['procurement', 'Procurement', 'procurement'],
  ['estimations', 'Estimations', 'estimations'],
  ['tenders', 'Tenders', 'tenders'],
  ['accounts', 'Organizations', 'accounts'],
  ['contacts', 'Contacts', 'contacts'],
  ['cost_types', 'CostTypes'],
  ['cost_components', 'CostComponents'],
  ['products', 'Products'],
  ['locations', 'Locations'],
  ['notes', 'Notes', 'notes'],
  ['tasks', 'Tasks', 'tasks'],
  ['meetings', 'Meetings', 'meetings'],
  ['calendar', 'MeetingsCalendar'],
  ['call_logs', 'Call Logs'],
]

// name = nama route desktop atau nama list mobile. Yang bukan menu selalu boleh.
export function menuAllowed(name) {
  const allowed = window.crm_menus
  const menu = MENUS.find((m) => m[1] === name || m[2] === name)
  return !allowed || !menu || allowed.includes(menu[0])
}

export function firstAllowedRoute() {
  return MENUS.find((m) => menuAllowed(m[1]))?.[1]
}
