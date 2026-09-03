/**
 * Satu pintu ke backend, dan satu tempat semua kegagalan diterjemahkan.
 *
 * Token CSRF diambil sekali setelah login lewat GET (metode aman, tidak kena cek
 * CSRF) supaya dev-server dan produksi berperilaku sama.
 */
let csrf = ''

// Modul backend yang dilayani bundel ini. Satu berkas api dipakai dua apps
// (sopir dan mandor) yang endpoint-nya beda modul, jadi awalannya diganti sekali
// saat apps start -- bukan disalin jadi dua api.js yang lalu menyimpang.
let ns = 'erp.fleet.api.mobile_driver'
export const setNs = (v) => (ns = v)

/** Kegagalan yang sudah punya sebab, bukan sekadar teks error. */
export class AppError extends Error {
  constructor(pesan, jenis) {
    super(pesan)
    this.jenis = jenis // offline | server | auth | tolak
  }
}

/** Dipanggil tiap kali keadaan koneksi ketahuan, diisi oleh store. */
let lapor = () => {}
export const setPelaporKoneksi = (fn) => (lapor = fn)

/**
 * Batas waktu satu permintaan.
 *
 * `fetch` TIDAK punya batas waktu bawaan. Kalau server menerima sambungan tapi
 * tidak pernah menjawab -- worker menggantung, antrean penuh, jaringan pelabuhan
 * yang setengah hidup -- promise-nya tidak pernah selesai. Dari sisi sopir itu
 * terlihat sebagai tirai "Memuat..." yang tidak berujung, bukan sebagai error.
 * Longgar (45 detik) karena absensi mengunggah foto lewat sinyal yang buruk.
 */
const REQUEST_TIMEOUT = 45000

async function request(path, { method = 'POST', body } = {}) {
  let res
  const batal = new AbortController()
  const jam = setTimeout(() => batal.abort(), REQUEST_TIMEOUT)
  try {
    res = await fetch(path, {
      method,
      headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrf },
      body: body ? JSON.stringify(body) : undefined,
      signal: batal.signal,
    })
  } catch (e) {
    if (e.name === 'AbortError') {
      lapor({ online: navigator.onLine, server: false })
      throw new AppError(
        'Server tidak menjawab. Periksa sinyal lalu coba lagi',
        'server',
      )
    }
    // fetch yang melempar berarti permintaannya tidak pernah sampai. Browser tidak
    // bisa membedakan "HP tanpa sinyal" dari "server mati" -- yang pasti hanya
    // navigator.onLine saat bernilai false. Sisanya ditanyakan ke server.
    if (!navigator.onLine) {
      lapor({ online: false, server: false })
      throw new AppError('Internet anda bermasalah, Silahkan coba lagi', 'offline')
    }
    const hidup = await serverHidup()
    lapor({ online: true, server: hidup })
    throw new AppError(
      hidup
        ? 'Koneksi terputus di tengah jalan. Silahkan coba lagi'
        : 'Server tidak bisa dihubungi. Silahkan coba lagi sebentar',
      'server',
    )
  } finally {
    clearTimeout(jam)
  }

  lapor({ online: true, server: true })

  const data = await res.json().catch(() => ({}))
  if (res.ok) return data.message

  const pesan = pesanServer(data)
  // 403 ikut dihitung auth: sesi yang habis membuat permintaan berjalan sebagai
  // Guest, dan endpoint ber-whitelist menolak Guest dengan PermissionError --
  // bukan 401. Tanpa ini sesi kedaluwarsa terbaca sebagai "permintaan ditolak"
  // dan sopir tinggal di layar yang tidak akan pernah memuat apa-apa.
  if (
    res.status === 401 ||
    res.status === 403 ||
    ['AuthenticationError', 'PermissionError', 'SessionExpired'].includes(data.exc_type)
  ) {
    throw new AppError(terjemahAuth(pesan, data), 'auth')
  }
  // Server hidup dan menjawab: ini aturan bisnis yang ditolak, bukan masalah
  // jaringan. Pesannya sudah dalam bahasa sopir, dipakai apa adanya.
  throw new AppError(pesan || 'Permintaan ditolak server', 'tolak')
}

function pesanServer(data) {
  try {
    const msgs = JSON.parse(data._server_messages || '[]')
    if (msgs.length) return JSON.parse(msgs[0]).message
  } catch {
    // pesan server tidak terbaca; jatuh ke bawah
  }
  return data.message || data.exception || ''
}

// Pesan Frappe apa adanya berbahasa Inggris dan menyebut istilah sistem ("User
// disabled or missing"). Sopir membacanya di HP tanpa siapa pun di sampingnya,
// jadi tiap sebab diberi kalimat yang memberitahu dia harus berbuat apa.
function terjemahAuth(pesan, data = {}) {
  // Sesi yang mati di tengah jalan hampir selalu berarti akunnya dipakai masuk di
  // HP lain -- satu akun sopir cuma boleh hidup di satu HP (hook `on_login`).
  // Pesan aslinya "Login to access... is not whitelisted", yang tidak menjelaskan
  // apa pun ke sopir.
  if (data.session_expired) {
    return 'Sesi anda berakhir. Akun ini dipakai masuk di perangkat lain, Silahkan login lagi'
  }
  if (/disabled|missing/i.test(pesan)) {
    return 'Akun anda sudah tidak aktif, Silahkan hubungi administrator'
  }
  if (/invalid login|incorrect|incomplete/i.test(pesan)) {
    return 'User atau password anda salah, Silahkan coba lagi'
  }
  return pesan || 'Login gagal'
}

/** Server menjawab atau tidak. Dipakai untuk memisahkan sinyal dari server mati. */
export async function serverHidup() {
  // Batasnya pendek dan berdiri sendiri: fungsi ini dipanggil DARI penanganan
  // error. Kalau ia ikut menggantung, penanganan errornya sendiri yang macet dan
  // sopir tetap melihat tirai tanpa ujung -- persis hal yang mau dihindari.
  const batal = new AbortController()
  const jam = setTimeout(() => batal.abort(), 5000)
  try {
    const r = await fetch('/api/method/ping', { cache: 'no-store', signal: batal.signal })
    return r.ok
  } catch {
    return false
  } finally {
    clearTimeout(jam)
  }
}

export async function loadCsrf() {
  csrf = await request('/api/method/' + ns + '.csrf', { method: 'GET' })
}

export async function login(usr, pwd) {
  await request('/api/method/login', { body: { usr, pwd } })
  await loadCsrf()
}

export async function logout() {
  await request('/api/method/logout')
  csrf = ''
}

export const call = (method, args) =>
  request('/api/method/' + ns + '.' + method, { body: args || {} })

/**
 * Posisi sekarang; null kalau ditolak/timeout -- laporan tetap boleh dikirim.
 *
 * Punya batas waktu SENDIRI di atas batas bawaan. Opsi `timeout` milik
 * getCurrentPosition hanya membatasi pencarian sinyal; kalau izin lokasi ditutup
 * tanpa dijawab, atau origin-nya bukan HTTPS, ada versi Chrome yang tidak
 * memanggil callback sukses maupun gagal. Promise-nya lalu tidak pernah selesai
 * dan tirai "Mengirim data..." menutupi layar selamanya -- dari sisi sopir itu
 * terlihat persis seperti tombol yang rusak.
 */
const GPS_TIMEOUT = 8000

export const position = () =>
  new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null)

    let selesai = false
    const beres = (v) => {
      if (selesai) return
      selesai = true
      resolve(v)
    }

    const pengaman = setTimeout(() => beres(null), GPS_TIMEOUT + 2000)
    const tutup = (v) => {
      clearTimeout(pengaman)
      beres(v)
    }

    navigator.geolocation.getCurrentPosition(
      (p) => tutup({ latitude: p.coords.latitude, longitude: p.coords.longitude }),
      () => tutup(null),
      { enableHighAccuracy: true, timeout: GPS_TIMEOUT },
    )
  })
