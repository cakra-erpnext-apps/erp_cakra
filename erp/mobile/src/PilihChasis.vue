<script setup>
/**
 * Daftar chasis, bentuknya sama dengan pemilih kendaraan.
 *
 * ponytail: kerangkanya (overlay, kotak cari, debounce, penahan back) sengaja
 * disalin dari PilihKendaraan.vue, bukan diangkat jadi komponen bersama. Yang
 * satu punya badge status, penolakan, dan modal alasan; yang ini daftar polos.
 * Menyatukannya berarti menyeret semua itu ke sini lewat slot. Kalau muncul
 * pemilih ketiga, barulah kerangkanya diangkat.
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { call } from './api'
import { tutupSaatBack } from './back'
import Ikon from './Ikon.vue'
import Peringatan from './Peringatan.vue'

defineProps({ terpilih: { type: String, default: '' } })
const emit = defineEmits(['pilih', 'tutup'])

const rows = ref([])
const q = ref('')
const memuat = ref(true)
const err = ref('')
let debounce

tutupSaatBack(() => emit('tutup'))

async function muat() {
  memuat.value = true
  err.value = ''
  try {
    rows.value = await call('trails', { q: q.value.trim() })
  } catch (e) {
    err.value = e.message
  } finally {
    memuat.value = false
  }
}

onMounted(muat)
onBeforeUnmount(() => clearTimeout(debounce))

watch(q, () => {
  clearTimeout(debounce)
  debounce = setTimeout(muat, 350)
})
</script>

<template>
  <div class="lapis flex flex-col bg-white">
    <header class="lapis-head">
      <button class="ikon-btn" aria-label="Batal" @click="emit('tutup')">
        <Ikon n="kembali" />
      </button>
      <div class="font-semibold">Pilih Chasis</div>
    </header>

    <div class="border-b border-slate-100 p-4">
      <div class="relative">
        <Ikon n="cari" class="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          v-model="q"
          class="field pl-11"
          type="search"
          placeholder="Cari kode chasis"
          autocapitalize="characters"
        />
      </div>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <Peringatan v-if="err" :pesan="err" class="m-4" />

      <p v-if="memuat" class="p-4 text-sm text-slate-500">Memuat chasis...</p>
      <p v-else-if="!rows.length" class="p-4 text-sm text-slate-600">
        {{ q ? 'Tidak ada chasis yang cocok.' : 'Belum ada data chasis di cabang Anda. Hubungi kantor.' }}
      </p>

      <button
        v-for="t in rows"
        :key="t.name"
        class="flex w-full items-center justify-between gap-3 border-b border-slate-100 px-4 py-4 text-left active:bg-slate-100"
        :class="t.name === terpilih && 'bg-brand-100 border-l-4 border-l-brand-500'"
        @click="emit('pilih', t.name)"
      >
        <span>
          <span class="block font-semibold">{{ t.name }}</span>
          <span v-if="t.title" class="block text-xs text-slate-500">{{ t.title }}</span>
        </span>
        <span v-if="t.size" class="shrink-0 text-sm text-slate-500">{{ t.size }}</span>
      </button>
    </div>
  </div>
</template>
