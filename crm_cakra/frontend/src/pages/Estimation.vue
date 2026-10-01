<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs" />
    </template>
    <template v-if="estimation.doc?.name" #right-header>
      <AssignTo v-model="assignees.data" doctype="CRM Estimation" :docname="props.estimationId" />
    </template>
  </LayoutHeader>

  <div v-if="estimation.doc?.name" class="flex h-full overflow-hidden">
    <!-- LEFT: Tabs -->
    <Tabs v-model="tabIndex" as="div" :tabs="tabs"
      class="flex flex-1 overflow-hidden flex-col [&_[role='tab']]:px-0 [&_[role='tab']]:shrink-0 [&_[role='tablist']]:px-5 [&_[role='tablist']::-webkit-scrollbar]:h-0 [&_[role='tablist']]:min-h-[45px] [&_[role='tablist']]:gap-7.5 [&_[role='tabpanel']:not([hidden])]:flex [&_[role='tabpanel']:not([hidden])]:grow">
      <template #tab-panel="{ tab }">
        <div v-if="tab.name === 'Data'" class="flex-1 overflow-y-auto px-5 pb-8">
          <DataFields doctype="CRM Estimation" :docname="props.estimationId" />
        </div>

        <Activities v-else ref="activities" v-model:reload="reload" v-model:tabIndex="tabIndex"
          doctype="CRM Estimation" :docname="props.estimationId" :tabs="tabs" />
      </template>
    </Tabs>

    <!-- RIGHT: Sidebar -->
    <Resizer side="right" class="flex flex-col justify-between border-l">
      <div class="flex h-[45px] cursor-copy items-center border-b px-5 py-2.5 text-lg font-medium text-ink-gray-9"
        @click="copyToClipboard(props.estimationId)">
        {{ props.estimationId }}
      </div>

      <div class="flex items-center justify-start gap-5 border-b p-5">
        <Tooltip :text="__('Estimation')">
          <div class="group relative size-12">
            <Avatar size="3xl" class="size-12" :label="title" />
          </div>
        </Tooltip>
        <div class="flex flex-col gap-2.5 truncate text-ink-gray-9">
          <div class="truncate text-2xl font-medium">{{ title }}</div>
          <div class="flex gap-1.5">
            <Button :tooltip="__('Attach a File')" :icon="AttachmentIcon" @click="showFilesUploader = true" />
          </div>
        </div>
      </div>

      <div v-if="estimation.doc.ascend_sync_status" class="flex flex-col gap-2 border-b p-5 text-base text-ink-gray-7">
        <div class="flex justify-between gap-2">
          <span>{{ __('Ascend') }}</span>
          <span class="truncate text-ink-gray-9">{{ estimation.doc.ascend_estimation_no || __('Not linked yet') }}</span>
        </div>
        <div class="flex justify-between gap-2">
          <span>{{ __('Sync Status') }}</span>
          <span :class="needsDecision ? 'text-ink-red-4' : 'text-ink-gray-9'">{{ __(estimation.doc.ascend_sync_status) }}</span>
        </div>
        <div v-if="estimation.doc.ascend_sync_error" class="whitespace-pre-line text-sm">
          {{ estimation.doc.ascend_sync_error }}
        </div>
        <div v-if="needsDecision" class="flex gap-2">
          <Button :label="__('Use CRM Data')" :loading="resolve.loading" @click="resolve.submit({ which: 'use_crm' })" />
          <Button v-if="estimation.doc.ascend_estimation_id" :label="__('Use Ascend Data')" :loading="resolve.loading"
            @click="resolve.submit({ which: 'use_ascend' })" />
        </div>
      </div>

      <div class="flex flex-col gap-2 border-b p-5 text-base text-ink-gray-7">
        <div class="font-medium text-ink-gray-9">{{ __('Approval') }}</div>
        <div v-for="lv in approvalLevels" :key="lv.level" class="flex items-center justify-between gap-2">
          <span>{{ __(lv.label) }}</span>
          <span v-if="estimation.doc[`approved_${lv.level}`]" class="truncate text-ink-green-3"
            :title="estimation.doc[`approved_${lv.level}_date`]">
            {{ getUser(estimation.doc[`approved_${lv.level}_by`]).full_name }}
          </span>
          <Button v-else-if="canApprove(lv)" size="sm" variant="solid" :label="__('Approve')"
            :loading="approve.loading" @click="approve.submit({ level: lv.level })" />
          <span v-else class="text-ink-gray-5">{{ __('Pending') }}</span>
        </div>
      </div>

      <div v-if="sections.data" class="flex flex-1 flex-col justify-between overflow-hidden">
        <SidePanelLayout :sections="sections.data" doctype="CRM Estimation" :docname="props.estimationId"
          @reload="sections.reload" />
      </div>
    </Resizer>
  </div>

  <ErrorPage v-else-if="errorTitle" :errorTitle="errorTitle" :errorMessage="errorMessage" />

  <FilesUploader v-model="showFilesUploader" doctype="CRM Estimation" :docname="props.estimationId" @after="
    () => {
      activities?.all_activities?.reload()
      changeTabTo('Attachments')
    }
  " />
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  createDocumentResource,
  createResource,
  Breadcrumbs,
  Button,
  Tabs,
  Tooltip,
  Avatar,
  toast,
} from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import Resizer from '@/components/Resizer.vue'
import ErrorPage from '@/components/ErrorPage.vue'
import ActivityIcon from '@/components/Icons/ActivityIcon.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import DetailsIcon from '@/components/Icons/DetailsIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import AttachmentIcon from '@/components/Icons/AttachmentIcon.vue'
import Activities from '@/components/Activities/Activities.vue'
import FilesUploader from '@/components/FilesUploader/FilesUploader.vue'
import SidePanelLayout from '@/components/SidePanelLayout.vue'
import DataFields from '@/components/Activities/DataFields.vue'
import AssignTo from '@/components/AssignTo.vue'
import { copyToClipboard } from '@/utils'
import { getView } from '@/utils/view'
import { useDocument } from '@/data/document'
import { usersStore } from '@/stores/users'
import { applyEstimationGridOverrides } from '@/utils/estimationGrid'
import { useActiveTabManager } from '@/composables/useActiveTabManager'

const route = useRoute()

const props = defineProps({
  estimationId: { type: String, required: true },
})

const errorTitle = ref('')
const errorMessage = ref('')
const reload = ref(false)
const showFilesUploader = ref(false)
const activities = ref(null)

const estimation = createDocumentResource({
  doctype: 'CRM Estimation',
  name: props.estimationId,
  cache: ['estimation', props.estimationId],
  auto: true,
  onError(err) {
    errorTitle.value = __(
      err.exc_type === 'DoesNotExistError' ? 'Estimation Not Found' : 'Error',
    )
    errorMessage.value = __(err.messages?.[0] || 'An Error Occurred')
  },
})

const sections = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections',
  params: { doctype: 'CRM Estimation' },
  auto: true,
})

const { document: gridDoc, assignees } = useDocument('CRM Estimation', props.estimationId)
applyEstimationGridOverrides(gridDoc)

const title = computed(
  () => estimation.doc?.customer_id || estimation.doc?.estimation_no || props.estimationId,
)

const breadcrumbs = computed(() => {
  const items = [{ label: __('Estimations'), route: { name: 'Estimations' } }]
  if (route.query.view || route.query.viewType) {
    const view = getView(route.query.view, route.query.viewType, 'CRM Estimation')
    if (view) {
      items.push({
        label: __(view.label),
        icon: view.icon,
        route: {
          name: 'Estimations',
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
  { name: 'Comments', label: __('Comments'), icon: CommentIcon },
  { name: 'Notes', label: __('Notes'), icon: NoteIcon },
  { name: 'Attachments', label: __('Attachments'), icon: AttachmentIcon },
  { name: 'Activity', label: __('Activity'), icon: ActivityIcon },
])

const { tabIndex } = useActiveTabManager(tabs, 'lastEstimationTab', 'data')

function changeTabTo(name) {
  const idx = tabs.value.findIndex((t) => t.name === name)
  if (idx >= 0) tabIndex.value = idx
}

// Estimasi berpasangan dengan Ascend: tidak bisa dihapus, konflik diputuskan di sini.
const needsDecision = computed(() =>
  ['Conflict', 'Push Failed', 'Pull Failed'].includes(estimation.doc?.ascend_sync_status),
)

// Approval 3 level; server (crm_estimation.approve) yang benar-benar menjaga role & urutan.
const { getUser } = usersStore()
const approvalLevels = [
  { level: 'procurement', label: 'Procurement', role: 'Estimation Approve Procurement' },
  { level: 'finance', label: 'Finance', role: 'Estimation Approve Finance' },
  { level: 'marketing', label: 'Marketing', role: 'Estimation Approve Marketing' },
]

function canApprove(lv) {
  const doc = estimation.doc
  if (doc.disabled || !(getUser().roles || []).includes(lv.role)) return false
  return lv.level !== 'marketing' || (doc.approved_procurement && doc.approved_finance)
}

const approve = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_estimation.crm_estimation.approve',
  makeParams: ({ level }) => ({ name: props.estimationId, level }),
  onSuccess: () => {
    estimation.reload()
    gridDoc.reload()
    reload.value = true
  },
  onError: (err) => toast.error(err.messages?.[0] || __('Approve failed')),
})

const resolve = createResource({
  makeParams: ({ which }) => ({ name: props.estimationId, which }),
  url: 'crm_cakra.integrations.ascend.resolve',
  onSuccess: () => {
    estimation.reload()
    reload.value = true
  },
  onError: (err) => toast.error(err.messages?.[0] || __('Sync failed')),
})
</script>
