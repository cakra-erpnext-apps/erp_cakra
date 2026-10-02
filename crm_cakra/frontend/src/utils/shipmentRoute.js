import { call, toast } from 'frappe-ui'
import { watch } from 'vue'

// Tabel Shipment Route (child CRM Shipment Route) dipakai Inquiry, Quotation,
// dan Estimation. Tombol Check per baris: perkiraan Est KM & Est Days dari peta,
// AI kalau peta tidak bisa menjawab (lihat crm_cakra/api/route.py).
export async function checkRoute(row) {
  if (!row?.origin || !row?.destination) {
    toast.error(__('Isi Origin dan Destination dulu.'))
    return
  }
  // Jalur AI bisa makan ~30 detik; beri tanda supaya tombol tidak diklik ulang.
  if (row.__checking) return
  row.__checking = true
  toast.info(__('Menghitung rute...'))
  try {
    const r = await call('crm_cakra.api.route.estimate', {
      origin: row.origin,
      destination: row.destination,
      detail_address: row.detail_address,
    })
    row.est_km = r.est_km
    row.est_days = r.est_days
    toast.success(
      r.source === 'ai'
        ? __('Perkiraan AI, mohon dicek ulang')
        : __('Dihitung dari peta'),
    )
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal memperkirakan rute'))
  } finally {
    delete row.__checking
  }
}

export const routeLabel = (r) => `${r.origin} - ${r.destination}`

const uniqueJoin = (values) => [...new Set(values.filter(Boolean))].join(', ')

// Pasang tombol Check di fieldPropertyOverrides dokumen (objek useDocument).
// quotation: true -> juga Loading/Unloading gabungan live + pilihan Route di
// tabel Product + sembunyikan kolom Duration/Margin produk.
export function setupShipmentRoutes(document, { quotation = false } = {}) {
  if (!document.fieldPropertyOverrides) document.fieldPropertyOverrides = {}
  const ov = document.fieldPropertyOverrides
  ov['routes.check'] = { ...(ov['routes.check'] || {}), click: checkRoute }
  if (!quotation) return

  ov['products.duration'] = { ...(ov['products.duration'] || {}), hidden: true }
  ov['products.margin_percent'] = { ...(ov['products.margin_percent'] || {}), hidden: true }

  watch(
    () =>
      (document.doc?.routes || [])
        .filter((r) => r.origin && r.destination)
        .map(routeLabel)
        .join('|'),
    () => {
      const rows = (document.doc?.routes || []).filter((r) => r.origin && r.destination)
      const fov = document.fieldPropertyOverrides
      fov['products.route'] = {
        ...(fov['products.route'] || {}),
        // Data di doctype (pilihannya dinamis), tampil sebagai Select di grid.
        fieldtype: 'Select',
        options: [
          { label: '', value: '' },
          ...rows.map((r) => ({ label: routeLabel(r), value: routeLabel(r) })),
        ],
      }
      if (!rows.length || !document.doc) return
      document.doc.loading_route = uniqueJoin(rows.map((r) => r.origin))
      document.doc.unloading_route = uniqueJoin(rows.map((r) => r.destination))
    },
    { immediate: true },
  )
}

// Salin baris rute dokumen sumber (inquiry -> quotation) sebagai baris baru.
export async function fetchRoutes(doctype, name) {
  const src = await call('frappe.client.get', { doctype, name })
  return (src?.routes || []).map(
    ({ origin, destination, detail_address, est_km, est_days }) => ({
      origin,
      destination,
      detail_address,
      est_km,
      est_days,
      doctype: 'CRM Shipment Route',
      parentfield: 'routes',
    }),
  )
}
