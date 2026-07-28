<template>
  <LayoutHeader>
    <template #left-header>
      <div class="flex items-center gap-2">
        <Button variant="ghost" icon="arrow-left" @click="$router.push({ name: 'Meetings' })" />
        <span class="font-semibold">{{ __('Absen Meeting') }}</span>
      </div>
    </template>
    <template #right-header>
      <Button :label="__('Refresh')" iconLeft="refresh-cw" @click="meetingsList.reload()" />
    </template>
  </LayoutHeader>

  <div class="mx-auto w-full max-w-2xl p-4 space-y-3">
    <div v-if="!meetings.length" class="py-16 text-center text-ink-gray-5">
      {{ __('Tidak ada meeting untuk kamu.') }}
    </div>

    <div v-for="m in meetings" :key="m.name" class="rounded-lg border border-outline-gray-2 p-4 space-y-3">
      <div class="flex items-start justify-between gap-2">
        <div>
          <div class="flex items-center gap-2 font-medium text-ink-gray-9">
            <span
              v-if="needsAction(m)"
              class="inline-block h-2 w-2 shrink-0 rounded-full bg-red-500"
              :title="__('Absen belum lengkap')"
            />
            {{ m.subject }}
          </div>
          <div class="text-sm text-ink-gray-6">{{ m.location || '—' }}</div>
          <div class="text-xs text-ink-gray-5">{{ fmt(m.meeting_date) }}</div>
        </div>
        <Badge :theme="statusTheme(m.status)" :label="m.status" variant="subtle" size="md" />
      </div>

      <!-- Titik absen (read-only) -->
      <MiniMap v-if="m.checkin_latitude" :lat="m.checkin_latitude" :lng="m.checkin_longitude"
        height="180px" />

      <div class="grid grid-cols-2 gap-3 text-xs text-ink-gray-6">
        <div>
          <div class="uppercase tracking-wide text-ink-gray-4">Check-In</div>
          <div>{{ m.checkin_time ? fmt(m.checkin_time) : '—' }}</div>
          <div v-if="m.checkin_latitude" class="text-ink-gray-4">
            {{ m.checkin_latitude.toFixed(5) }}, {{ m.checkin_longitude.toFixed(5) }}
          </div>
        </div>
        <div>
          <div class="uppercase tracking-wide text-ink-gray-4">Check-Out</div>
          <div>{{ m.checkout_time ? fmt(m.checkout_time) : '—' }}</div>
          <div v-if="m.checkout_latitude" class="text-ink-gray-4">
            {{ m.checkout_latitude.toFixed(5) }}, {{ m.checkout_longitude.toFixed(5) }}
          </div>
        </div>
      </div>

      <div class="flex gap-2 pt-1">
        <Button variant="solid" :label="__('Check In')" :disabled="!!m.checkin_time" class="flex-1"
          @click="openPicker(m, 'in')" />
        <Button :label="__('Check Out')" :disabled="!m.checkin_time || !!m.checkout_time" class="flex-1"
          @click="openPicker(m, 'out')" />
      </div>
    </div>
  </div>

  <!-- Dialog absen: peta buat set/geser titik -->
  <Dialog v-model="showPicker" :options="{ title: picker ? `Absen: ${picker.subject}` : 'Absen' }">
    <template #body-content>
      <div class="space-y-3">
        <p class="text-sm text-ink-gray-6">
          {{ locating ? __('Mengambil lokasi…') : __('Geser marker atau ketuk peta untuk menandai lokasi.') }}
        </p>
        <p v-if="geoError" class="rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {{ geoError }} — {{ __('tandai manual di peta.') }}
        </p>
        <MiniMap v-if="showPicker" :lat="picker?.lat" :lng="picker?.lng" editable height="320px"
          @update="onMapUpdate" />
        <p class="text-xs text-ink-gray-5">
          {{ picker?.lat != null ? `${picker.lat.toFixed(6)}, ${picker.lng.toFixed(6)}` : __('Belum ada titik') }}
        </p>
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="showPicker = false" />
        <Button variant="solid" :label="picker?.kind === 'in' ? __('Check In') : __('Check Out')"
          :loading="saving" :disabled="picker?.lat == null" @click="confirmCheck" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import MiniMap from '@/components/MiniMap.vue'
import { Button, Badge, Dialog, createResource } from 'frappe-ui'
import { sessionStore } from '@/stores/session'
import { formatDate } from '@/utils'
import { ref, computed } from 'vue'

const { user } = sessionStore()
const geoError = ref('')
const locating = ref(false)
const saving = ref(false)
const showPicker = ref(false)
const picker = ref(null) // { name, subject, kind: 'in'|'out', lat, lng }

const meetingsList = createResource({
  url: 'frappe.client.get_list',
  makeParams: () => ({
    doctype: 'CRM Meeting',
    or_filters: { marketing: user, owner: user },
    fields: [
      'name', 'subject', 'location', 'status', 'marketing', 'meeting_date', 'meeting_from', 'meeting_to',
      'checkin_time', 'checkin_latitude', 'checkin_longitude',
      'checkout_time', 'checkout_latitude', 'checkout_longitude',
    ],
    order_by: 'meeting_from desc',
    limit_page_length: 50,
  }),
  auto: true,
})
// Absen belum lengkap tampil paling atas + bertanda merah (selaras tab Meetings).
const needsAction = (m) =>
  m.status !== 'Cancelled' && (!m.checkin_time || !m.checkout_time)

const meetings = computed(() => {
  const rows = [...(meetingsList.data || [])]
  return rows.sort(
    (a, b) =>
      needsAction(b) - needsAction(a) ||
      new Date(b.meeting_date || 0) - new Date(a.meeting_date || 0),
  )
})

function fmt(dt) {
  return dt ? formatDate(dt, '', true, true) : '—'
}
function statusTheme(s) {
  return { Scheduled: 'blue', Visited: 'green', Cancelled: 'red' }[s] || 'gray'
}

function getPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error('Browser tidak mendukung GPS'))
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve(pos.coords),
      (err) => reject(new Error(err.message || 'Gagal ambil lokasi')),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    )
  })
}

// Buka dialog + coba GPS. Kalau GPS gagal, dialog tetap terbuka supaya bisa tandai manual.
async function openPicker(m, kind) {
  geoError.value = ''
  picker.value = { name: m.name, subject: m.subject, kind, lat: null, lng: null }
  showPicker.value = true
  locating.value = true
  try {
    const c = await getPosition()
    picker.value = { ...picker.value, lat: c.latitude, lng: c.longitude }
  } catch (e) {
    geoError.value = e.message
  } finally {
    locating.value = false
  }
}

function onMapUpdate({ lat, lng }) {
  if (picker.value) picker.value = { ...picker.value, lat, lng }
}

async function confirmCheck() {
  if (!picker.value || picker.value.lat == null) return
  saving.value = true
  try {
    const method = picker.value.kind === 'in' ? 'check_in' : 'check_out'
    await createResource({
      url: `crm_cakra.fcrm.doctype.crm_meeting.crm_meeting.${method}`,
      params: { meeting: picker.value.name, latitude: picker.value.lat, longitude: picker.value.lng },
    }).fetch()
    showPicker.value = false
    meetingsList.reload()
  } catch (e) {
    geoError.value = e.messages?.[0] || e.message || 'Gagal simpan absen'
  } finally {
    saving.value = false
  }
}
</script>
