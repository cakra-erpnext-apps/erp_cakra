<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { call, position } from '../api'
import Ikon from '../Ikon.vue'
import Kepala from '../Kepala.vue'
import Peringatan from '../Peringatan.vue'
import Rute from '../Rute.vue'
import Sibuk from '../Sibuk.vue'
import { refresh, state } from '../store'

const route = useRoute()
const router = useRouter()

const job = ref(null)
const memuat = ref(true)
const busy = ref('')
const err = ref('')
const errJenis = ref('error')
const info = ref('')
const container = ref('')

const sibuk = computed(() => busy.value !== '')
// Nomor dari kantor sering berisi "-" atau setengah jadi; yang begitu dianggap
// belum terisi, bukan sekadar berbeda. Aturannya sama persis dengan server.
const sahKontainer = (v) => /^[A-Z]{4}[0-9]{7}$/.test(String(v || '').toUpperCase().replace(/[^A-Z0-9]/g, ''))
const sudahKonfirmasi = computed(() => sahKontainer(job.value?.container_tms))
const nomorSah = computed(() => sahKontainer(container.value))
const selesai = computed(() => !!job.value?.ata)

// Sopir hanya boleh menutup job yang sudah dia terima; tombol Terima ada di
// daftar Tugas Saya, jadi di sini cukup dibaca dari langkahnya.
const sudahTerima = computed(() =>
  (job.value?.steps || []).some((s) => s.step_type === 'Accept Job' && s.start),
)

/**
 * Masker nomor kontainer ISO: 4 huruf lalu 7 angka, ditampilkan CMIO-213-312-1.
 *
 * Zona huruf hanya menerima huruf (dibesarkan sendiri) dan zona angka hanya
 * menerima angka -- sopir mengetik sambil berdiri di samping kontainer, salah
 * satu ketukan tidak boleh menggeser seluruh nomor. Strip cuma untuk mata:
 * yang dikirim ke server tetap tanpa strip supaya bisa dibandingkan apa adanya
 * dengan nomor dari kantor.
 */
function formatKontainer(v) {
  let huruf = ''
  let angka = ''
  for (const c of String(v || '').toUpperCase()) {
    if (huruf.length < 4) {
      if (c >= 'A' && c <= 'Z') huruf += c
    } else if (angka.length < 7 && c >= '0' && c <= '9') {
      angka += c
    }
  }
  return [huruf, angka.slice(0, 3), angka.slice(3, 6), angka.slice(6)].filter(Boolean).join('-')
}

function ketikKontainer(e) {
  const v = formatKontainer(e.target.value)
  container.value = v
  // Karakter yang ditolak tidak mengubah nilai, jadi Vue tidak menggambar ulang
  // input-nya dan huruf haram itu tertinggal di layar. Dihapus paksa.
  e.target.value = v
}

function pasangError(e) {
  err.value = e.message
  errJenis.value = e.jenis === 'tolak' ? 'awas' : 'error'
}

async function muat() {
  memuat.value = true
  try {
    job.value = await call('job_detail', { item: route.params.item })
    container.value = formatKontainer(job.value.container_tms || job.value.container_no)
  } catch (e) {
    pasangError(e)
  } finally {
    memuat.value = false
  }
}

async function jalankan(label, fn) {
  busy.value = label
  err.value = ''
  info.value = ''
  try {
    await fn()
    await muat()
    await refresh()
    // Kabar berhasil hilang sendiri: sopir tidak punya alasan menutupnya, dan
    // kotak hijau yang menetap ikut terbawa ke langkah berikutnya.
    if (info.value) setTimeout(() => (info.value = ''), 4000)
  } catch (e) {
    pasangError(e)
  } finally {
    busy.value = ''
  }
}

const konfirmasi = () =>
  jalankan('container', async () => {
    const p = await position()
    const r = await call('confirm_container', {
      item: job.value.name,
      container: container.value.replace(/-/g, ''),
      ...(p || {}),
    })
    info.value = r.berbeda
      ? `Nomor diralat jadi ${r.container_tms}. Nomor dari kantor tetap tersimpan.`
      : 'Nomor kontainer dikonfirmasi sesuai.'
  })

const tandai = (step_type) =>
  jalankan(step_type, async () => {
    const p = await position()
    await call('mark_step', { item: job.value.name, step_type, ...(p || {}) })
    info.value = `${step_type} tercatat.`
    // Lanjut Job berarti sopir mau langsung muat lagi. Kalau job tadi menyeberang
    // tengah malam dia belum absen hari ini, dan tanpa absen dia tidak akan
    // pernah bisa dinyatakan siap -- jadi dia diantar ke layar absen, bukan
    // dibiarkan menebak kenapa tidak ada job baru yang masuk.
    if (step_type === 'Lanjut Job' && !state.me.sudah_absen) {
      router.replace('/')
    }
  })

const jam = (v) => {
  if (!v) return null
  const d = new Date(v.replace(' ', 'T'))
  const tgl = d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short' })
  return `${tgl} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const labelLangkah = (s) =>
  s.step_type === 'Route' ? s.point || s.point_type || 'Titik rute' : s.step_type

onMounted(muat)
</script>

<template>
  <Sibuk v-if="sibuk" teks="Mengirim data..." />

  <!-- Notifikasi mengambang, bukan kotak di dalam halaman: pesannya kabar
       sesaat dan tidak boleh mendorong tata letak yang sedang dibaca sopir. -->
  <div v-if="info" class="lapis pointer-events-none flex items-start justify-center p-4">
    <p class="rounded-2xl bg-slate-900/90 px-4 py-3 text-sm text-white shadow-lg">{{ info }}</p>
  </div>

  <div v-if="memuat" class="card grid place-items-center gap-3 py-8">
    <span
      class="h-7 w-7 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600"
    ></span>
    <p class="text-sm text-slate-400">Memuat job...</p>
  </div>

  <div v-else-if="job" class="grid gap-4">
    <Kepala judul="Detail Job" ke="/jobs" />

    <Peringatan :pesan="err" :jenis="errJenis" />

    <!-- 1. Nomor kontainer: wajib dibenarkan atau diralat sopir di lapangan. -->
    <div class="card grid gap-3">
      <div class="flex items-start gap-3">
        <span class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600">
          <Ikon n="peti" />
        </span>
        <div>
          <div class="font-semibold">Nomor Kontainer / Isotank</div>
          <p class="mt-0.5 text-sm text-slate-500">
            Pastikan nomor yang tertempel di kontainer adalah benar sesuai yang dibawah ini.
            Jika berbeda, ketik dengan benar.
          </p>
        </div>
      </div>

      <input
        :value="container"
        class="field text-center text-lg font-bold tracking-widest"
        :class="nomorSah && 'border-brand-300 bg-brand-50/50 focus:border-brand-500 focus:ring-brand-500/10'"
        autocapitalize="characters"
        autocomplete="off"
        spellcheck="false"
        placeholder="CMIO-213-312-1"
        @input="ketikKontainer"
      />

      <p v-if="sudahKonfirmasi" class="flex items-center gap-1.5 text-xs text-brand-700">
        <Ikon n="cek" class="h-4 w-4" />
        Dikonfirmasi {{ jam(job.container_tms_at) }} sebagai {{ job.container_tms }}.
      </p>

      <p v-if="!nomorSah" class="text-xs text-accent-700">
        Nomor harus 4 huruf lalu 7 angka, contoh CMIO-213-312-1.
      </p>

      <button class="btn-primary" :disabled="sibuk || !nomorSah" @click="konfirmasi">
        {{ sudahKonfirmasi ? 'Perbarui Nomor' : 'Konfirmasi Nomor' }}
      </button>
    </div>

    <!-- 2. Detail job dari assigner. -->
    <div class="card grid gap-3">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="label">No DPO</div>
          <div class="font-semibold">{{ job.dpo_no || 'belum diisi' }}</div>
        </div>
        <span v-if="job.container_size" class="chip bg-slate-100 text-slate-600">
          {{ job.container_size }}
        </span>
      </div>

      <Rute :muat="job.order.origin_location" :bongkar="job.order.destination_location" />

      <div class="border-t border-slate-100 pt-3">
        <div class="label">Customer</div>
        <div class="text-sm font-medium">{{ job.order.customer || 'belum diisi' }}</div>
      </div>

      <div v-if="job.order.notes" class="rounded-xl bg-accent-50 p-3 text-sm text-accent-900">
        <div class="label mb-1 text-accent-700">Catatan dari kantor</div>
        <p class="whitespace-pre-line">{{ job.order.notes }}</p>
      </div>
    </div>

    <!-- 3. Activities: langsung dari trip_log, bukan daftar tersendiri. -->
    <div class="card grid gap-3">
      <div class="font-semibold">Aktivitas Job</div>
      <ol class="grid">
        <li
          v-for="s in job.steps"
          :key="s.name"
          class="relative flex items-baseline justify-between gap-3 border-l-2 pb-4 pl-5 last:border-transparent last:pb-0"
          :class="s.start ? 'border-brand-200' : 'border-slate-100'"
        >
          <span
            class="absolute -left-[0.3rem] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-white"
            :class="s.start ? 'bg-brand-600' : 'bg-slate-200'"
          ></span>
          <span>
            <span class="block text-sm font-semibold" :class="!s.start && 'text-slate-400'">
              {{ labelLangkah(s) }}
            </span>
            <span v-if="s.step_type === 'Route' && s.point" class="block text-xs text-slate-400">
              {{ s.point_type }}
            </span>
          </span>
          <span class="shrink-0 text-xs" :class="s.start ? 'text-slate-500' : 'text-slate-300'">
            {{ jam(s.start) || 'belum' }}
          </span>
        </li>
      </ol>
    </div>

    <!-- 4. Penutup job. -->
    <div class="card grid gap-3">
      <div class="flex items-start gap-3">
        <span
          class="grid h-10 w-10 shrink-0 place-items-center rounded-xl"
          :class="selesai ? 'bg-brand-50 text-brand-600' : 'bg-slate-100 text-slate-500'"
        >
          <Ikon n="cek" />
        </span>
        <div>
          <div class="font-semibold">Selesaikan Job</div>
          <p class="mt-0.5 text-sm text-slate-500">
            <template v-if="selesai">Job ini sudah ditutup.</template>
            <template v-else-if="!sudahTerima">Terima job ini dulu dari daftar Tugas Saya.</template>
            <template v-else-if="!sudahKonfirmasi">
              Konfirmasi nomor kontainer/isotank di atas dulu. Job tidak bisa ditutup selama
              nomornya belum dibenarkan.
            </template>
            <template v-else>
              Pilih Lanjut Job jika Anda siap menerima muatan berikutnya. Pilih Menuju Garasi
              jika Anda ingin berhenti dulu dan tidak menerima job lain.
            </template>
          </p>
        </div>
      </div>
      <template v-if="!selesai && sudahTerima && sudahKonfirmasi">
        <button class="btn-primary" :disabled="sibuk" @click="tandai('Lanjut Job')">
          Lanjut Job
        </button>
        <button class="btn-ghost" :disabled="sibuk" @click="tandai('Menuju Garasi')">
          Menuju Garasi
        </button>
      </template>
    </div>
  </div>
</template>
