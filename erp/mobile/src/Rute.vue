<script setup>
/**
 * Muat -> bongkar sebagai garis, bukan dua baris tabel.
 *
 * Dipakai di daftar job, detail job, dan riwayat. Bentuk yang sama di tiga
 * tempat itu justru gunanya: sopir mengenali "ini rutenya" tanpa membaca label.
 */
defineProps({
  muat: { type: String, default: '' },
  bongkar: { type: String, default: '' },
})
</script>

<template>
  <div class="grid grid-cols-[0.75rem_1fr] gap-x-3">
    <!-- Titik dan garis di kolom sendiri: kalau nama lokasinya jadi dua baris,
         garisnya ikut memanjang sendiri tanpa dihitung. -->
    <span class="mt-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-brand-100 bg-brand-600"></span>
    <span class="text-sm font-medium">{{ muat || 'belum diisi' }}</span>

    <span class="mx-auto my-1 w-0.5 flex-1 bg-slate-200" style="min-height: 0.75rem"></span>
    <span></span>

    <span class="mt-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-brand-100 bg-brand-600"></span>
    <span class="text-sm font-medium">{{ bongkar || 'belum diisi' }}</span>
  </div>
</template>
