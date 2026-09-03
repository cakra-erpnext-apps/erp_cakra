<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="[{ label: __('Procurement'), route: { name: 'Procurement' } }]" />
    </template>
    <template #right-header>
      <Button :label="__('Refresh')" :iconLeft="LucideRefreshCcw" @click="discussions.reload" />
    </template>
  </LayoutHeader>

  <div class="flex-1 overflow-y-auto">
    <div v-if="discussions.data?.length" class="min-w-[800px]">
      <!-- Header kolom, mengikuti gaya list view CRM -->
      <div
        class="sticky top-0 z-10 grid grid-cols-[1.1fr_1.4fr_0.6fr_0.7fr_1.8fr_0.5fr_0.7fr] gap-3 border-b bg-surface-white px-5 py-2 text-sm text-ink-gray-5"
      >
        <div>{{ __('Quotation') }}</div>
        <div>{{ __('Account') }}</div>
        <div>{{ __('Status') }}</div>
        <div>{{ __('Costing') }}</div>
        <div>{{ __('Last Comment') }}</div>
        <div class="text-center">{{ __('Comments') }}</div>
        <div class="text-right">{{ __('Updated') }}</div>
      </div>

      <router-link
        v-for="d in discussions.data"
        :key="d.name"
        :to="{ name: 'Quotation', params: { quotationId: d.name } }"
        class="grid grid-cols-[1.1fr_1.4fr_0.6fr_0.7fr_1.8fr_0.5fr_0.7fr] items-center gap-3 border-b border-outline-gray-modals px-5 py-3 hover:bg-surface-gray-1"
        @click="rememberProcurementTab"
      >
        <!-- Quotation -->
        <div class="min-w-0">
          <div class="truncate text-base font-medium text-ink-gray-9">
            {{ d.name }}
          </div>
        </div>

        <!-- Account + subject -->
        <div class="min-w-0">
          <div class="truncate text-base text-ink-gray-8">
            {{ d.account_name || '-' }}
          </div>
          <div v-if="d.subject" class="truncate text-sm text-ink-gray-5">
            {{ d.subject }}
          </div>
        </div>

        <!-- Status -->
        <div>
          <Badge :label="d.state || 'Draft'" :theme="stateTheme(d.state)" variant="subtle" />
        </div>

        <!-- Sudah/belum dihargai Procurement -->
        <div>
          <Badge
            :label="costing(d).label"
            :theme="costing(d).theme"
            variant="subtle"
          />
        </div>

        <!-- Komentar terakhir -->
        <div class="flex min-w-0 items-center gap-2">
          <template v-if="d.last_comment">
            <UserAvatar :user="d.last_owner_email" size="sm" class="shrink-0" />
            <div class="min-w-0 truncate text-base text-ink-gray-7">
              <span class="font-medium text-ink-gray-8">{{ d.last_owner }}:</span>
              {{ excerpt(d.last_comment) }}
            </div>
          </template>
          <span v-else class="text-base text-ink-gray-4">
            {{ __('Belum ada diskusi') }}
          </span>
        </div>

        <!-- Jumlah komentar -->
        <div class="flex items-center justify-center gap-1 text-base text-ink-gray-7">
          <LucideMessageCircle class="size-4 text-ink-gray-5" />
          {{ d.comments }}
        </div>

        <!-- Waktu -->
        <div class="text-right text-sm text-ink-gray-5">
          {{ __(timeAgo(d.last_at)) }}
        </div>
      </router-link>
    </div>

    <div
      v-else-if="!discussions.loading"
      class="flex h-full flex-col items-center justify-center gap-1 text-ink-gray-5"
    >
      <LucideMessageCircle class="mb-2 size-10 text-ink-gray-4" />
      <div class="text-base font-medium">{{ __('Belum ada quotation') }}</div>
      <div class="text-sm">
        {{ __('Quotation yang dibuat akan langsung muncul di sini untuk diproses.') }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { createResource, Breadcrumbs, Button, Badge, usePageMeta } from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import LucideRefreshCcw from '~icons/lucide/refresh-ccw'
import LucideMessageCircle from '~icons/lucide/message-circle'
import { timeAgo } from '@/utils'

const discussions = createResource({
  url: 'crm_cakra.api.procurement.get_discussions',
  cache: 'procurement_discussions',
  auto: true,
})

// Warna badge mengikuti warna status di halaman Quotation.
function stateTheme(state) {
  return (
    {
      Draft: 'gray',
      Sent: 'blue',
      Waiting: 'orange',
      Win: 'green',
      Lose: 'red',
      Converted: 'green',
    }[state] || 'gray'
  )
}

// Penanda pekerjaan Procurement: semua item sudah punya Base Price atau belum.
function costing(d) {
  if (!d.items) return { label: __('No Item'), theme: 'gray' }
  if (!d.priced) return { label: __('Perlu Diproses'), theme: 'orange' }
  if (d.priced < d.items)
    return { label: `${d.priced}/${d.items}`, theme: 'blue' }
  return { label: __('Done'), theme: 'green' }
}

function excerpt(html) {
  return (html || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
}

// Supaya klik dari sini langsung mendarat di tab Procurement quotation-nya.
function rememberProcurementTab() {
  localStorage.setItem('lastQuotationTab', 'procurement')
}

usePageMeta(() => ({ title: __('Procurement') }))
</script>
