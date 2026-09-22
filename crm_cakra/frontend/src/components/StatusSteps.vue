<template>
  <div v-if="steps.length" class="mb-5">
    <div class="flex w-full items-stretch gap-1">
      <!-- Dua lapis: glow dipasang di pembungkus dengan drop-shadow, bukan
           box-shadow di panahnya. clip-path ikut memotong box-shadow, jadi
           glow-nya tidak akan pernah terlihat kalau ditaruh satu lapis. -->
      <!-- flex-1 + min-w-0: tahapannya membagi lebar sama rata sampai ujung
           kanan. Tanpa min-w-0, teks panjang memaksa kotaknya melebar dan
           barisnya jadi lebih lebar dari panelnya. -->
      <div
        v-for="(step, i) in steps"
        :key="step.name"
        class="min-w-0 flex-1"
        :style="glowStyle(i, step)"
      >
        <div
          class="flex h-10 w-full items-center justify-center px-5 text-base"
          :class="i === indeksSekarang ? 'font-semibold' : 'font-medium'"
          :style="stepStyle(step, i)"
        >
          <!-- Nama status itu data, bukan kalimat. __('Submit') kebetulan punya
               terjemahan bawaan Frappe ("Validate") dan labelnya jadi salah. -->
          <span class="truncate">{{ step.name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { statusesStore } from '@/stores/statuses'

const props = defineProps({
  status: { type: String, default: '' },
  // Tahapan siap pakai: [{ name, color }], color berupa kelas teks Tailwind
  // ("text-blue-600"). Dipakai doctype yang statusnya Select biasa (CRM
  // Quotation). Dibiarkan kosong = tahapannya dibaca dari master CRM Inquiry
  // Status seperti semula.
  steps: { type: Array, default: null },
})

const { inquiryStatuses } = statusesStore()

// Warna master sudah tersimpan sebagai kelas teks Tailwind ("!text-orange-600").
// Yang dibutuhkan di sini latar belakang, dan kelas yang dirangkai saat runtime
// tidak ikut dibuat Tailwind -- jadi warnanya dipasang sebagai gaya langsung.
const HEX = {
  red: '#dc2626',
  orange: '#ea580c',
  amber: '#d97706',
  yellow: '#ca8a04',
  green: '#16a34a',
  teal: '#0d9488',
  cyan: '#0891b2',
  blue: '#2563eb',
  violet: '#7c3aed',
  purple: '#9333ea',
  pink: '#db2777',
  gray: '#6b7280',
  black: '#111827',
}
const BELUM = '#e5e7eb'
const BELUM_TEKS = '#6b7280'

function warna(step) {
  const nama = /text-([a-z]+)-/.exec(step.color || '')?.[1]
  return HEX[nama] || HEX.gray
}

// Langkahnya = status yang masih berjalan, urut posisi. Won/Lost tidak ikut
// berbaris (itu akhir cerita, bukan tahap) kecuali inquiry-nya memang sedang
// di sana -- supaya bar tetap menunjukkan keadaan sebenarnya.
const steps = computed(() => {
  if (props.steps) return props.steps

  const semua = inquiryStatuses.data || []
  const berjalan = semua.filter((s) => ['Open', 'Ongoing'].includes(s.type))
  const sekarang = semua.find((s) => s.name === props.status)
  if (sekarang && !berjalan.includes(sekarang)) return [...berjalan, sekarang]
  return berjalan
})

const indeksSekarang = computed(() =>
  steps.value.findIndex((s) => s.name === props.status),
)

// Ujung panah: yang pertama rata kiri, sisanya bertakik supaya menyambung.
function bentuk(i) {
  const t = '16px'
  return i === 0
    ? `polygon(0 0, calc(100% - ${t}) 0, 100% 50%, calc(100% - ${t}) 100%, 0 100%)`
    : `polygon(0 0, calc(100% - ${t}) 0, 100% 50%, calc(100% - ${t}) 100%, 0 100%, ${t} 50%)`
}

// Glow hanya untuk tahap yang sedang berjalan -- penanda "posisi sekarang".
function glowStyle(i, step) {
  if (i !== indeksSekarang.value) return {}
  const c = warna(step)
  return { filter: `drop-shadow(0 0 4px ${c}) drop-shadow(0 0 10px ${c})` }
}

function stepStyle(step, i) {
  const lewat = indeksSekarang.value >= 0 && i <= indeksSekarang.value
  return {
    clipPath: bentuk(i),
    backgroundColor: lewat ? warna(step) : BELUM,
    color: lewat ? '#ffffff' : BELUM_TEKS,
    // Langkah yang sudah lewat sedikit diredupkan supaya mata langsung
    // menemukan posisi sekarang.
    opacity: lewat && i < indeksSekarang.value ? 0.75 : 1,
  }
}
</script>
