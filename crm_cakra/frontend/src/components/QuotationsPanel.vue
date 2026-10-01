<template>
  <div class="px-2 pb-3">
    <div
      v-if="!quotations.data?.length"
      class="py-2 text-base text-ink-gray-5"
    >
      {{ __('Belum ada quotation untuk inquiry ini.') }}
    </div>

    <div v-else class="flex flex-col gap-1.5">
      <router-link
        v-for="q in quotations.data"
        :key="q.name"
        :to="{ name: 'Quotation', params: { quotationId: q.name } }"
        class="flex flex-col gap-1 rounded border border-outline-gray-modals px-2.5 py-2 hover:bg-surface-gray-2"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="truncate text-base font-medium text-ink-gray-8">
            {{ q.name }}
          </span>
          <Badge
            :label="q.state"
            :theme="STATE_THEME[q.state] || 'gray'"
            variant="subtle"
            size="sm"
          />
        </div>
        <div class="flex items-center justify-between gap-2 text-sm text-ink-gray-5">
          <span>{{ q.date ? formatDate(q.date) : '' }}</span>
          <span class="tabular-nums">{{ money(q.net_total) }}</span>
        </div>
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { Badge, createResource } from 'frappe-ui'
import { formatDate, money } from '@/utils'

const props = defineProps({
  inquiry: { type: String, required: true },
})

const STATE_THEME = {
  Draft: 'gray',
  Inquired: 'gray',
  'Follow Up': 'orange',
  Negotiation: 'blue',
  Win: 'green',
  Lose: 'red',
  Converted: 'green',
}

// Dibaca lewat get_list biasa supaya penyaringan akses per branch tetap berlaku:
// quotation milik cabang lain tidak ikut muncul walau inquiry-nya sama.
const quotations = createResource({
  url: 'frappe.client.get_list',
  params: {
    doctype: 'CRM Quotation',
    filters: { inquiry: props.inquiry },
    fields: ['name', 'state', 'date', 'net_total'],
    order_by: 'creation desc',
    limit_page_length: 0,
  },
  auto: true,
})
</script>
