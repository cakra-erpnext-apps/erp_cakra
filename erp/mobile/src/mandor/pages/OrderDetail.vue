<script setup>
/**
 * Satu Dispatch Order utuh di layar HP: Info, Item, Route, Map.
 *
 * Urutan section-nya sengaja sama dengan form desk -- mandor dan orang kantor
 * sering membicarakan DPO yang sama lewat telepon, dan dua urutan berbeda
 * berarti "yang di bawah customer itu lho" tidak menunjuk apa pun.
 *
 * Disimpan PER ITEM, bukan satu tombol simpan untuk seluruh dokumen. Di HP
 * mandor mengisi satu baris lalu tertarik urusan lain; satu tombol besar di
 * bawah berarti isian tiga baris hilang bersamaan begitu apps tertutup. Yang
 * dikirim tetap seluruh isi baris itu, jadi tidak ada nilai setengah tersimpan.
 *
 * Semua penolakan datang dari validate Dispatch Order dan ditampilkan apa
 * adanya -- pesannya memang sudah ditulis untuk dibaca orang.
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { call } from '../../api'
import Ikon from '../../Ikon.vue'
import Kepala from '../../Kepala.vue'
import Peringatan from '../../Peringatan.vue'
import Sibuk from '../../Sibuk.vue'
import { tanggal, waktu } from '../../waktu'
import PetaDpo from '../PetaDpo.vue'
import Pilih from '../Pilih.vue'
import TripForm from '../TripForm.vue'

const route = useRoute()
const nama = route.params.name

const doc = ref(null)
const edit = ref({})
// Nama sopir untuk dibaca, terpisah dari nilai yang dikirim. Driver.name berupa
// kode ("DRV.11"); menampilkan kode di kartu berarti mandor harus mengingat
// kode seluruh anak buahnya untuk memastikan dia tidak salah pilih.
const label = ref({})
const memuat = ref(true)
const busy = ref('')
const err = ref('')
const ok = ref('')
const pilih = ref(null) // { item, field }
const trip = ref(null) // { item, trip|null, judul, awal } -- form tambah/ubah ritase

// Chasis TIDAK ada di sini: yang memilihnya sopir saat menerima job di apps
// sopir (chasis menempel pada trip, bukan pada kartu DPO). Mandor cuma melihat.
const PEMILIH = {
  driver: { metode: 'drivers', judul: 'Pilih Driver', cari: 'Cari nama sopir' },
  vehicle: { metode: 'vehicles', judul: 'Pilih Kendaraan', cari: 'Cari nopol' },
}

function pasang(d) {
  doc.value = d
  label.value = Object.fromEntries(
    d.items.filter((i) => i.driver).map((i) => [`${i.name}:driver`, i.driver_nama]),
  )
  edit.value = Object.fromEntries(
    d.items.map((i) => [
      i.name,
      {
        atd: i.atd || '',
        ata: i.ata || '',
        driver: i.driver || '',
        vehicle: i.vehicle || '',
        chasis: i.chasis || '',
      },
    ]),
  )
}

async function muat() {
  memuat.value = true
  err.value = ''
  try {
    pasang(await call('order', { name: nama }))
  } catch (e) {
    err.value = e.message
  } finally {
    memuat.value = false
  }
}

onMounted(muat)

// Field header ditulis sebagai daftar, bukan sebelas blok markup yang sama:
// menambah satu field nanti cukup satu baris di sini.
const info = computed(() => {
  const d = doc.value
  if (!d) return []
  return [
    ['Packing List', d.packing_list],
    ['Tanggal PL', tanggal(d.packing_list_date)],
    ['Customer', d.customer],
    ['Branch', d.branch],
    ['Loading', d.origin_location],
    ['Unloading', d.destination_location],
    ['ETD', waktu(d.etd)],
    ['ETA', waktu(d.eta)],
    ['ETB', waktu(d.etb)],
    ['Dibuat oleh', d.created_by_user],
    ['Dibuat', waktu(d.created_on)],
  ]
})

// Ringkasan (section Summary di desk) = kumpulan nilai item yang dihitung server
// saat validate. Ditampilkan apa adanya supaya cocok dengan yang dilihat kantor.
const ringkas = computed(() => {
  const d = doc.value
  if (!d) return []
  // Driver dan Vehicle sengaja TIDAK diringkas di sini: keduanya sudah terbaca
  // per baris di section Item, dan daftar gabungannya cuma mengulang.
  return [
    ['Nomor DPO', d.dpo_list],
    ['Customer', d.customer_list],
  ].filter(([, v]) => v)
})

// Warna titik = aturan yang sama dengan section Map di desk.
const warnaTitik = (t, i) =>
  i === 0
    ? 'bg-ok-600'
    : t.langsir
      ? 'bg-sky-500'
      : t.jenis === 'Depo'
        ? 'bg-violet-600'
        : 'bg-blue-700'

const berubah = (i) => {
  const e = edit.value[i.name]
  return (
    e.atd !== (i.atd || '') ||
    e.ata !== (i.ata || '') ||
    e.driver !== (i.driver || '') ||
    e.vehicle !== (i.vehicle || '') ||
    e.chasis !== (i.chasis || '')
  )
}

const adaBelum = computed(() => (doc.value?.items || []).some((i) => !i.assigned))
// Section Route ditampilkan kalau ada ritase ATAU ada item yang sudah di-assign
// (yang terakhir supaya tombol Tambah Trip punya tempat).
const adaTrip = computed(() =>
  (doc.value?.items || []).some((i) => i.assigned || (doc.value.trips || {})[i.name]?.length),
)

function bukaTambah(i) {
  const daftar = doc.value.trips[i.name] || []
  const akhir = daftar[daftar.length - 1]
  // Nilai awal dari ritase terakhir, bukan kosong: ritase berikutnya biasanya
  // sopir dan unit yang sama, cuma tanggalnya yang maju.
  trip.value = {
    item: i.name,
    trip: null,
    judul: `Tambah Trip - ${i.dpo_no || i.container_no}`,
    awal: akhir
      ? { ...akhir, ata: '' }
      : { driver: i.driver, driver_nama: i.driver_nama, vehicle: i.vehicle, chasis: i.chasis, atd: i.atd, ata: '' },
  }
}

const bukaUbah = (i, t) => {
  trip.value = { item: i.name, trip: t.trip, judul: `Ubah Trip ${t.trip} - ${i.dpo_no || i.container_no}`, awal: { ...t } }
}

async function simpanTrip(nilai) {
  const { item, trip: nomor } = trip.value
  busy.value = 'trip'
  err.value = ''
  ok.value = ''
  try {
    const r = nomor
      ? await call('ubah_trip', { item, trip: nomor, ...nilai })
      : await call('tambah_trip', { item, ...nilai })
    pasang(r.order)
    ok.value = nomor ? `Trip ${nomor} diperbarui.` : `Trip ${r.hasil.trip} ditambahkan.`
    trip.value = null
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = ''
  }
}

async function hapusTrip(i, t) {
  // Konfirmasi bawaan browser: menghapus ritase menggeser dasar penagihan, dan
  // satu ketukan tak sengaja di HP terlalu murah harganya. Step-nya diarsip
  // server ke history.dispatch_order_history, jadi ini bukan hilang tanpa jejak.
  if (!confirm(`Hapus Trip ${t.trip} dari ${i.dpo_no || i.container_no}?`)) return
  busy.value = 'trip'
  err.value = ''
  ok.value = ''
  try {
    pasang((await call('hapus_trip', { item: i.name, trip: t.trip })).order)
    ok.value = `Trip ${t.trip} dihapus.`
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = ''
  }
}

async function simpan(i) {
  busy.value = i.name
  err.value = ''
  ok.value = ''
  try {
    pasang(await call('simpan_item', { item: i.name, ...edit.value[i.name] }))
    ok.value = `${i.dpo_no || i.container_no || 'Item'} tersimpan.`
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = ''
  }
}

async function assign() {
  busy.value = 'assign'
  err.value = ''
  ok.value = ''
  try {
    const r = await call('assign', { name: nama })
    pasang(r.order)
    ok.value = `${r.hasil.assigned} item di-assign dan sopirnya sudah diberi tahu.`
    if (r.hasil.missing?.length) {
      ok.value += ` Belum lengkap: ${r.hasil.missing.join(', ')}.`
    }
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = ''
  }
}

function terapkan(r) {
  const { item, field } = pilih.value
  const e = edit.value[item]
  e[field] = r ? r.name : ''
  label.value[`${item}:${field}`] = r ? r.label || r.name : ''

  // Sopir yang sudah absen sekalian memilih kendaraannya di apps sopir, jadi
  // nopolnya ikut terisi begitu sopirnya dipilih. Mengetiknya lagi cuma
  // membuka jalan mandor memasangkan sopir ke unit yang bukan dia pegang.
  if (field === 'driver' && r && r.vehicle) {
    e.vehicle = r.vehicle
    label.value[`${item}:vehicle`] = r.vehicle
  }
  pilih.value = null
}

const tampil = (item, field) => label.value[`${item}:${field}`] || edit.value[item][field]
</script>

<template>
  <Sibuk v-if="busy" :teks="busy === 'assign' ? 'Meng-assign job...' : 'Menyimpan...'" />
  <TripForm
    v-if="trip"
    :judul="trip.judul"
    :awal="trip.awal"
    @simpan="simpanTrip"
    @tutup="trip = null"
  />
  <Pilih
    v-if="pilih"
    v-bind="PEMILIH[pilih.field]"
    :terpilih="edit[pilih.item][pilih.field]"
    @pilih="terapkan"
    @tutup="pilih = null"
  />

  <div class="grid gap-3">
    <Kepala :judul="nama" ke="/" />

    <Peringatan :pesan="err" />
    <Peringatan :pesan="ok" jenis="ok" />

    <div v-if="memuat" class="card grid place-items-center gap-3 py-8">
      <span
        class="h-7 w-7 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600"
      ></span>
      <p class="text-sm text-slate-400">Memuat Dispatch Order...</p>
    </div>

    <template v-else-if="doc">
      <!-- ================= INFO ================= -->
      <div class="card grid gap-3">
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm font-semibold">{{ doc.branch || 'Tanpa cabang' }}</span>
          <span class="chip bg-slate-100 text-slate-600">{{ doc.assign_progress }}</span>
        </div>

        <dl class="grid grid-cols-2 gap-x-3 gap-y-2 border-t border-slate-100 pt-3">
          <div v-for="[k, v] in info" :key="k" class="min-w-0">
            <dt class="label">{{ k }}</dt>
            <dd class="truncate text-sm">{{ v || '-' }}</dd>
          </div>
        </dl>

        <p v-if="doc.notes" class="rounded-xl bg-accent-50 p-3 text-sm text-accent-900">
          <span class="label block text-accent-700">Catatan untuk Sopir</span>
          {{ doc.notes }}
        </p>

        <dl v-if="ringkas.length" class="grid gap-2 border-t border-slate-100 pt-3">
          <div v-for="[k, v] in ringkas" :key="k">
            <dt class="label">{{ k }}</dt>
            <dd class="text-sm">{{ v }}</dd>
          </div>
        </dl>
      </div>

      <!-- ================= ITEM ================= -->
      <div class="flex items-center gap-2 pt-1">
        <span class="label">Item ({{ doc.items.length }})</span>
        <span class="h-px flex-1 bg-slate-200"></span>
      </div>

      <div v-for="i in doc.items" :key="i.name" class="card grid gap-3">
        <div class="flex items-start justify-between gap-3">
          <div class="flex min-w-0 items-center gap-2.5">
            <span
              class="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"
            >
              <Ikon n="peti" class="h-5 w-5" />
            </span>
            <span class="min-w-0">
              <span class="block truncate font-semibold">
                {{ i.container_no || i.dpo_no || 'Tanpa nomor' }}
              </span>
              <span class="block truncate text-xs text-slate-400">
                {{ i.dpo_no }}<span v-if="i.container_size"> - {{ i.container_size }}</span>
                <span v-if="i.customer"> - {{ i.customer }}</span>
              </span>
            </span>
          </div>
          <span
            class="chip shrink-0"
            :class="i.assigned ? 'bg-ok-50 text-ok-700' : 'bg-slate-100 text-slate-500'"
          >
            {{ i.assigned ? 'Assigned' : 'Belum' }}
          </span>
        </div>

        <!-- Nomor yang dikonfirmasi sopir dari lapangan. Beda dengan container_no
             dari kantor, dan bedanya itu justru yang perlu dilihat mandor. -->
        <div v-if="i.container_tms" class="rounded-xl bg-slate-50 px-3 py-2 text-sm">
          <span class="label block">Container TMS (dikonfirmasi sopir)</span>
          {{ i.container_tms }}
          <span v-if="i.container_tms_at" class="text-xs text-slate-400">
            - {{ waktu(i.container_tms_at) }}
          </span>
        </div>

        <!-- Label dan input jadi anak grid yang SAMA, bukan dua <label>
             bertumpuk sendiri-sendiri: "ATA (Selesai Bongkar)" pecah dua baris
             sementara "ATD" satu baris, dan kalau tiap kolom mengurus tingginya
             sendiri kedua input berakhir tidak sejajar.

             Dua kolom tanggal baru mungkin sesudah `:where(.grid)` di style.css
             memaksa kolom `minmax(0,1fr)`: input[type=date] punya lebar
             intrinsik ~193 px yang tidak bisa diperkecil width/min-width apa
             pun, jadi tanpa itu kartunya melar lalu terpotong. Padding
             dikecilkan (px-2) supaya isi inputnya tetap terbaca di 320 px. -->
        <div class="grid grid-cols-2 gap-x-2 gap-y-1">
          <label class="label" :for="`atd-${i.name}`">ATD</label>
          <label class="label" :for="`ata-${i.name}`">ATA (Selesai Bongkar)</label>
          <input
            :id="`atd-${i.name}`"
            v-model="edit[i.name].atd"
            type="date"
            class="field px-2 py-2.5 text-sm"
          />
          <input
            :id="`ata-${i.name}`"
            v-model="edit[i.name].ata"
            type="date"
            class="field px-2 py-2.5 text-sm"
          />
        </div>

        <!-- Driver selebar kartu: namanya paling panjang dan paling sering
             dibaca, sedangkan nopol dan chasis cukup pendek untuk berdua.

             Item yang sudah punya trip terkunci di server
             (`_lock_assigned_items`), jadi jadi baris baca-saja -- bukan tombol
             yang diketuk lalu diam. Tombol mati butuh penjelasan; baris yang
             memang bukan tombol tidak. -->
        <button
          v-if="!i.terkunci"
          class="field flex items-center justify-between py-3 text-left"
          @click="pilih = { item: i.name, field: 'driver' }"
        >
          <span class="min-w-0">
            <span class="label block">Driver</span>
            <span class="block truncate" :class="!edit[i.name].driver && 'text-slate-400'">
              {{ tampil(i.name, 'driver') || 'Belum dipilih' }}
            </span>
          </span>
          <Ikon n="lanjut" class="h-4 w-4 shrink-0 text-slate-400" />
        </button>
        <div v-else class="min-w-0 rounded-2xl bg-slate-100 px-4 py-3">
          <span class="label block">Driver</span>
          <span class="block truncate" :class="!edit[i.name].driver && 'text-slate-400'">
            {{ tampil(i.name, 'driver') || 'Belum dipilih' }}
          </span>
        </div>

        <div class="grid grid-cols-2 gap-2">
          <button
            v-if="!i.terkunci"
            class="field flex items-center justify-between gap-1 px-3 py-3 text-left"
            @click="pilih = { item: i.name, field: 'vehicle' }"
          >
            <span class="min-w-0">
              <span class="label block">Nopol</span>
              <span class="block truncate" :class="!edit[i.name].vehicle && 'text-slate-400'">
                {{ tampil(i.name, 'vehicle') || 'Belum dipilih' }}
              </span>
            </span>
            <Ikon n="lanjut" class="h-4 w-4 shrink-0 text-slate-400" />
          </button>
          <div v-else class="min-w-0 rounded-2xl bg-slate-100 px-3 py-3">
            <span class="label block">Nopol</span>
            <span class="block truncate" :class="!edit[i.name].vehicle && 'text-slate-400'">
              {{ tampil(i.name, 'vehicle') || 'Belum dipilih' }}
            </span>
          </div>

          <!-- Chasis selalu baca-saja: yang memilihnya sopir saat menerima job. -->
          <div class="min-w-0 rounded-2xl bg-slate-100 px-3 py-3">
            <span class="label block">Chasis</span>
            <span class="block truncate" :class="!edit[i.name].chasis && 'text-slate-400'">
              {{ tampil(i.name, 'chasis') || 'Belum dipilih' }}
            </span>
          </div>
        </div>

        <!-- Muncul HANYA kalau ada yang berubah. Tombol "Tersimpan" yang mati
             tidak memberi tahu apa pun dan cuma menambah tinggi tiap kartu. -->
        <button v-if="berubah(i)" class="btn-primary" :disabled="busy === i.name" @click="simpan(i)">
          <Ikon n="cek" class="h-4 w-4" />
          Simpan Baris Ini
        </button>
      </div>

      <!-- Assign menyalakan job di HP sopir, jadi ia berdiri sendiri di bawah
           semua baris, bukan berdempetan dengan tombol simpan per baris. -->
      <button
        v-if="adaBelum"
        class="btn bg-ok-600 text-white shadow-lg shadow-ok-600/25 active:bg-ok-700"
        @click="assign"
      >
        <Ikon n="truk" class="h-5 w-5" />
        Assign &amp; Kirim ke Sopir
      </button>
      <p v-else class="text-center text-sm text-slate-400">Semua item sudah di-assign.</p>

      <!-- ================= ROUTE ================= -->
      <div class="flex items-center gap-2 pt-1">
        <span class="label">Route</span>
        <span class="h-px flex-1 bg-slate-200"></span>
      </div>

      <div v-if="!doc.route.length" class="card text-sm text-slate-500">
        Titik rute belum diisi di DPO ini.
      </div>

      <div v-else class="card grid gap-2">
        <div v-for="(t, n) in doc.route" :key="t.no" class="flex items-start gap-2.5">
          <span
            class="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold text-white"
            :class="warnaTitik(t, n)"
          >
            {{ n + 1 }}
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium">{{ t.titik }}</span>
            <span class="block truncate text-xs text-slate-400">
              {{ t.jenis }}<span v-if="n === 0"> - Start</span>
              <span v-if="t.origin"> - Origin</span><span v-if="t.dest"> - Destination</span>
              <span v-if="!t.latitude && !t.longitude"> - tanpa koordinat</span>
            </span>
          </span>
          <span v-if="t.langsir" class="chip shrink-0 bg-accent-50 px-2 py-0.5 text-accent-700">
            Langsir
          </span>
        </div>
      </div>

      <!-- Ritase. Jam masuk/keluar titik DIBACA SAJA -- itu datang dari geofence
           apps sopir, dan input di sini akan jadi sumber kedua untuk angka yang
           sama. Yang bisa diubah mandor cuma sopir/nopol/tanggal ritasenya,
           lewat endpoint yang membungkus tombol Tambah/Edit/Hapus Trip di desk. -->
      <template v-if="adaTrip">
        <div v-for="i in doc.items" :key="`trip-${i.name}`" class="grid gap-2">
          <div v-for="t in doc.trips[i.name] || []" :key="t.trip" class="card grid gap-2">
            <div class="flex items-center justify-between gap-1">
              <!-- Judul cukup "Trip n": nomor DPO yang panjang mendorong
                   judulnya terpotong jadi "...- Tri", dan itu bagian yang justru
                   tidak boleh hilang. Nomornya turun ke baris keterangan. -->
              <span class="truncate text-sm font-semibold">Trip {{ t.trip }}</span>
              <!-- Ikon, bukan tombol berteks: dua tombol "Ubah"/"Hapus" berjajar
                   memakan satu baris penuh di layar 320 px, padahal kartunya
                   sudah panjang. Label tetap ada lewat aria-label. -->
              <span class="flex shrink-0 items-center">
                <button class="ikon-btn" aria-label="Ubah trip" @click="bukaUbah(i, t)">
                  <Ikon n="ubah" class="h-[1.15rem] w-[1.15rem]" />
                </button>
                <button
                  class="ikon-btn text-red-600 active:bg-red-50"
                  aria-label="Hapus trip"
                  @click="hapusTrip(i, t)"
                >
                  <Ikon n="hapus" class="h-[1.15rem] w-[1.15rem]" />
                </button>
              </span>
            </div>
            <div class="truncate text-xs text-slate-400">
              {{ i.dpo_no || i.container_no }} - {{ t.vehicle || '-' }} -
              {{ t.driver_nama || '-' }}<span v-if="t.chasis"> - Chasis {{ t.chasis }}</span>
              <span v-if="t.atd"> - ATD {{ tanggal(t.atd) }}</span>
              <span v-if="t.ata"> - ATA {{ tanggal(t.ata) }}</span>
            </div>

            <div class="grid gap-1.5 border-t border-slate-100 pt-2">
              <div
                v-for="s in t.steps"
                :key="s.step"
                class="grid grid-cols-[0.5rem_minmax(0,1fr)_auto] items-center gap-2"
              >
                <span
                  class="h-2 w-2 rounded-full"
                  :class="s.start ? 'bg-ok-600' : 'bg-slate-200'"
                ></span>
                <span class="min-w-0 truncate text-xs">
                  {{ s.point || s.step_type }}
                  <span v-if="s.point" class="text-slate-400">({{ s.step_type }})</span>
                </span>
                <span class="shrink-0 text-right text-[0.65rem] leading-tight text-slate-500">
                  <span class="block">{{ waktu(s.start) || '-' }}</span>
                  <span v-if="s.point" class="block">{{ waktu(s.end) || '-' }}</span>
                </span>
              </div>
            </div>
          </div>

          <button
            v-if="i.assigned"
            class="btn-ghost w-auto justify-self-end px-3 py-2 text-sm"
            @click="bukaTambah(i)"
          >
            <Ikon n="tambah" class="h-4 w-4" />
            Trip
          </button>
        </div>
      </template>

      <!-- ================= MAP ================= -->
      <div class="flex items-center gap-2 pt-1">
        <span class="label">Map</span>
        <span class="h-px flex-1 bg-slate-200"></span>
      </div>
      <PetaDpo :route="doc.route" :armada="doc.armada" />
      <p class="pb-2 text-center text-xs text-slate-400">
        Pin bernomor = titik rute. Ikon truk = posisi GPS terakhir unit yang mengerjakan DPO ini.
      </p>
    </template>
  </div>
</template>
