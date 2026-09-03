import { reactive } from 'vue'
import { call, loadCsrf, logout, serverHidup, setPelaporKoneksi } from './api'
import { stop } from './tracker'

export const state = reactive({
  ready: false, // sudah selesai memeriksa sesi
  me: null, // null = belum login
  // Sebab terakhir sesi ditolak server. Layar login memakainya supaya sopir tahu
  // bedanya "akun tidak aktif" dari "belum tertaut ke Driver" -- dulu keduanya
  // dijawab satu kalimat tebakan yang sering salah.
  alasanAuth: '',
  error: '', // error yang tidak tertangkap, ditampilkan di layar
})

export const koneksi = reactive({
  online: navigator.onLine,
  server: true,
})

/**
 * Keadaan koneksi disimpulkan dari permintaan yang benar-benar terjadi, bukan
 * dari polling berkala -- HP sopir hidup seharian dan setiap ketukan jaringan
 * memakan baterai. Satu-satunya pemeriksaan tambahan terjadi saat sinyal baru
 * kembali, karena saat itu memang perlu tahu servernya ikut hidup atau tidak.
 */
export function pantauKoneksi() {
  setPelaporKoneksi((k) => Object.assign(koneksi, k))

  window.addEventListener('offline', () => Object.assign(koneksi, { online: false, server: false }))
  window.addEventListener('online', async () => {
    koneksi.online = true
    koneksi.server = await serverHidup()
  })
}

export const pesanKoneksi = () => {
  if (!koneksi.online) return 'Internet anda bermasalah, Silahkan coba lagi'
  if (!koneksi.server) return 'Server tidak bisa dihubungi. Silahkan coba lagi sebentar'
  return ''
}

/**
 * Apps ini dipakai di HP sopir; tidak ada yang bisa membuka devtools di sana.
 * Error yang cuma masuk console = tombol yang "tidak merespon" dan tidak ada
 * satu pun petunjuk. Jadi semuanya dimunculkan ke layar.
 */
export function catchAll(app) {
  const tampilkan = (e) => (state.error = String((e && e.message) || e))
  app.config.errorHandler = tampilkan
  window.addEventListener('error', (e) => tampilkan(e.error || e.message))
  window.addEventListener('unhandledrejection', (e) => tampilkan(e.reason))
}

export async function refresh() {
  try {
    await loadCsrf()
    state.me = await call('me')
  } catch (e) {
    // HANYA kegagalan auth yang melempar sopir ke layar login. Dulu semua error
    // selain jaringan mengosongkan state.me, jadi satu error 500 sesaat atau satu
    // aturan yang menolak sudah cukup membuat sopir "ter-logout" padahal sesinya
    // masih hidup -- itulah keluar-masuk yang bikin dia login berulang kali.
    if (e.jenis === 'auth') {
      state.me = null
      state.alasanAuth = e.message
    } else {
      state.error = e.message
    }
  } finally {
    state.ready = true
  }
}

/** Keluar: tracking dimatikan dulu, sesi server dibuang, lalu keadaan lokal. */
export async function keluar() {
  stop()
  await logout().catch(() => {})
  state.me = null
}
