import { call, toast } from 'frappe-ui'

// Buka rute Loading -> Unloading di Google Maps, tab baru.
//
// Tab dibuka SEKARANG, selagi klik user masih dihitung browser sebagai gesture.
// Menunggu URL dari server dulu berarti window.open jatuh setelah round trip
// jaringan dan diblokir tanpa bunyi -- tombolnya terlihat mati.
//
// Ongkosnya: kalau lokasinya belum di-pin, tab kosong berkelebat sebentar lalu
// ditutup; alasannya tetap terbaca lewat toast di halaman asal.
export function openGmapRoute(doc) {
  const { loading, unloading } = doc || {}
  if (!loading || !unloading) {
    toast.error(__('Isi Loading dan Unloading dulu.'))
    return
  }
  const tab = window.open('', '_blank')
  if (!tab) {
    toast.error(__('Tab baru diblokir browser. Izinkan popup untuk situs ini.'))
    return
  }
  call('erp.fleet.doctype.fleet_route.fleet_route.gmap_url', {
    origin: loading,
    destination: unloading,
  })
    .then((url) => {
      tab.location = url
    })
    .catch((e) => {
      tab.close()
      toast.error(
        e.messages?.[0] || e.message || __('Gagal membuka Google Maps'),
      )
    })
}

// Saran yang sama untuk semua kegagalan hitung jarak: mesin rute tidak punya
// jalan keluar lain, tapi user punya -- angka dari Google Maps boleh diketik.
const GMAP_HINT = __('Silakan klik Check in GMap, lalu isi KM manual.')

// Hitung jarak Loading -> Unloading dan tulis ke doc.distance_km.
//
// Dipanggil HANYA dari tombol "Get KM". Sebelumnya ini jalan otomatis tiap kali
// rute berubah, jadi angka yang sudah diketik user tertimpa diam-diam oleh mesin
// rute -- termasuk saat mesinnya menjawab 0.
//
// Kegagalan ditulis ke overrides.get_km.error supaya pesannya menetap di bawah
// tombol; toast keburu hilang sebelum alasannya selesai dibaca.
export function fetchDistance(doc, overrides) {
  const setError = (msg) => {
    if (overrides?.get_km) overrides.get_km.error = msg
  }
  setError('')

  const { loading, unloading } = doc || {}
  if (!loading || !unloading) {
    setError(__('Isi Loading dan Unloading dulu.'))
    return
  }

  return call('erp.fleet.doctype.fleet_route.fleet_route.get_distance', {
    origin: loading,
    destination: unloading,
  })
    .then((r) => {
      doc.distance_km = r?.distance_km || 0
      if (!doc.distance_km) {
        setError(`${__('Rute tidak ditemukan.')} ${GMAP_HINT}`)
      }
    })
    .catch((e) => {
      const msg = e.messages?.[0] || e.message || __('Gagal menghitung jarak rute')
      setError(`${msg} ${GMAP_HINT}`)
    })
}
