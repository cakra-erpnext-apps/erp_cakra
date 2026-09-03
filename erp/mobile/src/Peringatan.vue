<script setup>
/**
 * Satu bentuk untuk semua peringatan di apps.
 *
 * Sebelumnya kotak merah yang sama disalin di empat file, jadi tiap kali
 * warnanya atau bentuknya diubah selalu ada satu yang ketinggalan.
 */
defineProps({
  pesan: { type: String, default: '' },
  // error: gagal, sopir tidak bisa lanjut. awas: ditolak aturan, bisa diperbaiki
  // sopir sendiri. info: kabar. ok: berhasil.
  jenis: { type: String, default: 'error' },
})

// Garis tebal di tepi kiri, bukan cuma latar pucat: di layar HP di bawah
// matahari latar -50 praktis putih dan peringatannya tidak terlihat sama sekali.
const GAYA = {
  error: 'bg-red-50 text-red-700 border-red-500',
  awas: 'bg-accent-50 text-accent-800 border-accent-500',
  info: 'bg-slate-100 text-slate-700 border-slate-400',
  ok: 'bg-ok-50 text-ok-800 border-ok-500',
}
</script>

<template>
  <p
    v-if="pesan"
    class="rounded-xl border-l-4 p-3 text-sm font-medium"
    :class="GAYA[jenis] || GAYA.error"
  >
    {{ pesan }}
  </p>
</template>
