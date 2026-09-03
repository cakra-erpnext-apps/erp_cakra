<script setup>
/**
 * Ikon garis, digambar sendiri.
 *
 * ponytail: peta jalur SVG, bukan paket ikon. Yang dipakai apps ini belasan
 * bentuk; satu dependensi ikon berisi ribuan dan ikut ke dalam bundel yang
 * diunduh sopir lewat kuota sendiri. Kalau daftarnya lewat ~30, baru pindah ke
 * paket ikon.
 */
defineProps({ n: { type: String, required: true } })

const P = {
  riwayat: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7.5V12l3 2',
  tugas: 'M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01',
  kamera: 'M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1M12 16.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7',
  lonceng: 'M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8M13.7 21a2 2 0 0 1-3.4 0',
  orang: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8',
  kembali: 'M19 12H5M12 19l-7-7 7-7',
  cari: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16M21 21l-4.3-4.3',
  truk: 'M3 7.5h11v9H3zM14 10.5h4l3 3v3h-7M7.5 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4M17.5 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4',
  peti: 'M3 8l9-5 9 5v8l-9 5-9-5zM3 8l9 5 9-5M12 13v9',
  pin: 'M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11M12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5',
  lanjut: 'M9 18l6-6-6-6',
  cek: 'M20 6L9 17l-5-5',
  silang: 'M18 6L6 18M6 6l12 12',
  keluar: 'M15 17l5-5-5-5M20 12H9M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h7',
  hadiah: 'M20 12v9H4v-9M2 7h20v5H2zM12 21V7M12 7H7.5a2.5 2.5 0 1 1 0-5C11 2 12 7 12 7M12 7h4.5a2.5 2.5 0 1 0 0-5C13 2 12 7 12 7',
  ubah: 'M4 20h4L18.5 9.5a2.12 2.12 0 0 0-3-3L5 17v3M13.5 6.5l4 4',
  hapus: 'M4 7h16M10 4h4M6.5 7l.9 13h9.2l.9-13M10 11v5.5M14 11v5.5',
  tambah: 'M12 5v14M5 12h14',
  peta: 'M9 4L3 6.5v13.5L9 17.5m0-13.5l6 2.5m-6-2.5v13.5m6-11v13.5m0-13.5L21 4v13.5L15 20.5m0 0l-6-3',
  kalender: 'M8 2v4M16 2v4M3.5 9.5h17M5 4.5h14a1.5 1.5 0 0 1 1.5 1.5v14a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 20V6A1.5 1.5 0 0 1 5 4.5',
  segar: 'M20.5 12a8.5 8.5 0 1 1-2.6-6.1M20 4v5h-5',
  slip: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 13h6M9 17h4',
}
</script>

<template>
  <svg
    class="h-5 w-5 shrink-0"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="P[n]" />
  </svg>
</template>
