<script setup>
/**
 * Form satu ritase: dipakai untuk Tambah Trip maupun Ubah Trip.
 *
 * Satu form untuk keduanya karena isinya memang sama persis -- yang berbeda cuma
 * nilai awal dan endpoint yang dipanggil pemakainya. Dua berkas berarti dua
 * tempat yang harus diingat tiap kali ada field ritase yang bertambah.
 *
 * Pemilih driver/nopol dipasang DI DALAM form ini, bukan menumpang milik halaman
 * detail: kalau menumpang, menutup pemilih harus tahu sedang mengisi baris item
 * atau form ritase, dan salah tebak berarti nilai mendarat di baris yang salah.
 *
 * Chasis baca-saja, sama dengan di kartu item: yang memilihnya sopir saat
 * menerima job.
 */
import { ref } from 'vue'
import { tutupSaatBack } from '../back'
import Ikon from '../Ikon.vue'
import Pilih from './Pilih.vue'

const props = defineProps({
  judul: { type: String, required: true },
  awal: { type: Object, required: true },
})
const emit = defineEmits(['simpan', 'tutup'])

const PEMILIH = {
  driver: { metode: 'drivers', judul: 'Pilih Driver', cari: 'Cari nama sopir' },
  vehicle: { metode: 'vehicles', judul: 'Pilih Kendaraan', cari: 'Cari nopol' },
}

const nilai = ref({
  driver: props.awal.driver || '',
  vehicle: props.awal.vehicle || '',
  chasis: props.awal.chasis || '',
  atd: props.awal.atd || '',
  ata: props.awal.ata || '',
})
const label = ref({ driver: props.awal.driver_nama || props.awal.driver || '' })
const pilih = ref('')

function terapkan(r) {
  nilai.value[pilih.value] = r ? r.name : ''
  if (pilih.value === 'driver') {
    label.value.driver = r ? r.label || r.name : ''
    // Sopir yang sudah absen sekalian memilih kendaraannya; aturannya sama
    // dengan di kartu item supaya mandor tidak belajar dua perilaku.
    if (r && r.vehicle) nilai.value.vehicle = r.vehicle
  }
  pilih.value = ''
}

tutupSaatBack(() => (pilih.value ? (pilih.value = '') : emit('tutup')))
</script>

<template>
  <div class="lapis flex flex-col bg-white">
    <header class="lapis-head">
      <button class="ikon-btn" aria-label="Batal" @click="emit('tutup')">
        <Ikon n="kembali" />
      </button>
      <div class="font-semibold">{{ judul }}</div>
    </header>

    <div class="grid flex-1 content-start gap-3 overflow-y-auto p-4">
      <button
        class="field flex items-center justify-between py-3 text-left"
        @click="pilih = 'driver'"
      >
        <span class="min-w-0">
          <span class="label block">Driver</span>
          <span class="block truncate" :class="!nilai.driver && 'text-slate-400'">
            {{ label.driver || nilai.driver || 'Belum dipilih' }}
          </span>
        </span>
        <Ikon n="lanjut" class="h-4 w-4 shrink-0 text-slate-400" />
      </button>

      <div class="grid grid-cols-2 gap-2">
        <button
          class="field flex items-center justify-between gap-1 px-3 py-3 text-left"
          @click="pilih = 'vehicle'"
        >
          <span class="min-w-0">
            <span class="label block">Nopol</span>
            <span class="block truncate" :class="!nilai.vehicle && 'text-slate-400'">
              {{ nilai.vehicle || 'Belum dipilih' }}
            </span>
          </span>
          <Ikon n="lanjut" class="h-4 w-4 shrink-0 text-slate-400" />
        </button>

        <div class="min-w-0 rounded-2xl bg-slate-100 px-3 py-3">
          <span class="label block">Chasis</span>
          <span class="block truncate" :class="!nilai.chasis && 'text-slate-400'">
            {{ nilai.chasis || 'Belum dipilih' }}
          </span>
        </div>
      </div>

      <!-- ATD/ATA di sini milik RITASE ini, bukan baris item: nilai item
           diturunkan ulang oleh server dari seluruh ritasenya. -->
      <div class="grid grid-cols-2 gap-x-2 gap-y-1">
        <label class="label" for="trip-atd">ATD</label>
        <label class="label" for="trip-ata">ATA (Selesai Bongkar)</label>
        <input id="trip-atd" v-model="nilai.atd" type="date" class="field px-2 py-2.5 text-sm" />
        <input id="trip-ata" v-model="nilai.ata" type="date" class="field px-2 py-2.5 text-sm" />
      </div>
    </div>

    <div class="grid gap-2 border-t border-slate-100 p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
      <button class="btn-primary" :disabled="!nilai.driver || !nilai.vehicle" @click="emit('simpan', { ...nilai })">
        <Ikon n="cek" class="h-4 w-4" />
        Simpan
      </button>
      <button class="btn-ghost" @click="emit('tutup')">Batal</button>
    </div>

    <Pilih
      v-if="pilih"
      v-bind="PEMILIH[pilih]"
      :terpilih="nilai[pilih]"
      @pilih="terapkan"
      @tutup="pilih = ''"
    />
  </div>
</template>
