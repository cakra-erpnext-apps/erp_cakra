<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs" />
    </template>
    <template #right-header>
      <FileUploader :upload-args="{ private: true }" @success="(f) => files.push(f)">
        <template #default="{ openFileSelector, uploading }">
          <Button
            :label="__('Attach a File')"
            iconLeft="paperclip"
            :loading="uploading"
            @click="openFileSelector()"
          />
        </template>
      </FileUploader>
      <Button :label="__('Cancel')" @click="cancel" />
      <Button
        variant="solid"
        :label="__('Create')"
        :loading="creating"
        @click="createEstimation"
      />
    </template>
  </LayoutHeader>

  <div class="flex-1 overflow-y-auto px-5 py-6">
    <div class="mx-auto max-w-4xl">
      <div
        v-if="tabs.loading"
        class="flex flex-col items-center justify-center gap-3 py-20 text-ink-gray-5"
      >
        <LoadingIndicator class="h-6 w-6" />
        <span>{{ __('Loading...') }}</span>
      </div>

      <FieldLayout
        v-else-if="tabs.data?.length"
        :tabs="tabs.data"
        :data="estimation.doc"
        doctype="CRM Estimation"
      />

      <div v-if="files.length" class="mt-6 flex flex-col gap-1">
        <div class="mb-1 text-base font-medium text-ink-gray-8">{{ __('Attachments') }}</div>
        <div
          v-for="f in files"
          :key="f.name"
          class="flex items-center gap-2 rounded bg-surface-gray-2 px-2 py-1.5 text-base"
        >
          <span class="min-w-0 flex-1 truncate text-ink-gray-8">{{ f.file_name }}</span>
          <Button variant="ghost" icon="x" @click="files = files.filter((x) => x.name !== f.name)" />
        </div>
      </div>

      <ErrorMessage v-if="error" class="mt-4" :message="__(error)" />
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import FieldLayout from '@/components/FieldLayout/FieldLayout.vue'
import LoadingIndicator from '@/components/Icons/LoadingIndicator.vue'
import { Breadcrumbs, Button, ErrorMessage, FileUploader, call, createResource, toast } from 'frappe-ui'
import { setupShipmentRoutes } from '@/utils/shipmentRoute'
import { useDocument } from '@/data/document'
import { startNewDoc } from '@/utils/draft'
import { applyEstimationGridOverrides } from '@/utils/estimationGrid'
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const error = ref(null)
const creating = ref(false)
// Lampiran diunggah lepas dulu; ditempelkan ke estimasi setelah dokumennya ada.
const files = ref([])

const { document: estimation } = useDocument('CRM Estimation')

// Cache dokumen "new" (key '') di data/document.js persist antar navigasi, jadi
// tanpa reset form estimasi baru membawa data estimasi sebelumnya. Kalau datang
// dari Convert to Estimation, isinya sudah disiapkan server (build_estimation)
// dan dititipkan lewat sessionStorage -- dokumennya sendiri belum ada sampai
// tombol Save di halaman ini ditekan. Isian yang belum tersimpan (refresh/
// internet putus) dipulihkan.
const discardDraft = startNewDoc(estimation, 'CRM Estimation', {
  __newDocument: true,
  doctype: 'CRM Estimation',
})

const breadcrumbs = computed(() => [
  { label: __('Estimations'), route: { name: 'Estimations' } },
  { label: __('New Estimation') },
])

const tabs = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout',
  cache: ['NewEstimation', 'CRM Estimation'],
  params: { doctype: 'CRM Estimation', type: 'Data Fields' },
  auto: true,
  transform: (_tabs) => {
    _tabs.forEach((tab) =>
      tab.sections.forEach((s) =>
        s.columns.forEach((c) =>
          c.fields.forEach((f) => {
            if (f.fieldtype === 'Table' && !estimation.doc[f.fieldname]) {
              estimation.doc[f.fieldname] = []
            }
          }),
        ),
      ),
    )
    return _tabs
  },
})

onMounted(() => {
  applyEstimationGridOverrides(estimation)
  setupShipmentRoutes(estimation)

  if (!estimation.doc.effective_date) {
    estimation.doc.effective_date = new Date().toISOString().slice(0, 10)
  }
  if (!estimation.doc.purpose) estimation.doc.purpose = 'Customer'
})

function createEstimation() {
  error.value = null
  const doc = { ...estimation.doc, doctype: 'CRM Estimation' }
  delete doc.__newDocument

  creating.value = true
  createResource({
    url: 'frappe.client.insert',
    params: { doc },
    auto: true,
    async onSuccess(d) {
      try {
        await Promise.all(
          files.value.map((f) =>
            call('frappe.client.set_value', {
              doctype: 'File',
              name: f.name,
              fieldname: { attached_to_doctype: 'CRM Estimation', attached_to_name: d.name },
            }),
          ),
        )
      } catch (e) {
        toast.error(e.messages?.[0] || e.message || __('Lampiran gagal ditempelkan'))
      }
      files.value = []
      creating.value = false
      discardDraft()
      router.push({ name: 'Estimation', params: { estimationId: d.name } })
    },
    onError(err) {
      creating.value = false
      error.value =
        err.messages?.join('\n') || err.message || __('Failed to create estimation')
    },
  })
}

function cancel() {
  discardDraft()
  router.push({ name: 'Estimations' })
}
</script>
