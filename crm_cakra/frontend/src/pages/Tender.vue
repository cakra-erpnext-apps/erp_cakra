<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs" />
    </template>
    <template v-if="tender.doc?.name" #right-header>
      <Badge
        :theme="STATUS_THEME[tender.doc.status] || 'gray'"
        :label="__(tender.doc.status)"
        size="lg"
      />
      <Button
        :tooltip="__('Attach a File')"
        :icon="AttachmentIcon"
        @click="showFilesUploader = true"
      />
      <Button
        :tooltip="__('Delete')"
        variant="subtle"
        icon="trash-2"
        theme="red"
        @click="deleteTender"
      />
    </template>
  </LayoutHeader>

  <div v-if="tender.doc?.name" class="flex h-full overflow-hidden">
    <Tabs
      v-model="tabIndex"
      as="div"
      :tabs="tabs"
      class="flex flex-1 overflow-hidden flex-col [&_[role='tab']]:px-0 [&_[role='tab']]:shrink-0 [&_[role='tablist']]:px-5 [&_[role='tablist']::-webkit-scrollbar]:h-0 [&_[role='tablist']]:min-h-[45px] [&_[role='tablist']]:gap-7.5 [&_[role='tabpanel']:not([hidden])]:flex [&_[role='tabpanel']:not([hidden])]:grow"
    >
      <template #tab-panel="{ tab }">
        <div
          v-if="tab.name === 'Data'"
          class="flex-1 overflow-y-auto px-5 pb-8"
        >
          <DataFields doctype="CRM Tender" :docname="props.tenderId" />
        </div>

        <TenderFiles
          v-else-if="tab.name === 'File'"
          :tenderId="props.tenderId"
          class="flex-1 overflow-hidden"
        />

        <Activities
          v-else
          ref="activities"
          v-model:reload="reload"
          v-model:tabIndex="tabIndex"
          doctype="CRM Tender"
          :docname="props.tenderId"
          :tabs="tabs"
        />
      </template>
    </Tabs>

    <Resizer side="right" class="flex flex-col justify-between border-l">
      <div
        class="flex h-[45px] cursor-copy items-center border-b px-5 py-2.5 text-lg font-medium text-ink-gray-9"
        @click="copyToClipboard(props.tenderId)"
      >
        {{ props.tenderId }}
      </div>

      <div class="flex items-center justify-start gap-5 border-b p-5">
        <Tooltip :text="__('Tender')">
          <div class="group relative size-12">
            <Avatar size="3xl" class="size-12" :label="title" />
          </div>
        </Tooltip>
        <div class="flex flex-col gap-2.5 truncate text-ink-gray-9">
          <Tooltip :text="title">
            <div class="truncate text-2xl font-medium">{{ title }}</div>
          </Tooltip>
          <div class="text-base text-ink-gray-6">
            {{ tender.doc.tender_type || __('Tanpa tipe') }}
            <span v-if="closingLabel"> · {{ closingLabel }}</span>
          </div>
        </div>
      </div>

      <div
        v-if="sections.data"
        class="flex flex-1 flex-col justify-between overflow-hidden"
      >
        <SidePanelLayout
          :sections="sections.data"
          doctype="CRM Tender"
          :docname="props.tenderId"
          @reload="sections.reload"
        />
      </div>
    </Resizer>
  </div>

  <ErrorPage
    v-else-if="errorTitle"
    :errorTitle="errorTitle"
    :errorMessage="errorMessage"
  />

  <FilesUploader
    v-model="showFilesUploader"
    doctype="CRM Tender"
    :docname="props.tenderId"
    @after="
      () => {
        activities?.all_activities?.reload()
        changeTabTo('File')
      }
    "
  />
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Avatar,
  Badge,
  Breadcrumbs,
  Button,
  Tabs,
  Tooltip,
  createDocumentResource,
  createResource,
} from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import Resizer from '@/components/Resizer.vue'
import ErrorPage from '@/components/ErrorPage.vue'
import Activities from '@/components/Activities/Activities.vue'
import DataFields from '@/components/Activities/DataFields.vue'
import SidePanelLayout from '@/components/SidePanelLayout.vue'
import FilesUploader from '@/components/FilesUploader/FilesUploader.vue'
import TenderFiles from '@/components/Tender/TenderFiles.vue'
import ActivityIcon from '@/components/Icons/ActivityIcon.vue'
import AttachmentIcon from '@/components/Icons/AttachmentIcon.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import DetailsIcon from '@/components/Icons/DetailsIcon.vue'
import EmailIcon from '@/components/Icons/EmailIcon.vue'
import FileSpreadsheetIcon from '@/components/Icons/FileSpreadsheetIcon.vue'
import MeetingIcon from '@/components/Icons/MeetingIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import { copyToClipboard, formatDate } from '@/utils'
import { getView } from '@/utils/view'
import { useActiveTabManager } from '@/composables/useActiveTabManager'

const props = defineProps({ tenderId: { type: String, required: true } })

const router = useRouter()
const route = useRoute()

const STATUS_THEME = {
  Draft: 'gray',
  Prepared: 'blue',
  Submitted: 'orange',
  Won: 'green',
  Lost: 'red',
  Cancelled: 'gray',
}

const errorTitle = ref('')
const errorMessage = ref('')
const reload = ref(false)
const activities = ref(null)
const showFilesUploader = ref(false)

const tender = createDocumentResource({
  doctype: 'CRM Tender',
  name: props.tenderId,
  cache: ['tender', props.tenderId],
  auto: true,
  onError(err) {
    errorTitle.value = __(
      err.exc_type === 'DoesNotExistError' ? 'Tender Not Found' : 'Error',
    )
    errorMessage.value = __(err.messages?.[0] || 'An Error Occurred')
  },
})

const sections = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections',
  params: { doctype: 'CRM Tender' },
  auto: true,
})

const title = computed(() => tender.doc?.subject || props.tenderId)

// Sisa hari menuju closing: yang paling sering ditanya soal tender.
const closingLabel = computed(() => {
  const d = tender.doc?.closing_date
  if (!d) return ''
  const days = Math.ceil(
    (new Date(d + 'T00:00:00') - new Date().setHours(0, 0, 0, 0)) / 86400000,
  )
  if (days > 0) return __('closing {0} (H-{1})', [formatDate(d, 'D MMM'), days])
  if (days === 0) return __('closing hari ini')
  return __('closing {0} (lewat)', [formatDate(d, 'D MMM YYYY')])
})

const breadcrumbs = computed(() => {
  const items = [{ label: __('Tenders'), route: { name: 'Tenders' } }]
  if (route.query.view || route.query.viewType) {
    const view = getView(route.query.view, route.query.viewType, 'CRM Tender')
    if (view) {
      items.push({
        label: __(view.label),
        icon: view.icon,
        route: {
          name: 'Tenders',
          params: { viewType: route.query.viewType },
          query: { view: route.query.view },
        },
      })
    }
  }
  items.push({ label: title.value })
  return items
})

const tabs = computed(() => [
  { name: 'Data', label: __('Data'), icon: DetailsIcon },
  { name: 'File', label: __('File'), icon: FileSpreadsheetIcon },
  { name: 'Emails', label: __('Emails'), icon: EmailIcon },
  { name: 'Comments', label: __('Comments'), icon: CommentIcon },
  { name: 'Tasks', label: __('Tasks'), icon: TaskIcon },
  { name: 'Meetings', label: __('Meetings'), icon: MeetingIcon },
  { name: 'Notes', label: __('Notes'), icon: NoteIcon },
  { name: 'Attachments', label: __('Attachments'), icon: AttachmentIcon },
  { name: 'Calls', label: __('Calls'), icon: PhoneIcon },
  { name: 'Activity', label: __('Activity'), icon: ActivityIcon },
])

const { tabIndex } = useActiveTabManager(tabs, 'lastTenderTab', 'data')

function changeTabTo(name) {
  const idx = tabs.value.findIndex((t) => t.name === name)
  if (idx >= 0) tabIndex.value = idx
}

function deleteTender() {
  if (!confirm(__('Hapus tender ini?'))) return
  tender.delete.submit().then(() => router.push({ name: 'Tenders' }))
}
</script>
