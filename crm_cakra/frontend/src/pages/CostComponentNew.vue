<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs" />
    </template>
    <template #right-header>
      <Button :label="__('Cancel')" @click="cancel" />
      <Button
        variant="solid"
        :label="__('Save')"
        :loading="creating"
        @click="createComponent"
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
        :data="component.doc"
        doctype="CRM Cost Component"
      />

      <ErrorMessage v-if="error" class="mt-4" :message="__(error)" />
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import FieldLayout from '@/components/FieldLayout/FieldLayout.vue'
import LoadingIndicator from '@/components/Icons/LoadingIndicator.vue'
import { Breadcrumbs, Button, ErrorMessage, createResource, toast } from 'frappe-ui'
import { useDocument } from '@/data/document'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const error = ref(null)
const creating = ref(false)

const { document: component } = useDocument('CRM Cost Component')

// Cache dokumen "new" (key '') persist antar navigasi, jadi tanpa reset form
// baru membawa isian sebelumnya.
component.doc = {
  __newDocument: true,
  doctype: 'CRM Cost Component',
  type: 'Variable Cost',
  date: new Date().toISOString().slice(0, 10),
  items: [],
}
component.fieldPropertyOverrides = {}

const breadcrumbs = computed(() => [
  { label: __('Cost Components'), route: { name: 'CostComponents' } },
  { label: __('New Cost Component') },
])

// Layout yang SAMA dengan halaman detail.
const tabs = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout',
  params: { doctype: 'CRM Cost Component', type: 'Data Fields' },
  auto: true,
  transform: (_tabs) => {
    // Field Table harus berupa array sebelum grid bisa dirender.
    _tabs.forEach((tab) =>
      tab.sections.forEach((s) =>
        s.columns.forEach((c) =>
          c.fields.forEach((f) => {
            if (f.fieldtype === 'Table' && !component.doc[f.fieldname]) {
              component.doc[f.fieldname] = []
            }
          }),
        ),
      ),
    )
    return _tabs
  },
})

// Total mengikuti isi tabel secara langsung, tanpa menunggu save.
watch(
  () => (component.doc.items || []).map((i) => `${i.qty}|${i.rate}`).join(';'),
  () => {
    let total = 0
    ;(component.doc.items || []).forEach((i) => {
      i.amount = (Number(i.qty) || 0) * (Number(i.rate) || 0)
      total += i.amount
    })
    component.doc.total_amount = total
  },
)

function createComponent() {
  error.value = null
  const doc = { ...component.doc, doctype: 'CRM Cost Component' }
  delete doc.__newDocument

  creating.value = true
  createResource({
    url: 'frappe.client.insert',
    params: { doc },
    auto: true,
    onSuccess(d) {
      creating.value = false
      router.push({ name: 'CostComponent', params: { componentId: d.name } })
    },
    onError(err) {
      creating.value = false
      error.value =
        err.messages?.join('\n') || err.message || __('Failed to create cost component')
      toast.error(error.value)
    },
  })
}

function cancel() {
  router.push({ name: 'CostComponents' })
}
</script>
