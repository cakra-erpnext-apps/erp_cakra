<template>
  <Dialog v-model="show" :options="{ title: meetingId ? 'Edit Meeting' : 'New Meeting', size: '2xl' }">
    <template #body-content>
      <div class="space-y-4">
        <FormControl v-model="form.subject" label="Subject" required />
        <div class="grid grid-cols-2 gap-4">
          <LinkField label="Marketing" doctype="User" v-model="form.marketing" required />
          <FormControl v-model="form.status" label="Status" type="select"
            :options="['Scheduled', 'Visited', 'Cancelled']" />
        </div>
        <div class="grid grid-cols-2 gap-4">
          <LinkField label="Related To" doctype="CRM Organization" v-model="form.organization" />
          <LinkField label="Contact" doctype="Contact" v-model="form.contact" />
        </div>
        <div class="grid grid-cols-2 gap-4">
          <LinkField label="Inquiry" doctype="CRM Inquiry" v-model="form.inquiry" />
          <LinkField label="Quotation" doctype="CRM Quotation" v-model="form.quotation" />
        </div>
        <FormControl v-model="form.meeting_date" label="Meeting Date" type="datetime-local" required />
        <div class="grid grid-cols-2 gap-4">
          <FormControl v-model="form.meeting_from" label="From (Check In)" type="datetime-local" />
          <FormControl v-model="form.meeting_to" label="To (Check Out)" type="datetime-local" />
        </div>
        <FormControl v-model="form.location" label="Location" />
        <FormControl v-model="form.purpose" label="Tujuan Visit" type="textarea" />
        <div class="grid grid-cols-2 gap-4">
          <FormControl v-model="form.venue" label="Meeting Venue" />
          <FormControl v-model="form.provider" label="Provider" />
        </div>
        <FormControl v-model="form.nominal" label="Nominal" type="number" />
        <FormControl v-model="form.summary" label="Summary Meeting" type="textarea" />

        <div v-if="meetingId && checkin.lat != null">
          <label class="mb-1.5 block text-xs text-ink-gray-5">{{ __('Titik Absen (Check-In)') }}</label>
          <MiniMap :lat="checkin.lat" :lng="checkin.lng" height="220px" />
        </div>
      </div>
    </template>

    <template #actions>
      <div class="flex w-full items-center justify-between gap-2">
        <Button v-if="meetingId" :label="__('Absen')" iconLeft="map-pin"
          @click="goAbsen" />
        <span v-else />
        <div class="flex gap-2">
          <Button :label="__('Cancel')" @click="show = false" />
          <Button variant="solid" :label="__('Save')" :loading="saveDoc.loading" @click="save" />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Dialog, FormControl, Button, createResource } from 'frappe-ui'
import LinkField from '@/components/Controls/LinkField.vue'
import MiniMap from '@/components/MiniMap.vue'
import { sessionStore } from '@/stores/session'

const show = defineModel()
const props = defineProps({
  meetingId: { type: String, default: '' },
  // Nilai awal saat create dari halaman Quotation/Inquiry, mis. { quotation, organization }.
  prefill: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['created', 'updated'])
const router = useRouter()
const { user } = sessionStore()

const blank = () => ({
  subject: '', status: 'Scheduled', organization: '', contact: '',
  inquiry: '', quotation: '', meeting_date: '', meeting_from: '', meeting_to: '',
  location: '', purpose: '', marketing: user, venue: '', provider: '', nominal: 0, summary: '',
})
const form = ref(blank())
const checkin = ref({ lat: null, lng: null }) // titik absen untuk peta read-only

// Edit mode: muat dokumen saat modal dibuka dengan meetingId.
// Create mode: mulai dari blank + prefill konteks (quotation/inquiry/organization).
watch(
  () => [show.value, props.meetingId],
  ([open]) => {
    if (!open) return
    if (props.meetingId) loadDoc.fetch()
    else {
      form.value = { ...blank(), ...props.prefill }
      checkin.value = { lat: null, lng: null }
    }
  },
)

function goAbsen() {
  show.value = false
  router.push({ name: 'MeetingAttendance' })
}

// datetime-local butuh "YYYY-MM-DDTHH:mm"; Frappe menyimpan "YYYY-MM-DD HH:mm:ss".
const DT_KEYS = ['meeting_date', 'meeting_from', 'meeting_to']
const toInput = (v) => (v ? String(v).replace(' ', 'T').slice(0, 16) : '')
const fromInput = (v) => (v ? String(v).replace('T', ' ') : '')

const loadDoc = createResource({
  url: 'frappe.client.get',
  makeParams: () => ({ doctype: 'CRM Meeting', name: props.meetingId }),
  onSuccess(doc) {
    // Ambil hanya field editable; jangan bawa name/owner/creation ke set_value.
    const f = blank()
    for (const k in f) if (doc[k] != null) f[k] = doc[k]
    DT_KEYS.forEach((k) => (f[k] = toInput(f[k])))
    form.value = f
    checkin.value = { lat: doc.checkin_latitude ?? null, lng: doc.checkin_longitude ?? null }
  },
})

function onSaved(doc) {
  if (props.meetingId) {
    show.value = false
    emit('updated', props.meetingId)
  } else {
    // Jangan tutup: emit nama baru supaya parent flip ke edit mode & tombol Absen muncul.
    emit('created', doc?.name)
  }
}
function onError(err) {
  alert(err.messages?.[0] || err.message || 'Failed to save')
}

function outValues() {
  const v = { ...form.value }
  DT_KEYS.forEach((k) => (v[k] = fromInput(v[k])))
  return v
}
const insertDoc = createResource({
  url: 'frappe.client.insert',
  makeParams: () => ({ doc: { doctype: 'CRM Meeting', ...outValues() } }),
  onSuccess: onSaved,
  onError,
})
const updateDoc = createResource({
  url: 'frappe.client.set_value',
  makeParams: () => ({ doctype: 'CRM Meeting', name: props.meetingId, fieldname: outValues() }),
  onSuccess: onSaved,
  onError,
})
const saveDoc = { get loading() { return insertDoc.loading || updateDoc.loading } }

function save() {
  if (!form.value.subject) return alert('Subject is required')
  if (!form.value.marketing) return alert('Marketing is required')
  // Tanpa tanggal, meeting tidak akan pernah tampil di kalender.
  if (!form.value.meeting_date) return alert('Meeting Date wajib diisi')
  ;(props.meetingId ? updateDoc : insertDoc).submit()
}
</script>
