import { onBeforeUnmount, onMounted } from 'vue'

/**
 * Tombol back Android menutup layar bertumpuk, bukan meninggalkan halaman.
 *
 * Tanpa ini sopir yang menekan back mengira dia membatalkan kamera atau pemilih
 * kendaraan, dan yang terjadi malah keluar dari layar absen tanpa penjelasan.
 * Sudah pernah terjadi, dan datanya jadi tidak jelas terkirim atau tidak.
 */
export function tutupSaatBack(tutup) {
  let entriSendiri = false

  const onPop = () => {
    entriSendiri = false
    tutup()
  }

  onMounted(() => {
    history.pushState({ overlay: 1 }, '')
    entriSendiri = true
    window.addEventListener('popstate', onPop)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('popstate', onPop)
    // Ditutup lewat tombol Batal, bukan back: entri riwayat tadi harus dibuang
    // supaya back berikutnya tidak sekadar "membatalkan" layar yang sudah tutup.
    //
    // Hanya kalau entri itu MASIH yang teratas. Kalau sesudah overlay ditutup
    // apps sempat pindah halaman (mis. terima job lalu buka detailnya),
    // history.back() di sini menarik sopir balik ke halaman sebelumnya dan
    // perpindahan tadi terlihat seperti tombol yang tidak berfungsi.
    if (entriSendiri && history.state && history.state.overlay) history.back()
  })
}
