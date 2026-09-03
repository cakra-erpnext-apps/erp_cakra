<script setup>
import { onMounted, ref } from 'vue'
import { call } from '../api'
import Ikon from '../Ikon.vue'
import Kepala from '../Kepala.vue'
import Peringatan from '../Peringatan.vue'

const rows = ref([])
const total = ref(0)
const err = ref('')
const memuat = ref(true)

onMounted(async () => {
  try {
    const r = await call('rewards')
    rows.value = r.rows
    total.value = r.total
  } catch (e) {
    err.value = e.message
  } finally {
    memuat.value = false
  }
})

const rupiah = (v) =>
  'Rp ' + Number(v || 0).toLocaleString('id-ID', { maximumFractionDigits: 0 })

const tanggal = (v) =>
  v ? new Date(v).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : '-'
</script>

<template>
  <div class="grid gap-4">
    <Kepala judul="Reward" ke="/profil" />

    <Peringatan :pesan="err" />

    <div class="hero rounded-2xl p-4 shadow-lg shadow-brand-700/20">
      <div class="flex items-center gap-2 text-[0.7rem] font-semibold uppercase tracking-wider text-white/70">
        <Ikon n="hadiah" class="h-4 w-4" />
        Total Reward
      </div>
      <div class="mt-1 text-2xl font-bold">{{ rupiah(total) }}</div>
    </div>

    <div v-if="memuat" class="card grid place-items-center gap-3 py-8">
      <span class="h-7 w-7 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600"></span>
      <p class="text-sm text-slate-400">Memuat...</p>
    </div>
    <div v-else-if="!rows.length" class="card grid justify-items-center gap-2 py-8 text-center">
      <span class="grid h-12 w-12 place-items-center rounded-2xl bg-slate-100 text-slate-400">
        <Ikon n="hadiah" class="h-6 w-6" />
      </span>
      <p class="text-sm text-slate-500">Belum ada reward.</p>
    </div>

    <div v-for="r in rows" :key="r.name" class="card grid gap-1.5">
      <div class="flex items-start justify-between gap-3">
        <div class="font-semibold">{{ r.reward_type }}</div>
        <div class="shrink-0 font-semibold text-brand-700">{{ rupiah(r.amount) }}</div>
      </div>
      <div class="text-xs text-slate-400">{{ tanggal(r.reward_date) }}</div>
      <div v-if="r.note" class="text-sm text-slate-600">{{ r.note }}</div>
    </div>
  </div>
</template>
