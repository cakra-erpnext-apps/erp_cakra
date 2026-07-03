<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs" />
    </template>
    <template #right-header>
      <Button :label="__('Cancel')" @click="cancel" />
      <Button
        variant="solid"
        :label="__('Create')"
        :loading="creating"
        @click="createInquiry"
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
        :data="inquiry.doc"
        doctype="CRM Inquiry"
      />

      <ErrorMessage v-if="error" class="mt-4" :message="__(error)" />
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import FieldLayout from '@/components/FieldLayout/FieldLayout.vue'
import LoadingIndicator from '@/components/Icons/LoadingIndicator.vue'
import { Breadcrumbs, Button, ErrorMessage, createResource } from 'frappe-ui'
import { useDocument } from '@/data/document'
import { usersStore } from '@/stores/users'
import { statusesStore } from '@/stores/statuses'
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const router = useRouter()
const route = useRoute()
const error = ref(null)
const creating = ref(false)
const { getUser } = usersStore()
const { statusOptions } = statusesStore()

// Dokumen baru (CRM Inquiry = Inquiry).
const { document: inquiry } = useDocument('CRM Inquiry')

// Cache dokumen "new" (key '') di data/document.js persist antar navigasi, jadi
// tanpa reset form New Inquiry membawa data inquiry sebelumnya. Reset ke kosong.
inquiry.doc = { __newDocument: true, doctype: 'CRM Inquiry' }
inquiry.fieldPropertyOverrides = {}

const breadcrumbs = computed(() => [
  { label: __('Inquiries'), route: { name: 'Inquiries' } },
  { label: __('New Inquiry') },
])

const inquiryStatuses = computed(() => statusOptions('inquiry'))

// Layout yang SAMA dengan field yang di-set untuk inquiry (Data Fields).
const tabs = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout',
  cache: ['NewInquiry', 'CRM Inquiry'],
  params: { doctype: 'CRM Inquiry', type: 'Data Fields' },
  auto: true,
  transform: (_tabs) => {
    _tabs.forEach((tab) =>
      tab.sections.forEach((s) =>
        s.columns.forEach((c) =>
          c.fields.forEach((f) => {
            if (f.fieldtype === 'Table' && !inquiry.doc[f.fieldname]) {
              inquiry.doc[f.fieldname] = []
            }
          }),
        ),
      ),
    )
    return _tabs
  },
})

onMounted(() => {
  // Default dari query (mis. klik "+" di kolom kanban).
  if (route.query && Object.keys(route.query).length) {
    Object.assign(inquiry.doc, route.query)
  }
  if (!inquiry.doc.inquiry_owner) inquiry.doc.inquiry_owner = getUser().name
  // Status wajib tapi tidak ada di layout → default ke status pertama.
  if (!inquiry.doc.status && inquiryStatuses.value?.[0]?.value) {
    inquiry.doc.status = inquiryStatuses.value[0].value
  }
  if (!inquiry.doc.currency) inquiry.doc.currency = 'IDR'
  if (!inquiry.doc.exchange_rate) inquiry.doc.exchange_rate = 1
})

function createInquiry() {
  error.value = null
  const doc = { ...inquiry.doc, doctype: 'CRM Inquiry' }
  delete doc.__newDocument

  creating.value = true
  createResource({
    url: 'frappe.client.insert',
    params: { doc },
    auto: true,
    onSuccess(d) {
      creating.value = false
      router.push({ name: 'Inquiry', params: { inquiryId: d.name } })
    },
    onError(err) {
      creating.value = false
      error.value =
        err.messages?.join('\n') || err.message || __('Failed to create inquiry')
    },
  })
}

function cancel() {
  router.push({ name: 'Inquiries' })
}
</script>
