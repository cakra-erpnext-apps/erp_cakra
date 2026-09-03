<script setup>
/**
 * Kepala halaman dalam: tombol kembali + judul.
 *
 * Tombol kembalinya sengaja tombol bundar bergaris, bukan tautan teks kecil:
 * halaman ini tidak punya tab di nav bawah, jadi ini SATU-SATUNYA jalan keluar
 * dan harus terlihat seperti tombol dari jarak lengan.
 */
import { useRouter } from 'vue-router'
import Ikon from './Ikon.vue'

defineProps({
  judul: { type: String, default: '' },
  // Tujuan tetap, dipakai kalau halaman ini bisa dibuka dari notifikasi atau
  // tautan langsung -- history.back() di tab baru tidak ke mana-mana.
  ke: { type: String, default: '' },
})

const router = useRouter()
</script>

<template>
  <div class="flex items-center gap-3">
    <button
      class="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-sm active:bg-slate-100"
      aria-label="Kembali"
      @click="ke ? router.push(ke) : router.back()"
    >
      <Ikon n="kembali" />
    </button>
    <div class="truncate text-lg font-semibold">{{ judul }}</div>
  </div>
</template>
