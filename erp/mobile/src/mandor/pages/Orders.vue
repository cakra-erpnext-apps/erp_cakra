<script setup>
/**
 * Daftar Dispatch Order. Layar pembuka apps mandor.
 *
 * Saringan bawaannya "Belum Di-assign", bukan semua: itu yang membuat apps ini
 * ada -- mandor membukanya justru saat ada yang belum diberi sopir. DPO yang
 * sudah beres tetap bisa dilihat lewat chip Semua, jadi tidak ada yang hilang.
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { call } from '../../api'
import Ikon from '../../Ikon.vue'
import Peringatan from '../../Peringatan.vue'
import { lazy } from '../../lazy'
import { tanggalPendek } from '../../waktu'

const PAGE = 5

const router = useRouter()
const rows = ref([])
const q = ref('')
const saring = ref('belum')
const err = ref('')
const memuat = ref(true)
const habis = ref(false)

let debounce

async function muat(reset = false) {
  if (memuat.value && !reset) return
  if (habis.value && !reset) return
  memuat.value = true
  err.value = ''
  try {
    const start = reset ? 0 : rows.value.length
    const batch = await call('orders', {
      limit: PAGE,
      start,
      q: q.value.trim(),
      saring: saring.value,
    })
    rows.value = reset ? batch : rows.value.concat(batch)
    habis.value = batch.length < PAGE
  } catch (e) {
    err.value = e.message
    habis.value = true
  } finally {
    memuat.value = false
  }
}

function ulang() {
  habis.value = false
  muat(true)
}

watch(q, () => {
  clearTimeout(debounce)
  debounce = setTimeout(ulang, 350)
})
watch(saring, ulang)

const sentinel = lazy(() => muat())

onMounted(() => muat(true))
onBeforeUnmount(() => clearTimeout(debounce))
</script>

<template>
  <div class="grid gap-3">
    <div class="relative">
      <Ikon n="cari" class="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input
        v-model="q"
        class="field pl-11 pr-11"
        type="search"
        placeholder="Cari DPO, PL, customer, nopol, sopir"
      />
      <button
        v-if="q"
        class="absolute right-2 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full text-slate-400 active:bg-slate-100"
        aria-label="Hapus pencarian"
        @click="q = ''"
      >
        <Ikon n="silang" class="h-4 w-4" />
      </button>
    </div>

    <div class="flex gap-2">
      <button
        v-for="s in [
          { v: 'belum', t: 'Belum Di-assign' },
          { v: '', t: 'Semua' },
        ]"
        :key="s.v"
        class="chip"
        :class="saring === s.v ? 'bg-brand-600 text-white' : 'bg-white text-slate-600 ring-1 ring-slate-200'"
        @click="saring = s.v"
      >
        {{ s.t }}
      </button>
      <button
        class="ml-auto grid h-8 w-8 place-items-center rounded-full text-slate-400 active:bg-slate-200"
        aria-label="Muat ulang"
        @click="ulang"
      >
        <Ikon n="segar" class="h-4 w-4" />
      </button>
    </div>

    <Peringatan :pesan="err" />

    <div v-if="!rows.length && !memuat" class="card grid justify-items-center gap-2 py-8 text-center">
      <span class="grid h-12 w-12 place-items-center rounded-2xl bg-slate-100 text-slate-400">
        <Ikon n="tugas" class="h-6 w-6" />
      </span>
      <p class="font-semibold">Tidak ada Dispatch Order</p>
      <p class="text-sm text-slate-500">
        {{ q ? 'Tidak ada yang cocok dengan pencarian.' : 'Semua DPO sudah di-assign.' }}
      </p>
    </div>

    <!-- Kartu dirapatkan: rute jadi SATU baris berpanah, bukan komponen Rute
         yang bertingkat, dan ETD menempel di baris customer. Di daftar, yang
         dicari mandor cuma "DPO mana yang belum lengkap" -- detailnya sudah
         ada satu ketukan di sebelah. -->
    <div class="grid gap-2">
      <button
        v-for="r in rows"
        :key="r.name"
        class="grid gap-1 rounded-2xl bg-white p-3 text-left shadow-sm shadow-slate-900/5 ring-1 ring-slate-900/5 active:bg-slate-50"
        @click="router.push(`/dpo/${r.name}`)"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="truncate text-sm font-semibold">{{ r.name }}</span>
          <span
            class="chip shrink-0 px-2 py-0.5"
            :class="
              r.total && r.assigned === r.total
                ? 'bg-ok-50 text-ok-700'
                : 'bg-accent-50 text-accent-700'
            "
          >
            {{ r.assigned }}/{{ r.total }}
          </span>
        </div>

        <div class="truncate text-xs text-slate-400">{{ r.packing_list }}</div>

        <div class="flex items-center gap-1.5 truncate text-xs font-medium">
          <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-ok-600"></span>
          <span class="truncate">{{ r.origin_location || '-' }}</span>
          <span class="shrink-0 text-slate-300">&#10148;</span>
          <span class="truncate">{{ r.destination_location || '-' }}</span>
        </div>

        <div class="flex items-center justify-between gap-2 text-xs text-slate-500">
          <span class="truncate">{{ r.customer_list || '-' }}</span>
          <span class="shrink-0">ETD {{ tanggalPendek(r.etd) || '-' }}</span>
        </div>
      </button>
    </div>

    <div ref="sentinel" class="grid place-items-center py-2 text-sm text-slate-400">
      <span
        v-if="memuat"
        class="h-6 w-6 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600"
      ></span>
      <span v-else-if="habis && rows.length">Semua DPO sudah tampil</span>
    </div>
  </div>
</template>
