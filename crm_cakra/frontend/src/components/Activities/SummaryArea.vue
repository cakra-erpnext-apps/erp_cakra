<template>
  <div class="px-3 pb-5 sm:px-10">
    <div
      v-if="summary.loading"
      class="py-16 text-center text-base text-ink-gray-5"
    >
      {{ __('Loading...') }}
    </div>

    <template v-else>
      <!-- Counts -->
      <div class="grid grid-cols-2 gap-3 py-4 sm:grid-cols-5">
        <div
          v-for="s in sections"
          :key="s.key"
          class="rounded-lg border border-outline-gray-2 px-4 py-3"
        >
          <div class="text-2xl font-semibold text-ink-gray-9">
            {{ s.rows.length }}
          </div>
          <div class="text-sm text-ink-gray-6">{{ s.label }}</div>
        </div>
      </div>

      <!-- One block per doctype -->
      <div v-for="s in sections" :key="s.key" class="mb-6">
        <div class="mb-2 text-base font-medium text-ink-gray-8">
          {{ s.label }}
        </div>
        <div
          v-if="!s.rows.length"
          class="rounded-lg border border-outline-gray-2 px-4 py-6 text-center text-sm text-ink-gray-5"
        >
          {{ __('Nothing yet') }}
        </div>
        <div v-else class="divide-y rounded-lg border border-outline-gray-2">
          <div
            v-for="row in visibleRows(s)"
            :key="row.name"
            class="flex items-center justify-between gap-3 px-4 py-3"
            :class="
              s.route || s.open ? 'cursor-pointer hover:bg-surface-gray-1' : ''
            "
            @click="s.route ? router.push(s.route(row)) : s.open?.(row)"
          >
            <div class="min-w-0">
              <div class="truncate text-base text-ink-gray-8">
                {{ s.title(row) }}
              </div>
              <div class="truncate text-sm text-ink-gray-5">
                {{ s.detail(row) }}
              </div>
            </div>
            <Badge
              v-if="s.status(row)"
              :label="s.status(row)"
              variant="subtle"
              class="shrink-0"
            />
          </div>
          <button
            v-if="s.rows.length > COLLAPSED"
            class="w-full px-4 py-2 text-left text-sm text-ink-gray-6 hover:bg-surface-gray-1"
            @click="toggle(s.key)"
          >
            {{
              expanded[s.key]
                ? __('Show less')
                : __('Show all {0}', [s.rows.length])
            }}
          </button>
        </div>
      </div>
    </template>

    <MeetingModal
      v-if="meetingId"
      v-model="showMeetingModal"
      :meetingId="meetingId"
      @updated="summary.reload()"
    />
  </div>
</template>

<script setup>
import { Badge, createResource } from 'frappe-ui'
import MeetingModal from '@/components/Modals/MeetingModal.vue'
import { useDoctypeModal } from '@/composables/doctypeModal'
import { formatDate, timeAgo } from '@/utils'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const COLLAPSED = 5

const props = defineProps({
  docname: { type: String, required: true },
  doctype: { type: String, default: 'CRM Lead' },
})

const router = useRouter()

const isOrganization = props.doctype === 'CRM Organization'

const summary = createResource({
  url: 'crm_cakra.api.activities.get_summary',
  params: { name: props.docname, doctype: props.doctype },
  cache: ['summary', props.doctype, props.docname],
  auto: true,
})

// Tasks/Notes ikut terkumpul dari Inquiry & Quotation di bawahnya, jadi tiap
// baris menyebut asalnya kalau bukan menempel di dokumen ini sendiri.
const source = (row) =>
  row.reference_docname && row.reference_docname !== props.docname
    ? row.reference_docname
    : ''

// Task/Note/Meeting tidak punya halaman sendiri: Task & Note pakai modal global
// (DoctypeModals di App.vue), Meeting pakai modal khususnya.
const { showModal } = useDoctypeModal()

const openDoctypeModal = (doctype, title) => (row) =>
  showModal({
    name: row.name,
    doctype,
    title,
    callbacks: { afterUpdate: () => summary.reload() },
  })

const showMeetingModal = ref(false)
const meetingId = ref('')

function openMeeting(row) {
  meetingId.value = row.name
  showMeetingModal.value = true
}

watch(showMeetingModal, (open) => {
  if (!open) meetingId.value = ''
})

const expanded = reactive({})
const toggle = (key) => (expanded[key] = !expanded[key])
const visibleRows = (s) =>
  expanded[s.key] ? s.rows : s.rows.slice(0, COLLAPSED)

const money = (row) =>
  row.net_total || row.expected_inquiry_value
    ? `${row.currency || ''} ${Number(
        row.net_total || row.expected_inquiry_value,
      ).toLocaleString()}`.trim()
    : ''

const joined = (...parts) => parts.filter(Boolean).join(' - ')

const sections = computed(() => {
  const d = summary.data || {}
  return [
    ...(isOrganization
      ? [
          {
            key: 'leads',
            label: __('Leads'),
            rows: d.leads || [],
            title: (r) => r.lead_name || r.name,
            detail: (r) => joined(r.name, r.lead_owner),
            status: (r) => (r.converted ? __('Converted') : r.status),
            route: (r) => ({ name: 'Lead', params: { leadId: r.name } }),
          },
        ]
      : []),
    {
      key: 'inquiries',
      label: __('Inquiries'),
      rows: d.inquiries || [],
      title: (r) => r.name,
      detail: (r) => joined(r.organization, money(r)),
      status: (r) => r.status,
      route: (r) => ({ name: 'Inquiry', params: { inquiryId: r.name } }),
    },
    {
      key: 'quotations',
      label: __('Quotations'),
      rows: d.quotations || [],
      title: (r) => r.number || r.name,
      detail: (r) => joined(r.subject, r.date && formatDate(r.date), money(r)),
      status: (r) => r.state,
      route: (r) => ({ name: 'Quotation', params: { quotationId: r.name } }),
    },
    {
      key: 'meetings',
      label: __('Meetings'),
      rows: d.meetings || [],
      title: (r) => r.subject || r.name,
      detail: (r) =>
        joined(r.meeting_date && formatDate(r.meeting_date), r.location),
      status: (r) => r.status,
      open: openMeeting,
    },
    {
      key: 'tasks',
      label: __('Tasks'),
      rows: d.tasks || [],
      title: (r) => r.title,
      detail: (r) =>
        joined(r.priority, r.start_date && formatDate(r.start_date), source(r)),
      status: (r) => r.status,
      open: openDoctypeModal('CRM Task', 'Task'),
    },
    {
      key: 'notes',
      label: __('Notes'),
      rows: d.notes || [],
      title: (r) => r.title || __('Untitled'),
      detail: (r) => joined(__(timeAgo(r.modified)), source(r)),
      status: () => '',
      open: openDoctypeModal('FCRM Note', 'Note'),
    },
  ]
})
</script>
