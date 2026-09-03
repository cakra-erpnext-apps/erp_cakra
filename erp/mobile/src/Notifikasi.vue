<script setup>
/**
 * Kotak notifikasi sopir. Isinya dari Notification Log bawaan Frappe.
 *
 * Notifikasi ini hanya terlihat saat apps DIBUKA. Supaya sopir tidak menunggu
 * job yang tidak pernah dia lihat, badge-nya juga disegarkan tiap kali layar
 * kembali menyala -- lihat App.vue.
 */
import { onMounted, ref } from 'vue'
import { call } from './api'
import { tutupSaatBack } from './back'
import Ikon from './Ikon.vue'
import Peringatan from './Peringatan.vue'

const emit = defineEmits(['tutup', 'terbaca'])

const rows = ref([])
const memuat = ref(true)
const err = ref('')

tutupSaatBack(() => emit('tutup'))

onMounted(async () => {
  try {
    rows.value = await call('notifications')
  } catch (e) {
    err.value = e.message
  } finally {
    memuat.value = false
  }
})

async function tandaiSemua() {
  try {
    await call('mark_read')
    rows.value = rows.value.map((r) => ({ ...r, read: 1 }))
    emit('terbaca')
  } catch (e) {
    err.value = e.message
  }
}

const waktu = (v) => {
  const d = new Date(v.replace(' ', 'T'))
  const tanggal = d.toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' })
  return `${tanggal} - ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <div class="lapis flex flex-col bg-white">
    <header class="lapis-head justify-between">
      <div class="flex min-w-0 items-center gap-3">
        <button class="ikon-btn" aria-label="Tutup" @click="emit('tutup')">
          <Ikon n="kembali" />
        </button>
        <div class="font-semibold">Notifikasi</div>
      </div>
      <button
        v-if="rows.some((r) => !r.read)"
        class="shrink-0 px-2 text-sm font-medium text-brand-600"
        @click="tandaiSemua"
      >
        Tandai dibaca
      </button>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <Peringatan v-if="err" :pesan="err" class="m-4" />

      <p v-if="memuat" class="p-4 text-sm text-slate-400">Memuat notifikasi...</p>
      <p v-else-if="!rows.length" class="p-4 text-sm text-slate-600">Belum ada notifikasi.</p>

      <div
        v-for="n in rows"
        :key="n.name"
        class="border-b border-slate-100 px-4 py-4"
        :class="!n.read && 'bg-brand-50/60'"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="font-semibold">{{ n.subject }}</div>
          <span
            v-if="!n.read"
            class="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-600"
            aria-label="Belum dibaca"
          ></span>
        </div>
        <div v-if="n.email_content" class="mt-1 whitespace-pre-line text-sm text-slate-600">{{ n.email_content }}</div>
        <div class="mt-1 text-xs text-slate-400">{{ waktu(n.creation) }}</div>
      </div>
    </div>
  </div>
</template>
