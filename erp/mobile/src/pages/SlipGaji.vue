<script setup>
import { onMounted, ref } from 'vue'
import { call } from '../api'
import Ikon from '../Ikon.vue'
import Kepala from '../Kepala.vue'
import Peringatan from '../Peringatan.vue'

const rows = ref([])
const err = ref('')
const memuat = ref(true)
// Slip yang sedang dibuka. Rinciannya sudah ikut terangkut dari server, jadi
// membuka baris tidak memanggil server lagi.
const buka = ref('')

onMounted(async () => {
  try {
    rows.value = await call('slipgaji')
  } catch (e) {
    err.value = e.message
  } finally {
    memuat.value = false
  }
})

const rupiah = (v) =>
  'Rp ' + Number(v || 0).toLocaleString('id-ID', { maximumFractionDigits: 0 })
</script>

<template>
  <div class="grid gap-4">
    <Kepala judul="Slip Gaji" ke="/profil" />

    <Peringatan :pesan="err" />

    <div v-if="memuat" class="card grid place-items-center gap-3 py-8">
      <span class="h-7 w-7 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600"></span>
      <p class="text-sm text-slate-400">Memuat...</p>
    </div>
    <div v-else-if="!rows.length" class="card grid justify-items-center gap-2 py-8 text-center">
      <span class="grid h-12 w-12 place-items-center rounded-2xl bg-slate-100 text-slate-400">
        <Ikon n="slip" class="h-6 w-6" />
      </span>
      <p class="text-sm text-slate-500">Belum ada slip gaji.</p>
    </div>

    <div v-for="r in rows" :key="r.name" class="card grid gap-2">
      <button
        class="flex items-start justify-between gap-3 text-left"
        @click="buka = buka === r.name ? '' : r.name"
      >
        <div class="min-w-0">
          <div class="font-semibold">{{ r.periode }}</div>
          <div class="text-xs text-slate-400">{{ r.name }}</div>
        </div>
        <div class="shrink-0 text-right">
          <div class="font-semibold">{{ rupiah(r.gaji_bersih) }}</div>
          <div class="text-xs font-medium text-brand-600">
            {{ buka === r.name ? 'Tutup' : 'Rincian' }}
          </div>
        </div>
      </button>

      <div v-if="buka === r.name" class="grid gap-1 border-t border-slate-100 pt-2 text-sm">
        <div
          v-for="(i, n) in r.items"
          :key="n"
          class="flex items-start justify-between gap-3"
        >
          <div class="min-w-0">
            <div :class="i.type === 'Potongan' ? 'text-rose-700' : 'text-slate-700'">
              {{ i.component }}
            </div>
            <div v-if="i.note" class="text-xs text-slate-400">{{ i.note }}</div>
          </div>
          <div class="shrink-0" :class="i.type === 'Potongan' ? 'text-rose-700' : 'text-slate-700'">
            {{ i.type === 'Potongan' ? '-' : '' }}{{ rupiah(i.amount) }}
          </div>
        </div>

        <div class="mt-1 flex justify-between border-t border-slate-100 pt-2 text-slate-500">
          <span>Total Pendapatan</span><span>{{ rupiah(r.total_pendapatan) }}</span>
        </div>
        <div class="flex justify-between text-slate-500">
          <span>Total Potongan</span><span>-{{ rupiah(r.total_potongan) }}</span>
        </div>
        <div class="flex justify-between font-semibold">
          <span>Gaji Bersih</span><span>{{ rupiah(r.gaji_bersih) }}</span>
        </div>
        <div v-if="r.note" class="pt-1 text-slate-600">{{ r.note }}</div>
      </div>
    </div>
  </div>
</template>
