<script setup>
/**
 * Satu pemilih layar penuh untuk driver dan vehicle.
 *
 * Dua daftar, satu komponen: bentuk barisnya sama (nama besar, keterangan
 * kecil, badge status), dan pencariannya sama-sama di server. Menyalinnya jadi
 * dua berkas berarti dua tempat yang harus diingat tiap kali badge atau
 * debounce-nya diubah.
 *
 * Baris ber-`boleh: 0` (dikirim server) tidak bisa dipilih, tapi tetap
 * DITAMPILKAN lengkap dengan sebabnya. Menyembunyikannya berarti mandor yang
 * mencari nama anak buahnya tidak menemukannya dan mengira daftarnya rusak;
 * yang dia butuh adalah tahu orangnya ada, dan kenapa belum bisa dipakai.
 *
 * Daftar yang tidak mengirim `boleh` (vehicle) tidak memblokir apa pun:
 * yang menolak di sana adalah validate Dispatch Order, dan menegakkannya lagi
 * di layar akan jadi aturan kedua yang diam-diam menyimpang.
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { call } from '../api'
import { tutupSaatBack } from '../back'
import Ikon from '../Ikon.vue'
import Peringatan from '../Peringatan.vue'

const props = defineProps({
  judul: { type: String, required: true },
  metode: { type: String, required: true }, // endpoint: drivers | vehicles
  terpilih: { type: String, default: '' },
  cari: { type: String, default: 'Cari' },
})
const emit = defineEmits(['pilih', 'tutup'])

const rows = ref([])
const q = ref('')
const memuat = ref(true)
const err = ref('')
const ditolak = ref(null) // baris yang diketuk tapi tidak boleh dipakai
let debounce

const GAYA = {
  Tersedia: 'bg-ok-50 text-ok-700',
  Absen: 'bg-ok-50 text-ok-700',
  Dipakai: 'bg-accent-50 text-accent-700',
  Jalan: 'bg-accent-50 text-accent-700',
  'Belum Absen': 'bg-slate-100 text-slate-500',
  Maintenance: 'bg-red-50 text-red-700',
}

async function muat() {
  memuat.value = true
  err.value = ''
  try {
    rows.value = await call(props.metode, { q: q.value.trim() })
  } catch (e) {
    err.value = e.message
  } finally {
    memuat.value = false
  }
}

function ketuk(r) {
  if (r.boleh === 0) ditolak.value = r
  else emit('pilih', r)
}

tutupSaatBack(() => (ditolak.value ? (ditolak.value = null) : emit('tutup')))
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
      <div class="font-semibold">{{ judul }}</div>
    </header>

    <div class="grid gap-3 border-b border-slate-100 p-4">
      <div class="relative">
        <Ikon n="cari" class="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input v-model="q" class="field pl-11" type="search" :placeholder="cari" />
      </div>
      <!-- Mengosongkan pilihan harus punya tombolnya sendiri: tanpa ini satu
           baris yang salah isi cuma bisa diperbaiki lewat desk. -->
      <button v-if="terpilih" class="btn-ghost" @click="emit('pilih', null)">
        <Ikon n="silang" class="h-4 w-4" />
        Kosongkan pilihan
      </button>
    </div>

    <div class="flex-1 overflow-y-auto">
      <Peringatan v-if="err" :pesan="err" class="m-4" />

      <p v-if="memuat" class="p-4 text-sm text-slate-500">Memuat...</p>
      <p v-else-if="!rows.length" class="p-4 text-sm text-slate-600">
        {{ q ? 'Tidak ada yang cocok.' : 'Belum ada data di cabang Anda.' }}
      </p>

      <button
        v-for="r in rows"
        :key="r.name"
        class="flex w-full items-center justify-between gap-3 border-b border-slate-100 px-4 py-4 text-left active:bg-slate-100"
        :class="[
          r.name === terpilih && 'bg-brand-50/60 border-l-4 border-l-brand-600',
          r.boleh === 0 && 'bg-slate-50',
        ]"
        @click="ketuk(r)"
      >
        <span class="min-w-0" :class="r.boleh === 0 && 'text-slate-400'">
          <span class="block truncate font-semibold">{{ r.label || r.name }}</span>
          <span v-if="r.ket" class="block truncate text-xs text-slate-500">{{ r.ket }}</span>
          <span v-if="r.keterangan" class="block truncate text-xs text-accent-700">
            {{ r.keterangan }}
          </span>
        </span>
        <span v-if="r.status" class="chip" :class="GAYA[r.status] || 'bg-slate-100 text-slate-600'">
          {{ r.status }}
        </span>
      </button>
    </div>

    <!-- Modal alasan: tombol yang diam tanpa penjelasan selalu berakhir jadi
         telepon ke kantor. -->
    <div
      v-if="ditolak"
      class="absolute inset-0 z-10 grid place-items-center bg-slate-900/60 p-6"
      @click.self="ditolak = null"
    >
      <div class="grid w-full gap-3 rounded-3xl bg-white p-5 shadow-2xl">
        <div class="text-lg font-semibold">{{ ditolak.label || ditolak.name }}</div>
        <span class="chip justify-self-start" :class="GAYA[ditolak.status] || 'bg-slate-100 text-slate-600'">
          {{ ditolak.status }}
        </span>
        <p class="text-sm text-slate-600">{{ ditolak.keterangan }}</p>
        <p class="text-sm text-slate-600">
          Belum bisa dipilih. Pilih yang lain, atau hubungi kantor kalau menurut Anda ini keliru.
        </p>
        <button class="btn-primary" @click="ditolak = null">Mengerti</button>
      </div>
    </div>
  </div>
</template>
