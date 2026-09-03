import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * Infinite scroll: pasang ref yang dikembalikan di elemen paling bawah daftar.
 *
 * Daftar di apps ini panjangnya ratusan baris (armada, sopir, DPO) dan dibuka
 * di HP lapangan -- memuat semuanya sekaligus terasa berat sebelum satu baris
 * pun terbaca. Semua daftar memakai potongan awal kecil lalu menambah sendiri
 * saat digulir; pencarian tetap menjangkau seluruh data.
 */
export function lazy(muatLagi) {
  const sentinel = ref(null)
  let observer

  onMounted(() => {
    // rootMargin: mulai memuat sebelum sentinelnya benar-benar terlihat, supaya
    // gulirannya tidak pernah berhenti di layar kosong.
    observer = new IntersectionObserver((e) => e[0].isIntersecting && muatLagi(), {
      rootMargin: '200px',
    })
    if (sentinel.value) observer.observe(sentinel.value)
  })

  onBeforeUnmount(() => observer && observer.disconnect())

  return sentinel
}
