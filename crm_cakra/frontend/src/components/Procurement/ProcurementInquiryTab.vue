<template>
  <div class="flex-1 overflow-y-auto px-3 pb-8 sm:px-10">
    <template v-if="info?.name">
      <!-- Permintaan terakhir yang dikirim. Ini yang dilihat Marketing: angka
           costing-nya di bawah hanya dirender untuk tim Procurement. -->
      <div
        class="my-5 rounded-lg border border-outline-gray-2 px-4 py-3"
      >
        <div class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-5">
          <Badge
            :label="__(info.status)"
            :theme="STATUS_THEME[info.status] || 'gray'"
            variant="subtle"
          />
          <span v-if="info.submitted_on">
            {{ __('Dikirim ke') }} {{ info.requested_to }} &middot;
            {{ formatDate(info.submitted_on) }}
          </span>
          <span v-else>{{ __('Belum dikirim ke tim procurement.') }}</span>
        </div>
        <div
          v-if="info.remark"
          class="mt-1 whitespace-pre-wrap text-base text-ink-gray-8"
        >
          {{ info.remark }}
        </div>
      </div>

      <ProcurementPanel
        :key="info.name"
        :canEdit="isProcurement() || allowCostEdit"
        :procurementId="info.name"
        :inquiry="inquiry"
      />

      <!-- Obrolan procurement, dokumen yang sama dengan panel komentar di
           halaman Procurement. Ditaruh paling bawah supaya angka costing tetap
           yang pertama terbaca, dan pemilik inquiry bisa membalas dari sini
           tanpa berpindah halaman. -->
      <div class="mt-8 h-[28rem] rounded-lg border border-outline-gray-2">
        <CommentPane doctype="CRM Procurement" :docname="info.name" />
      </div>
    </template>

    <EmptyState
      v-else
      name="Procurement"
      icon="dollar-sign"
      :title="__('Belum ada permintaan procurement')"
      :description="
        __('Tekan Submit to Procurement di atas untuk meminta harga ke tim procurement.')
      "
    />
  </div>
</template>

<script setup>
import { Badge } from 'frappe-ui'
import EmptyState from '@/components/ListViews/EmptyState.vue'
import ProcurementPanel from '@/components/Procurement/ProcurementPanel.vue'
import CommentPane from '@/components/CommentPane.vue'
import { usersStore } from '@/stores/users'
import { getSettings } from '@/stores/settings'
import { formatDate } from '@/utils'
import { computed } from 'vue'

const { isProcurement } = usersStore()
const { settings } = getSettings()

// Setting General "Allow edit in cost in inquiry - Tab Procurement": kalau
// menyala, siapa pun yang membuka tab ini boleh mengubah angka costingnya,
// bukan cuma tim Procurement.
const allowCostEdit = computed(() =>
  Boolean(settings.value?.allow_cost_edit_in_inquiry),
)

// Request = diminta Marketing, Reviewing = procurement sudah mengisi biaya,
// Approve = angkanya dinyatakan final.
const STATUS_THEME = {
  Draft: 'gray',
  Request: 'orange',
  Reviewing: 'blue',
  Approve: 'green',
}

defineProps({
  inquiry: { type: String, required: true },
  // Ringkasan dokumen CRM Procurement inquiry ini, null kalau belum ada.
  // Halamannya yang memuat -- tombol Submit di header memakai data yang sama.
  info: { type: Object, default: null },
})
</script>
