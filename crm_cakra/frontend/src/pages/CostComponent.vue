<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs" />
    </template>
    <template v-if="component.doc?.name" #right-header>
      <Badge :label="__(status)" :theme="statusTheme" variant="subtle" />
      <Button
        v-if="status !== 'Validated'"
        variant="solid"
        theme="green"
        :label="__('Validate')"
        :loading="acting"
        @click="setValidation('validate')"
      />
      <Button
        v-else
        :label="__('Invalidate')"
        :loading="acting"
        @click="setValidation('invalidate')"
      />
      <Button
        :tooltip="__('Delete')"
        variant="subtle"
        icon="trash-2"
        theme="red"
        @click="deleteComponent"
      />
    </template>
  </LayoutHeader>

  <div v-if="component.doc?.name" class="flex-1 overflow-y-auto px-5 pb-8">
    <div class="mx-auto max-w-4xl">
      <DataFields
        doctype="CRM Cost Component"
        :docname="props.componentId"
        @afterSave="followRename"
      />
    </div>
  </div>

  <ErrorPage v-else-if="errorTitle" :errorTitle="errorTitle" :errorMessage="errorMessage" />
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createDocumentResource, Breadcrumbs, Button, Badge, call, toast } from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import ErrorPage from '@/components/ErrorPage.vue'
import DataFields from '@/components/Activities/DataFields.vue'
import { useDocument } from '@/data/document'

const router = useRouter()

const props = defineProps({
  componentId: { type: String, required: true },
})

const errorTitle = ref('')
const errorMessage = ref('')

const component = createDocumentResource({
  doctype: 'CRM Cost Component',
  name: props.componentId,
  cache: ['cost_component', props.componentId],
  auto: true,
  onError(err) {
    errorTitle.value = __(
      err.exc_type === 'DoesNotExistError' ? 'Cost Component Not Found' : 'Error',
    )
    errorMessage.value = __(err.messages?.[0] || 'An Error Occurred')
  },
})

// Dokumen yang sama dengan yang dipakai DataFields, supaya total ikut bergerak
// saat tabel diedit -- tanpa ini angkanya baru benar setelah save.
const { document: doc } = useDocument('CRM Cost Component', props.componentId)

watch(
  () => (doc.doc?.items || []).map((i) => `${i.qty}|${i.rate}`).join(';'),
  () => {
    if (!doc.doc) return
    let total = 0
    doc.doc.items.forEach((i) => {
      i.amount = (Number(i.qty) || 0) * (Number(i.rate) || 0)
      total += i.amount
    })
    doc.doc.total_amount = total
  },
)

// Status dibaca dari dokumen yang sedang diedit DataFields, bukan dari resource
// header -- supaya badge langsung ikut berubah setelah Validate/Invalidate.
const status = computed(() => doc.doc?.status || component.doc?.status || 'Draft')
const statusTheme = computed(
  () => ({ Validated: 'green', Invalidated: 'red' })[status.value] || 'gray',
)

const acting = ref(false)

async function setValidation(action) {
  acting.value = true
  try {
    const res = await call(
      'crm_cakra.fcrm.doctype.crm_cost_component.crm_cost_component.set_validation',
      { name: props.componentId, action },
    )
    if (doc.doc) Object.assign(doc.doc, res)
    if (doc.originalDoc) Object.assign(doc.originalDoc, res)
    component.reload()
    toast.success(__('Status: {0}', [res.status]))
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Failed'))
  } finally {
    acting.value = false
  }
}

const breadcrumbs = computed(() => [
  { label: __('Cost Components'), route: { name: 'CostComponents' } },
  { label: component.doc?.component_name || props.componentId },
])

// Component Name adalah nama dokumennya: mengubahnya = dokumen di-rename server.
// URL halaman ini masih menunjuk nama lama, jadi harus ikut pindah -- kalau tidak,
// refresh berikutnya jatuh ke "Cost Component Not Found".
function followRename(changes) {
  const newName = changes?.component_name
  if (!newName || newName === props.componentId) return
  router.replace({ name: 'CostComponent', params: { componentId: newName } })
}

function deleteComponent() {
  if (!confirm(__('Delete this cost component?'))) return
  component.delete.submit().then(() => {
    router.push({ name: 'CostComponents' })
  })
}
</script>
