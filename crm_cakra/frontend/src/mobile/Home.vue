<template>
  <div class="sticky top-0 z-10 flex h-12 items-center justify-between border-b bg-surface-white px-4">
    <span class="truncate text-base font-semibold text-ink-gray-8">
      {{ __('Hi') }}, {{ me?.first_name || me?.full_name }}
    </span>
    <Avatar
      :image="me?.user_image"
      :label="me?.full_name"
      size="lg"
      @click="$router.push({ name: 'MobileMore' })"
    />
  </div>

  <!-- Angka bulan berjalan, sumbernya endpoint chart yang sama dengan dashboard
       desktop -- supaya tidak ada dua definisi "inquiry berjalan". -->
  <div class="grid grid-cols-2 gap-3 p-4">
    <div
      v-for="card in charts"
      :key="card.name"
      class="rounded-lg border p-3"
    >
      <div class="truncate text-sm text-ink-gray-5">
        {{ card.resource.data?.title || __(card.label) }}
      </div>
      <div class="mt-1 text-2xl font-semibold text-ink-gray-8">
        {{ card.resource.data?.value ?? '-' }}
      </div>
      <div class="truncate text-xs text-ink-gray-5">
        {{ card.resource.data?.suffix || delta(card.resource.data) }}
      </div>
    </div>
  </div>

  <div class="px-4 pb-2 text-sm font-medium text-ink-gray-5">
    {{ __('Meetings today') }}
  </div>
  <div v-if="today.data?.data?.length" class="divide-y border-y">
    <button
      v-for="m in today.data.data"
      :key="m.name"
      class="flex w-full items-start justify-between gap-3 px-4 py-3 text-left active:bg-surface-gray-2"
      @click="openMeeting(m.name)"
    >
      <div class="min-w-0">
        <div class="truncate text-base font-medium text-ink-gray-8">
          {{ m.subject || m.name }}
        </div>
        <div class="truncate text-sm text-ink-gray-5">
          {{ m.organization || m.location || '' }}
        </div>
      </div>
      <span class="shrink-0 text-sm text-ink-gray-6">
        {{ formatDate(m.meeting_date, 'hh:mm a') }}
      </span>
    </button>
  </div>
  <div v-else class="border-y px-4 py-6 text-center text-sm text-ink-gray-4">
    {{ __('No meetings today') }}
  </div>

  <div class="grid grid-cols-2 gap-3 p-4">
    <Button
      v-for="action in actions"
      :key="action.label"
      class="h-10"
      :label="__(action.label)"
      :iconLeft="action.icon"
      @click="action.onClick"
    />
  </div>

  <MeetingModal v-model="showMeeting" :meetingId="meetingId" @updated="today.reload()" />
</template>

<script setup>
import MeetingModal from '@/components/Modals/MeetingModal.vue'
import { sessionStore } from '@/stores/session'
import { usersStore } from '@/stores/users'
import { formatDate } from '@/utils'
import { Avatar, Button, createResource, dayjsLocal } from 'frappe-ui'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const { user } = sessionStore()
const { getUser } = usersStore()

const me = computed(() => getUser(user))
const showMeeting = ref(false)
const meetingId = ref('')

const chart = (name) =>
  createResource({
    url: 'crm_cakra.api.dashboard.get_chart',
    params: { name, type: 'number' },
    auto: true,
  })

// Tanpa from_date/to_date, server memakai bulan berjalan.
const charts = [
  { name: 'total_leads', label: 'Total leads', resource: chart('total_leads') },
  { name: 'ongoing_inquiries', label: 'Ongoing inquiries', resource: chart('ongoing_inquiries') },
  { name: 'won_inquiries', label: 'Won inquiries', resource: chart('won_inquiries') },
  { name: 'open_quotations', label: 'Open quotations', resource: chart('open_quotations') },
]

const today = createResource({
  url: 'crm_cakra.api.doc.get_linked_list',
  params: {
    doctype: 'CRM Meeting',
    filters: { meeting_date: ['between', [todayStart(), todayEnd()]] },
    fields: ['name', 'subject', 'organization', 'location', 'meeting_date', 'status'],
    order_by: 'meeting_date asc',
    page_length: 20,
  },
  auto: true,
})

// dayjsLocal, bukan toISOString(): di WIB (UTC+7) tanggal UTC masih kemarin
// sampai jam 7 pagi, jadi "meeting hari ini" akan salah sepanjang pagi.
function todayStart() {
  return dayjsLocal().format('YYYY-MM-DD') + ' 00:00:00'
}

function todayEnd() {
  return dayjsLocal().format('YYYY-MM-DD') + ' 23:59:59'
}

function delta(data) {
  if (!data || data.delta === undefined || data.delta === null) return ''
  const value = Number(data.delta).toFixed(1)
  return `${data.delta > 0 ? '+' : ''}${value}${data.deltaSuffix || ''}`
}

function openMeeting(name) {
  meetingId.value = name
  showMeeting.value = true
}

const actions = [
  { label: 'New Inquiry', icon: 'plus', onClick: () => router.push({ name: 'NewInquiry' }) },
  { label: 'New Quotation', icon: 'plus', onClick: () => router.push({ name: 'NewQuotation' }) },
  { label: 'Absen', icon: 'map-pin', onClick: () => router.push({ name: 'MeetingAttendance' }) },
  {
    label: 'Meetings',
    icon: 'calendar',
    onClick: () => router.push({ name: 'MobileList', params: { list: 'meetings' } }),
  },
]
</script>
