<script setup>
/**
 * Tirai selama data dikirim ke server.
 *
 * Menutupi seluruh layar, bukan sekadar mengubah tulisan di tombol: sopir yang
 * tidak melihat tanda apa pun akan menekan lagi, dan dua permintaan yang jalan
 * bersamaan pernah membuat dua record absensi untuk hari yang sama.
 */
defineProps({ teks: { type: String, default: 'Mengirim data...' } })
</script>

<template>
  <div class="lapis grid place-items-center bg-slate-900/60 p-6 backdrop-blur-sm">
    <div class="grid justify-items-center gap-3 rounded-3xl bg-white px-8 py-7 shadow-2xl">
      <span
        class="h-9 w-9 animate-spin rounded-full border-4 border-brand-100 border-t-brand-600"
      ></span>
      <p class="text-sm font-medium">{{ teks }}</p>
      <p class="text-xs text-slate-500">Jangan tutup apps dulu.</p>
    </div>
  </div>
</template>
