<template>
  <LayoutHeader>
    <header
      class="relative flex h-10.5 items-center justify-between gap-2 py-2.5 pl-2"
    >
      <Breadcrumbs :items="breadcrumbs" />
    </header>
  </LayoutHeader>

  <div
    v-if="estimation.doc?.name"
    class="flex h-12 items-center justify-between gap-2 border-b px-3 py-2.5"
  >
    <AssignTo v-model="assignees.data" doctype="CRM Estimation" :docname="estimationId" />
    <div class="flex items-center gap-1.5">
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
        @click="deleteEstimation"
      />
    </div>
  </div>

  <div v-if="estimation.doc?.name" class="flex h-full overflow-hidden">
    <Tabs
      v-model="tabIndex"
      as="div"
      :tabs="tabs"
      class="flex flex-1 overflow-auto flex-col [&_[role='tab']]:px-0 [&_[role='tab']]:shrink-0 [&_[role='tablist']]:px-3 [&_[role='tablist']]:min-h-[45px] [&_[role='tablist']]:gap-7.5 [&_[role='tabpanel']:not([hidden])]:flex [&_[role='tabpanel']:not([hidden])]:grow"
    >
      <template #tab-panel="{ tab }">
        <div v-if="tab.name === 'Data'" class="flex-1 overflow-y-auto px-3 pb-8">
          <div v-if="sections.data" class="mb-4">
            <SidePanelLayout
              :sections="sections.data"
              doctype="CRM Estimation"
              :docname="estimationId"
              @reload="sections.reload"
            />
          </div>
          <DataFields doctype="CRM Estimation" :docname="estimationId" />
        </div>

        <div v-else-if="tab.name === 'Route'" class="flex-1 overflow-y-auto px-3 py-6">
          <EstimationRoute :docname="estimationId" />
        </div>

        <Activities
          v-else
          ref="activities"
          v-model:reload="reload"
          v-model:tabIndex="tabIndex"
          doctype="CRM Estimation"
          :docname="estimationId"
          :tabs="tabs"
        />
      </template>
    </Tabs>
  </div>

  <ErrorPage
    v-else-if="errorTitle"
    :errorTitle="errorTitle"
    :errorMessage="errorMessage"
  />

  <FilesUploader
    v-model="showFilesUploader"
    doctype="CRM Estimation"
    :docname="estimationId"
    @after="
      () => {
        activities?.all_activities?.reload()
        changeTabTo('Attachments')
      }
    "
  />
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  createDocumentResource,
  createResource,
  Breadcrumbs,
  Button,
  Tabs,
} from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
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
import EstimationRoute from '@/components/Estimation/EstimationRoute.vue'
import { getView } from '@/utils/view'
import { useDocument } from '@/data/document'
import { useActiveTabManager } from '@/composables/useActiveTabManager'

const router = useRouter()
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
if (!gridDoc.fieldPropertyOverrides) gridDoc.fieldPropertyOverrides = {}
gridDoc.fieldPropertyOverrides['revenue_items.type_id'] = {
  link_filters: JSON.stringify({ item_category: 'Revenue' }),
}
gridDoc.fieldPropertyOverrides['expense_items.type_id'] = {
  link_filters: JSON.stringify({ item_category: 'Expense' }),
}

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
  { name: 'Route', label: __('Route'), icon: DetailsIcon },
  { name: 'Activity', label: __('Activity'), icon: ActivityIcon },
  { name: 'Comments', label: __('Comments'), icon: CommentIcon },
  { name: 'Notes', label: __('Notes'), icon: NoteIcon },
  { name: 'Attachments', label: __('Attachments'), icon: AttachmentIcon },
])

const { tabIndex } = useActiveTabManager(tabs, 'lastEstimationTab')

function changeTabTo(name) {
  const idx = tabs.value.findIndex((t) => t.name === name)
  if (idx >= 0) tabIndex.value = idx
}

function deleteEstimation() {
  if (confirm(__('Delete this estimation?'))) {
    estimation.delete.submit().then(() => {
      router.push({ name: 'Estimations' })
    })
  }
}
</script>
