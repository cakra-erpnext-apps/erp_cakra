<template>
  <div class="flex h-full flex-col overflow-hidden">
    <div class="shrink-0 px-4 pt-3">
      <div class="text-base font-semibold text-ink-gray-8">
        {{ __(config.title) }}
      </div>
      <div v-if="config.subtitle" class="text-xs text-ink-gray-5">
        {{ __(config.subtitle) }}
      </div>
    </div>

    <div
      v-if="!rows.length"
      class="flex flex-1 items-center justify-center text-sm text-ink-gray-4"
    >
      {{ __('No outstanding quotations') }}
    </div>

    <div v-else class="mt-2 flex-1 overflow-auto px-2 pb-2">
      <table class="w-full text-xs">
        <thead
          class="sticky top-0 bg-surface-white text-ink-gray-5 shadow-[0_1px_0_0_var(--surface-gray-2)]"
        >
          <tr>
            <th class="px-2 py-1.5 text-left font-medium">{{ __('Quotation') }}</th>
            <th class="px-2 py-1.5 text-left font-medium">{{ __('Account') }}</th>
            <th class="px-2 py-1.5 text-left font-medium">{{ __('Status') }}</th>
            <th class="px-2 py-1.5 text-right font-medium">{{ __('Value') }}</th>
            <th class="px-2 py-1.5 text-right font-medium">{{ __('Age') }}</th>
            <th class="px-2 py-1.5 text-right font-medium">{{ __('Expires') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.name"
            class="cursor-pointer border-t border-outline-gray-1 hover:bg-surface-gray-1"
            @click="open(row.name)"
          >
            <td class="whitespace-nowrap px-2 py-1.5 font-medium text-ink-gray-8">
              {{ row.name }}
            </td>
            <td class="max-w-[10rem] truncate px-2 py-1.5 text-ink-gray-7">
              {{ row.account }}
            </td>
            <td class="px-2 py-1.5">
              <span
                class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-ink-gray-7"
              >
                {{ row.status }}
              </span>
            </td>
            <td
              class="whitespace-nowrap px-2 py-1.5 text-right tabular-nums text-ink-gray-8"
            >
              {{ money(row) }}
            </td>
            <td
              class="whitespace-nowrap px-2 py-1.5 text-right tabular-nums text-ink-gray-6"
            >
              {{ row.age_days == null ? '-' : `${row.age_days}d` }}
            </td>
            <td
              class="whitespace-nowrap px-2 py-1.5 text-right tabular-nums"
              :class="expiryClass(row.days_left)"
            >
              {{ expiryLabel(row.days_left) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  config: { type: Object, required: true },
})

const router = useRouter()
const rows = computed(() => props.config?.data || [])

function open(name) {
  router.push({ name: 'Quotation', params: { quotationId: name } })
}

function money(row) {
  const value = Number(row.value || 0)
  return `${row.currency || ''} ${value.toLocaleString('id-ID', {
    maximumFractionDigits: 0,
  })}`.trim()
}

// Hitung mundur kadaluarsa. Negatif = sudah lewat, dan itu yang paling mendesak.
function expiryLabel(daysLeft) {
  if (daysLeft == null) return '-'
  if (daysLeft < 0) return __('Expired')
  if (daysLeft === 0) return __('Today')
  return `${daysLeft}d`
}

function expiryClass(daysLeft) {
  if (daysLeft == null) return 'text-ink-gray-4'
  if (daysLeft < 0) return 'font-medium text-ink-red-3'
  if (daysLeft <= 7) return 'font-medium text-ink-amber-3'
  return 'text-ink-gray-6'
}
</script>
