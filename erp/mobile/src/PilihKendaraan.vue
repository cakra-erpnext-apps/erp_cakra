<script setup>
/**
 * Daftar kendaraan sebagai layar penuh, bukan dropdown.
 *
 * Satu cabang bisa punya ratusan unit; `<select>` di HP menjadi gulungan panjang
 * tanpa pencarian, dan nopol yang mirip-mirip gampang salah pilih. Pencariannya
 * di server supaya yang dicari seluruh armada cabang, bukan 50 baris pertama
 * yang kebetulan sudah termuat.
 *
 * Yang tidak tersedia tetap DITAMPILKAN, tidak disembunyikan: sopir yang mencari
 * truknya dan tidak menemukannya akan mengira sistemnya salah. Yang dia butuh
 * adalah tahu truk itu ada, dan kenapa belum bisa dipakai.
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
const ditolak = ref(null) // kendaraan yang diketuk tapi tidak bisa dipakai
let debounce

const GAYA = {
  Tersedia: 'bg-brand-50 text-brand-700',
  Dipakai: 'bg-accent-50 text-accent-700',
  Maintenance: 'bg-red-50 text-red-700',
}

async function muat() {
  memuat.value = true
  err.value = ''
  try {
    rows.value = await call('vehicles', { q: q.value.trim() })
  } catch (e) {
    err.value = e.message
  } finally {
    memuat.value = false
  }
}

// Baris "terakhir Anda pakai" ditandai ORANYE, bukan hijau: badge Tersedia
// sekarang juga hijau, jadi baris hijau di antara baris hijau tidak menandai apa
// pun. Warna aksenlah yang membuat mata sopir langsung jatuh ke sana, dan ia
// menang atas abu-abu tidak-tersedia. Status sebenarnya tetap terbaca dari badge
// dan dari teksnya yang meredup.
//
// Garis tepi kiri ikut dipasang karena latar tipis saja praktis tidak terlihat
// di layar HP di bawah matahari.
const latar = (v) =>
  v.terakhir
    ? 'bg-accent-50 border-l-4 border-l-accent-500'
    : v.status !== 'Tersedia'
      ? 'bg-slate-50'
      : ''

function ketuk(v) {
  if (v.status === 'Tersedia') emit('pilih', v.name)
  else ditolak.value = v
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
      <div class="font-semibold">Pilih Kendaraan</div>
    </header>

    <div class="border-b border-slate-100 p-4">
      <div class="relative">
        <Ikon n="cari" class="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          v-model="q"
          class="field pl-11"
          type="search"
          placeholder="Cari nopol"
          autocapitalize="characters"
        />
      </div>
    </div>

    <div class="flex-1 overflow-y-auto">
      <Peringatan v-if="err" :pesan="err" class="m-4" />

      <p v-if="memuat" class="p-4 text-sm text-slate-500">Memuat kendaraan...</p>
      <p v-else-if="!rows.length" class="p-4 text-sm text-slate-600">
        {{ q ? 'Tidak ada kendaraan yang cocok.' : 'Belum ada kendaraan di cabang Anda.' }}
      </p>

      <button
        v-for="v in rows"
        :key="v.name"
        class="flex w-full items-center justify-between gap-3 border-b border-slate-100 px-4 py-4 text-left active:bg-slate-100"
        :class="latar(v)"
        @click="ketuk(v)"
      >
        <span :class="v.status !== 'Tersedia' && 'text-slate-400'">
          <span class="block font-semibold">{{ v.name }}</span>
          <!-- Alasan baris ini ada di atas ditulis, bukan dibiarkan ditebak. -->
          <span v-if="v.terakhir" class="block text-xs font-semibold text-accent-700">
            Terakhir Anda pakai
          </span>
          <span v-if="v.merk" class="block text-xs">{{ v.merk }}</span>
          <span v-if="v.oleh" class="block text-xs">Dipakai {{ v.oleh }}</span>
        </span>
        <span class="chip" :class="GAYA[v.status]">{{ v.status }}</span>
      </button>
    </div>

    <!-- Modal alasan: menjelaskan kenapa truk ini belum bisa dipakai. Tombol mati
         tanpa penjelasan akan berakhir jadi telepon ke kantor. -->
    <div
      v-if="ditolak"
      class="absolute inset-0 z-10 grid place-items-center bg-slate-900/60 p-6"
      @click.self="ditolak = null"
    >
      <div class="grid w-full gap-3 rounded-3xl bg-white p-5 shadow-2xl">
        <div class="text-lg font-semibold">{{ ditolak.name }}</div>
        <span class="chip justify-self-start" :class="GAYA[ditolak.status]">
          {{ ditolak.status }}
        </span>
        <p class="text-sm text-slate-600">{{ ditolak.keterangan }}</p>
        <p class="text-sm text-slate-600">
          Kendaraan ini belum bisa dipakai. Pilih kendaraan lain, atau hubungi kantor
          kalau menurut Anda ini keliru.
        </p>
        <button class="btn-primary" @click="ditolak = null">Mengerti</button>
      </div>
    </div>
  </div>
</template>
