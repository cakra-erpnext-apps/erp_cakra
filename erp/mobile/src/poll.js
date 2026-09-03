import { onBeforeUnmount, onMounted } from 'vue'

// ponytail: polling, bukan push. Sopir memegang apps yang terbuka, jadi tanpa ini
// job baru dan notifikasi baru menunggu sampai dia keluar-masuk apps dulu.
// Naikkan ke frappe.realtime (socketio) kalau jeda 45 detik masih terasa lambat.
export const JEDA = 45000

/**
 * Jalankan `fn` berkala selama apps benar-benar terlihat, dan sekali lagi tiap
 * kali sopir kembali ke apps.
 *
 * Digantung pada visibilitas, bukan interval polos: HP di saku dengan layar mati
 * tidak perlu menembak server tiap 45 detik, dan sopir yang baru membuka apps
 * tidak boleh menunggu satu putaran interval dulu untuk melihat job barunya.
 */
export function poll(fn, ms = JEDA) {
  let timer
  const kalauTerlihat = () => document.visibilityState === 'visible' && fn()

  onMounted(() => {
    timer = setInterval(kalauTerlihat, ms)
    document.addEventListener('visibilitychange', kalauTerlihat)
  })

  onBeforeUnmount(() => {
    clearInterval(timer)
    document.removeEventListener('visibilitychange', kalauTerlihat)
  })
}
