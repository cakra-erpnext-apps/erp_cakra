<script setup>
/**
 * Kamera depan di dalam apps, bukan `input capture`.
 *
 * `<input type="file" capture="user">` hanya MENYARANKAN kamera -- banyak HP
 * tetap memunculkan pilihan galeri, dan foto lama bisa dikirim sebagai absensi
 * hari ini. getUserMedia tidak punya jalan ke galeri sama sekali, dan gambarnya
 * live jadi sopir tahu foto itu diambil saat itu juga.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { tutupSaatBack } from './back'

const emit = defineEmits(['ambil', 'tutup'])

const video = ref(null)
const siap = ref(false)
const err = ref('')
let stream

tutupSaatBack(() => emit('tutup'))

onMounted(async () => {
  if (!navigator.mediaDevices?.getUserMedia) {
    // getUserMedia hanya ada di origin aman. Pesannya harus menyebut sebabnya,
    // kalau tidak ini terbaca sebagai "HP saya rusak".
    err.value = window.isSecureContext
      ? 'Perangkat ini tidak punya kamera yang bisa diakses.'
      : 'Kamera butuh koneksi HTTPS. Buka apps lewat alamat https.'
    return
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    })
    video.value.srcObject = stream
    await video.value.play()
    siap.value = true
  } catch (e) {
    err.value =
      e.name === 'NotAllowedError'
        ? 'Izin kamera ditolak. Nyalakan izin kamera untuk apps ini lalu coba lagi.'
        : 'Kamera tidak bisa dibuka: ' + e.message
  }
})

// Kamera yang tidak dimatikan akan terus menyala dengan lampu indikator hidup
// walau layarnya sudah pindah. Wajib dilepas, bukan cuma disembunyikan.
onBeforeUnmount(() => stream?.getTracks().forEach((t) => t.stop()))

function ambil() {
  if (!siap.value) return
  emit('ambil', video.value)
}
</script>

<template>
  <div class="lapis flex flex-col bg-black">
    <div class="relative flex-1 overflow-hidden">
      <!-- Pratinjau dicerminkan supaya terasa seperti cermin; yang DISIMPAN
           tidak dicerminkan, agar tulisan di seragam tetap terbaca. -->
      <video ref="video" class="h-full w-full -scale-x-100 object-cover" playsinline muted></video>
      <p v-if="err" class="absolute inset-x-6 top-1/2 -translate-y-1/2 text-center text-white">
        {{ err }}
      </p>
    </div>

    <!-- Rana bundar besar di tengah, Batal di sisi kiri: bentuk kamera yang sudah
         dikenal semua orang, dan jempol sopir jatuh ke sana tanpa mencari. -->
    <div
      class="relative grid place-items-center px-5 py-6 pb-[max(1.5rem,env(safe-area-inset-bottom))]"
    >
      <button
        class="absolute left-5 top-1/2 -translate-y-1/2 px-2 py-3 text-sm font-medium text-white/70"
        @click="emit('tutup')"
      >
        Batal
      </button>
      <button
        class="grid h-[4.5rem] w-[4.5rem] place-items-center rounded-full ring-4 ring-white/40 transition active:scale-95 disabled:opacity-40"
        :disabled="!siap"
        aria-label="Ambil Foto"
        @click="ambil"
      >
        <span class="h-[3.6rem] w-[3.6rem] rounded-full bg-white"></span>
      </button>
    </div>
  </div>
</template>
