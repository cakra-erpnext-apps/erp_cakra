<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { call, position } from '../api'
import Ikon from '../Ikon.vue'
import Peringatan from '../Peringatan.vue'
import PilihChasis from '../PilihChasis.vue'
import { poll } from '../poll'
import Rute from '../Rute.vue'
import Sibuk from '../Sibuk.vue'
import { refresh, state } from '../store'

const router = useRouter()
const jobs = ref([])
const pilihTrail = ref({})
const chasisUntuk = ref('') // nama job yang sedang memilih chasis
const busy = ref('')
const err = ref('')
const memuat = ref(true)

async function muat({ pertama = false } = {}) {
  try {
    jobs.value = await call('jobs')
    err.value = ''
    // Job yang sudah diterima tidak perlu dilihat sebagai kartu lagi -- yang
    // dibutuhkan sopir adalah langkah berikutnya. Daftar hanya ditahan selama
    // masih ada tawaran yang belum dijawab, atau kalau job jalannya lebih dari
    // satu sehingga harus dipilih dulu.
    //
    // Pengalihan ini HANYA saat pemuatan pertama: kalau ikut jalan di penyegaran
    // berkala, sopir yang sedang membaca daftar bisa terlempar ke halaman detail
    // di tengah dia menggulir.
    const diterima = jobs.value.filter((j) => j.accepted)
    if (pertama && diterima.length === 1 && diterima.length === jobs.value.length) {
      router.replace(`/jobs/${diterima[0].name}`)
    }
  } catch (e) {
    err.value = e.message
  } finally {
    memuat.value = false
  }
}

onMounted(() => muat({ pertama: true }))

// Tawaran job baru masuk tanpa sopir menyentuh apa pun, jadi daftarnya menyegarkan
// diri sendiri -- tidak perlu tombol Refresh. Ditahan selagi sopir sedang menekan
// tombol atau memilih chasis supaya pilihannya tidak tertimpa di tengah jalan.
poll(() => {
  if (busy.value || chasisUntuk.value) return
  muat()
})

async function terima(job) {
  busy.value = job.name
  err.value = ''
  try {
    const p = await position()
    await call('accept_job', { item: job.name, trail: pilihTrail.value[job.name] || null, ...(p || {}) })
    await refresh()
    // Langsung ke detail: sesudah diterima, yang dibutuhkan sopir adalah
    // langkah berikutnya, bukan daftar job yang sama sekali lagi.
    const tujuan = `/jobs/${job.name}`
    await router.push(tujuan).catch(() => {})
    // Router yang navigasinya dibatalkan diam-diam meninggalkan sopir di daftar
    // tanpa satu pun tanda. Muat ulang penuh jelek, tapi tidak pernah gagal.
    if (router.currentRoute.value.path !== tujuan) location.assign('/driver' + tujuan)
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <Sibuk v-if="busy" teks="Mengirim penerimaan job..." />
  <PilihChasis
    v-if="chasisUntuk"
    :terpilih="pilihTrail[chasisUntuk]"
    @pilih="(t) => ((pilihTrail[chasisUntuk] = t), (chasisUntuk = ''))"
    @tutup="chasisUntuk = ''"
  />

  <div class="grid gap-4">
    <Peringatan :pesan="err" />

    <div v-if="memuat" class="card grid place-items-center gap-3 py-8">
      <span
        class="h-7 w-7 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600"
      ></span>
      <p class="text-sm text-slate-400">Memuat job...</p>
    </div>

    <div v-else-if="!jobs.length" class="card grid justify-items-center gap-2 py-8 text-center">
      <span class="grid h-12 w-12 place-items-center rounded-2xl bg-slate-100 text-slate-400">
        <Ikon n="peti" class="h-6 w-6" />
      </span>
      <p class="font-semibold">Belum ada job untuk Anda</p>
      <p v-if="!state.me.siap && !state.me.on_job" class="text-sm text-slate-500">
        Absensi lalu tekan Siap Menerima Job supaya bisa menerima tugas.
      </p>
    </div>

    <div v-for="job in jobs" :key="job.name" class="card grid gap-3">
      <div class="flex items-start justify-between gap-3">
        <div class="flex min-w-0 items-center gap-2.5">
          <span class="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600">
            <Ikon n="peti" class="h-5 w-5" />
          </span>
          <span class="min-w-0">
            <span class="block truncate font-semibold">
              {{ job.container_no || job.dpo_no || job.name }}
            </span>
            <span v-if="job.customer" class="block truncate text-xs text-slate-400">
              {{ job.customer }}
            </span>
          </span>
        </div>
        <span
          class="chip"
          :class="job.accepted ? 'bg-brand-50 text-brand-700' : 'bg-brand-50 text-brand-700'"
        >
          {{ job.accepted ? 'Diterima' : 'Tawaran baru' }}
        </span>
      </div>

      <Rute :muat="job.origin_location" :bongkar="job.destination_location" />

      <div v-if="job.vehicle || job.chasis" class="flex flex-wrap gap-2">
        <span v-if="job.vehicle" class="chip bg-slate-100 text-slate-600">
          <Ikon n="truk" class="h-4 w-4" />{{ job.vehicle }}
        </span>
        <span v-if="job.chasis" class="chip bg-slate-100 text-slate-600">
          Chasis {{ job.chasis }}
        </span>
      </div>

      <button
        v-if="job.accepted"
        class="btn-ghost"
        @click="router.push(`/jobs/${job.name}`)"
      >
        Buka Detail Job
        <Ikon n="lanjut" class="h-4 w-4" />
      </button>

      <template v-else>
        <!-- Chasis wajib: menempel pada trip, bukan pada kendaraan. -->
        <button
          class="field flex items-center justify-between text-left"
          @click="chasisUntuk = job.name"
        >
          <span :class="pilihTrail[job.name] ? 'font-semibold' : 'text-slate-400'">
            {{ pilihTrail[job.name] || 'Pilih Chasis' }}
          </span>
          <Ikon n="lanjut" class="h-4 w-4 text-slate-400" />
        </button>
        <button
          class="btn-primary"
          :disabled="busy === job.name || !pilihTrail[job.name]"
          @click="terima(job)"
        >
          {{ busy === job.name ? 'Mengirim...' : 'Terima Job' }}
        </button>
      </template>
    </div>
  </div>
</template>
