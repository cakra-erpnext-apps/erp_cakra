import { call, position } from './api'

/**
 * Setoran posisi berkala selama sopir bertugas.
 *
 * ponytail: versi web ini hanya jalan selama app di layar -- setInterval mati
 * begitu HP terkunci. Itu cukup untuk uji coba dan untuk admin yang buka lewat
 * browser, TIDAK cukup untuk sopir di jalan. Upgrade-nya di shell Capacitor:
 * @capacitor-community/background-geolocation dengan foreground service, lalu
 * fungsi ini tinggal dipanggil dari callback plugin, bukan dari timer.
 */
let timer = null
let busy = false

export function start(minutes) {
  stop()
  const ms = Math.max(1, Number(minutes) || 60) * 60000
  tick()
  timer = setInterval(tick, ms)
  document.addEventListener('visibilitychange', onVisible)
}

export function stop() {
  if (timer) clearInterval(timer)
  timer = null
  document.removeEventListener('visibilitychange', onVisible)
}

// Layar kembali menyala setelah lama terkunci: kirim satu titik supaya jeda
// tidak terbaca sebagai sopir hilang lebih lama dari sebenarnya.
function onVisible() {
  if (document.visibilityState === 'visible') tick()
}

async function tick() {
  if (busy) return
  busy = true
  try {
    const p = await position()
    if (p) await call('ping', p)
  } catch {
    // Titik yang gagal kirim sekarang hilang. Server tetap melihatnya sebagai
    // sopir sunyi lewat silent_drivers(), jadi tidak lolos diam-diam.
  } finally {
    busy = false
  }
}
