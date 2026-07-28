<template>
  <div class="px-3 pb-3 sm:px-10 sm:pb-5">
    <div class="flex items-center justify-between py-3">
      <div class="text-base text-ink-gray-5">
        {{ meetings.length ? __('{0} meeting', [meetings.length]) : '' }}
      </div>
      <Button
        variant="solid"
        :label="__('New Meeting')"
        iconLeft="plus"
        @click="startCreate"
      />
    </div>

    <!-- Form create inline (bukan modal) -->
    <div
      v-if="creating"
      class="mb-4 rounded-lg border border-outline-gray-2 p-4"
    >
      <MeetingForm v-model="createForm" />
      <div class="mt-4 flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="creating = false" />
        <Button
          variant="solid"
          :label="__('Save')"
          :loading="insertDoc.loading"
          @click="saveNew"
        />
      </div>
    </div>

    <div
      v-if="!meetings.length && !creating"
      class="py-16 text-center text-ink-gray-5"
    >
      {{ __('Belum ada meeting untuk dokumen ini.') }}
    </div>

    <div
      v-for="m in meetings"
      :key="m.name"
      class="mb-3 rounded-lg border border-outline-gray-2"
    >
      <!-- Baris ringkas: klik untuk buka/tutup detail -->
      <div
        class="flex cursor-pointer items-start justify-between gap-2 p-4"
        @click="toggle(m.name)"
      >
        <div>
          <div class="flex items-center gap-2 font-medium text-ink-gray-9">
            <span
              v-if="needsAction(m)"
              class="inline-block h-2 w-2 shrink-0 rounded-full bg-red-500"
              :title="__('Absen belum lengkap')"
            />
            {{ m.subject }}
          </div>
          <div class="text-sm text-ink-gray-6">
            {{ getUser(m.marketing).full_name || m.marketing || '—' }} - {{ m.location || '—' }}
          </div>
          <div class="text-xs text-ink-gray-5">
            {{ fmt(m.meeting_date) }}
            <template v-if="m.meeting_from">
              | {{ fmt(m.meeting_from) }} - {{ fmt(m.meeting_to) }}
            </template>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <Badge
            :theme="statusTheme(m.status)"
            :label="m.status"
            variant="subtle"
            size="md"
          />
          <FeatherIcon
            :name="expanded == m.name ? 'chevron-up' : 'chevron-down'"
            class="h-4 w-4 text-ink-gray-5"
          />
        </div>
      </div>

      <!-- Detail inline: form edit + absen, satu halaman -->
      <div v-if="expanded == m.name" class="space-y-4 border-t border-outline-gray-2 p-4">
        <MeetingForm v-if="editForm" v-model="editForm" />

        <MiniMap
          v-if="m.checkin_latitude"
          :lat="m.checkin_latitude"
          :lng="m.checkin_longitude"
          height="180px"
        />
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

        <div class="flex items-center gap-2">
          <Button
            variant="solid"
            :label="__('Check In')"
            :disabled="!!m.checkin_time"
            class="flex-1"
            @click="openPicker(m, 'in')"
          />
          <Button
            :label="__('Check Out')"
            :disabled="!m.checkin_time || !!m.checkout_time"
            class="flex-1"
            @click="openPicker(m, 'out')"
          />
          <Button
            variant="subtle"
            :label="__('Save')"
            :loading="updateDoc.loading"
            @click="saveEdit(m.name)"
          />
        </div>
      </div>
    </div>

    <!-- Dialog kecil khusus absen: perlu peta fokus untuk set/geser titik -->
    <Dialog
      v-model="showPicker"
      :options="{ title: picker ? `Absen: ${picker.subject}` : 'Absen' }"
    >
      <template #body-content>
        <div class="space-y-3">
          <p class="text-sm text-ink-gray-6">
            {{ locating ? __('Mengambil lokasi…') : __('Geser marker atau ketuk peta untuk menandai lokasi.') }}
          </p>
          <p v-if="geoError" class="rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {{ geoError }} — {{ __('tandai manual di peta.') }}
          </p>
          <MiniMap
            v-if="showPicker"
            :lat="picker?.lat"
            :lng="picker?.lng"
            editable
            height="320px"
            @update="onMapUpdate"
          />
          <p class="text-xs text-ink-gray-5">
            {{ picker?.lat != null ? `${picker.lat.toFixed(6)}, ${picker.lng.toFixed(6)}` : __('Belum ada titik') }}
          </p>
        </div>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="showPicker = false" />
          <Button
            variant="solid"
            :label="picker?.kind === 'in' ? __('Check In') : __('Check Out')"
            :loading="saving"
            :disabled="picker?.lat == null"
            @click="confirmCheck"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import MiniMap from '@/components/MiniMap.vue'
import LinkField from '@/components/Controls/LinkField.vue'
import {
  Button,
  Badge,
  Dialog,
  FormControl,
  FeatherIcon,
  createResource,
} from 'frappe-ui'
import { sessionStore } from '@/stores/session'
import { usersStore } from '@/stores/users'
import { formatDate } from '@/utils'
import { ref, computed, h } from 'vue'

const props = defineProps({
  doctype: { type: String, required: true }, // CRM Lead | CRM Inquiry | CRM Quotation
  docname: { type: String, required: true },
  // doc induk, untuk prefill organization/contact saat create
  doc: { type: Object, default: () => ({}) },
})

const { user } = sessionStore()
const { getUser } = usersStore()

// Field link di CRM Meeting yang menunjuk ke dokumen induk tab ini.
const LINK_FIELD = {
  'CRM Lead': 'lead',
  'CRM Inquiry': 'inquiry',
  'CRM Quotation': 'quotation',
}
const linkField = computed(() => LINK_FIELD[props.doctype])

const FIELDS = [
  'name', 'subject', 'status', 'organization', 'contact',
  'lead', 'inquiry', 'quotation', 'meeting_date', 'meeting_from', 'meeting_to',
  'location', 'purpose', 'marketing', 'venue', 'provider', 'nominal', 'summary',
  'checkin_time', 'checkin_latitude', 'checkin_longitude',
  'checkout_time', 'checkout_latitude', 'checkout_longitude',
]

const meetingsList = createResource({
  url: 'frappe.client.get_list',
  makeParams: () => ({
    doctype: 'CRM Meeting',
    filters: { [linkField.value]: props.docname },
    fields: FIELDS,
    order_by: 'meeting_from desc',
    limit_page_length: 50,
  }),
  auto: true,
})
// Perlu tindakan = absen belum lengkap (belum check-in / belum check-out),
// kecuali meeting yang dibatalkan. Yang selesai tidak ditandai.
const needsAction = (m) =>
  m.status !== 'Cancelled' && (!m.checkin_time || !m.checkout_time)

const meetings = computed(() => {
  const rows = [...(meetingsList.data || [])]
  // Yang belum lengkap di atas; sesama grupnya urut jadwal terbaru dulu.
  return rows.sort(
    (a, b) =>
      needsAction(b) - needsAction(a) ||
      new Date(b.meeting_date || 0) - new Date(a.meeting_date || 0),
  )
})

// ---- form bersama create & edit (inline, bukan modal) ---------------------
const EDIT_KEYS = [
  'subject', 'status', 'organization', 'contact', 'lead', 'inquiry',
  'quotation', 'meeting_date', 'meeting_from', 'meeting_to', 'location',
  'purpose', 'marketing', 'venue', 'provider', 'nominal', 'summary',
]

// Render form sebagai functional component kecil: field sama persis dgn MeetingModal.
const MeetingForm = {
  props: { modelValue: Object },
  emits: ['update:modelValue'],
  setup(p) {
    // Object modelValue dimutasi langsung oleh v-model tiap kontrol — cukup.
    const f = p.modelValue
    const row = (...children) =>
      h('div', { class: 'grid grid-cols-2 gap-4' }, children)
    return () =>
      h('div', { class: 'space-y-4' }, [
        h(FormControl, {
          label: 'Subject', required: true, modelValue: f.subject,
          'onUpdate:modelValue': (v) => (f.subject = v),
        }),
        row(
          h(LinkField, {
            label: 'Marketing', doctype: 'User', required: true, modelValue: f.marketing,
            'onUpdate:modelValue': (v) => (f.marketing = v),
          }),
          h(FormControl, {
            label: 'Status', type: 'select',
            options: ['Scheduled', 'Visited', 'Cancelled'], modelValue: f.status,
            'onUpdate:modelValue': (v) => (f.status = v),
          }),
        ),
        row(
          h(LinkField, {
            label: 'Related To', doctype: 'CRM Organization', modelValue: f.organization,
            'onUpdate:modelValue': (v) => (f.organization = v),
          }),
          h(LinkField, {
            label: 'Contact', doctype: 'Contact', modelValue: f.contact,
            'onUpdate:modelValue': (v) => (f.contact = v),
          }),
        ),
        h(FormControl, {
          label: 'Meeting Date', type: 'datetime-local', required: true,
          modelValue: f.meeting_date,
          'onUpdate:modelValue': (v) => (f.meeting_date = v),
        }),
        row(
          h(FormControl, {
            label: 'From (Check In)', type: 'datetime-local', modelValue: f.meeting_from,
            'onUpdate:modelValue': (v) => (f.meeting_from = v),
          }),
          h(FormControl, {
            label: 'To (Check Out)', type: 'datetime-local', modelValue: f.meeting_to,
            'onUpdate:modelValue': (v) => (f.meeting_to = v),
          }),
        ),
        h(FormControl, {
          label: 'Location', modelValue: f.location,
          'onUpdate:modelValue': (v) => (f.location = v),
        }),
        h(FormControl, {
          label: 'Tujuan Visit', type: 'textarea', modelValue: f.purpose,
          'onUpdate:modelValue': (v) => (f.purpose = v),
        }),
        row(
          h(FormControl, {
            label: 'Meeting Venue', modelValue: f.venue,
            'onUpdate:modelValue': (v) => (f.venue = v),
          }),
          h(FormControl, {
            label: 'Provider', modelValue: f.provider,
            'onUpdate:modelValue': (v) => (f.provider = v),
          }),
        ),
        h(FormControl, {
          label: 'Nominal', type: 'number', modelValue: f.nominal,
          'onUpdate:modelValue': (v) => (f.nominal = v),
        }),
        h(FormControl, {
          label: 'Summary Meeting', type: 'textarea', modelValue: f.summary,
          'onUpdate:modelValue': (v) => (f.summary = v),
        }),
      ])
  },
}

// ---- create ---------------------------------------------------------------
const creating = ref(false)
const createForm = ref(null)

function startCreate() {
  const d = props.doc || {}
  createForm.value = {
    subject: `Meeting - ${d.organization || d.account || ''}`.trim(),
    status: 'Scheduled',
    organization: d.organization || d.account || '',
    contact: d.contact || '',
    lead: '', inquiry: '', quotation: '',
    meeting_date: '', meeting_from: '', meeting_to: '', location: '', purpose: '',
    marketing: user, venue: '', provider: '', nominal: 0, summary: '',
    [linkField.value]: props.docname,
  }
  creating.value = true
}

const insertDoc = createResource({
  url: 'frappe.client.insert',
  makeParams: () => {
    const doc = { doctype: 'CRM Meeting', ...createForm.value }
    DT_KEYS.forEach((k) => (doc[k] = fromInput(doc[k])))
    return { doc }
  },
  onSuccess: () => {
    creating.value = false
    meetingsList.reload()
  },
  onError: (e) => alert(e.messages?.[0] || e.message || 'Failed to save'),
})
function saveNew() {
  if (!createForm.value.subject) return alert('Subject is required')
  if (!createForm.value.marketing) return alert('Marketing is required')
  if (!createForm.value.meeting_date) return alert('Meeting Date wajib diisi')
  insertDoc.submit()
}

// ---- edit inline ----------------------------------------------------------
const expanded = ref('')
const editForm = ref(null)

// datetime-local hanya menerima "YYYY-MM-DDTHH:mm"; Frappe menyimpan
// "YYYY-MM-DD HH:mm:ss.ffffff". Tanpa konversi dua arah, input-nya diam-diam
// menolak nilai (tampak kosong) dan nilai balik tak tersimpan.
const DT_KEYS = ['meeting_date', 'meeting_from', 'meeting_to']
const toInput = (v) => (v ? String(v).replace(' ', 'T').slice(0, 16) : '')
const fromInput = (v) => (v ? String(v).replace('T', ' ') : '')

function buildForm(m) {
  const f = Object.fromEntries(EDIT_KEYS.map((k) => [k, m?.[k] ?? '']))
  DT_KEYS.forEach((k) => (f[k] = toInput(f[k])))
  return f
}

// Form yang sedang terbuka dibangun ulang dari data terbaru (dipanggil setelah reload).
function syncEditForm(name) {
  if (expanded.value !== name) return
  const m = meetings.value.find((x) => x.name === name)
  if (m) editForm.value = buildForm(m)
}

function toggle(name) {
  if (expanded.value === name) {
    expanded.value = ''
    editForm.value = null
    return
  }
  const m = meetings.value.find((x) => x.name === name)
  editForm.value = buildForm(m)
  expanded.value = name
}

const updateDoc = createResource({
  url: 'frappe.client.set_value',
  onSuccess: () => meetingsList.reload(),
  onError: (e) => alert(e.messages?.[0] || e.message || 'Failed to save'),
})
function saveEdit(name) {
  const values = { ...editForm.value }
  DT_KEYS.forEach((k) => (values[k] = fromInput(values[k])))
  updateDoc.submit({
    doctype: 'CRM Meeting',
    name,
    fieldname: values,
  })
}

// ---- absen (pola sama dgn halaman MeetingAttendance) ----------------------
const geoError = ref('')
const locating = ref(false)
const saving = ref(false)
const showPicker = ref(false)
const picker = ref(null)

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
    const res = await createResource({
      url: `crm_cakra.fcrm.doctype.crm_meeting.crm_meeting.${method}`,
      params: { meeting: picker.value.name, latitude: picker.value.lat, longitude: picker.value.lng },
    }).fetch()
    showPicker.value = false
    // check_in/check_out MENGEMBALIKAN dokumen terbaru — pakai langsung supaya
    // From/To & info absen berubah SEKETIKA, tanpa menunggu round-trip reload.
    if (res) {
      const rows = meetingsList.data || []
      const idx = rows.findIndex((x) => x.name === picker.value.name)
      if (idx >= 0) {
        const patch = Object.fromEntries(FIELDS.map((k) => [k, res[k] ?? rows[idx][k]]))
        meetingsList.data = [...rows.slice(0, idx), { ...rows[idx], ...patch }, ...rows.slice(idx + 1)]
        syncEditForm(picker.value.name)
      }
    }
    meetingsList.reload() // penyelaras belakang; UI sudah benar duluan
  } catch (e) {
    geoError.value = e.messages?.[0] || e.message || 'Gagal simpan absen'
  } finally {
    saving.value = false
  }
}
</script>
