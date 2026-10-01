<template>
  <div class="flex flex-col overflow-y-auto px-5 py-4">
    <div class="mb-3 flex items-center justify-between">
      <span class="text-lg font-medium text-ink-gray-8">
        {{ __('Quotations') }}
      </span>
      <Button
        :label="__('Create Quotation')"
        icon-left="plus"
        @click="createQuotation"
      />
    </div>

    <div
      v-for="q in quotations.data || []"
      :key="q.name"
      class="flex cursor-pointer items-center gap-4 rounded px-3 py-2.5 hover:bg-surface-gray-2"
      @click="router.push({ name: 'Quotation', params: { quotationId: q.name } })"
    >
      <div class="w-44 shrink-0 truncate text-base font-medium text-ink-gray-8">
        {{ q.name }}
      </div>
      <div class="min-w-0 flex-1 truncate text-base text-ink-gray-7">
        {{ q.subject || q.account_name || '' }}
      </div>
      <div class="w-28 shrink-0 text-sm text-ink-gray-5">
        {{ q.date ? formatDate(q.date, 'D MMM YYYY') : '' }}
      </div>
      <div class="w-36 shrink-0 text-right text-base text-ink-gray-8">
        {{ formatNumber(q.net_total) }} {{ q.currency }}
      </div>
      <Badge class="w-24 shrink-0 justify-center" :label="__(q.state)" />
    </div>

    <div
      v-if="quotations.data && !quotations.data.length"
      class="py-10 text-center text-sm text-ink-gray-5"
    >
      {{ __('Belum ada quotation untuk tender ini.') }}
    </div>
  </div>
</template>

<script setup>
import { Badge, Button, createResource } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { formatDate } from '@/utils'

const props = defineProps({
  tenderId: { type: String, required: true },
  inquiry: { type: String, default: '' },
})

const router = useRouter()

const quotations = createResource({
  url: 'frappe.client.get_list',
  params: {
    doctype: 'CRM Quotation',
    filters: { tender: props.tenderId },
    fields: ['name', 'subject', 'account_name', 'date', 'net_total', 'currency', 'state'],
    order_by: 'creation desc',
    limit_page_length: 0,
  },
  auto: true,
})

const formatNumber = (v) => Number(v || 0).toLocaleString('id-ID')

function createQuotation() {
  const query = { tender: props.tenderId }
  if (props.inquiry) query.inquiry = props.inquiry
  router.push({ name: 'NewQuotation', query })
}
</script>
