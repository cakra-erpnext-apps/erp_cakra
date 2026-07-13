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
      {{ __('Nothing outstanding') }}
    </div>

    <!-- Scroll dua arah: kolom tabel sekarang banyak (branch, rute, owner, dst.),
         jadi tabel memakai lebar naturalnya dan digulir horizontal bila sempit. -->
    <div v-else class="themed-scroll mt-2 flex-1 overflow-auto px-2 pb-2">
      <table class="w-max min-w-full text-xs">
        <thead
          class="sticky top-0 bg-surface-white text-ink-gray-5 shadow-[0_1px_0_0_var(--surface-gray-2)]"
        >
          <tr>
            <th
              v-for="col in columns"
              :key="col.key"
              class="whitespace-nowrap px-2 py-1.5 font-medium"
              :class="col.align === 'right' ? 'text-right' : 'text-left'"
            >
              {{ __(col.label) }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.name"
            class="cursor-pointer border-t border-outline-gray-1 hover:bg-surface-gray-1"
            @click="open(row.name)"
          >
            <td
              v-for="col in columns"
              :key="col.key"
              class="px-2 py-1.5"
              :class="cellClass(col, row)"
            >
              <span
                v-if="col.type === 'badge'"
                class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-ink-gray-7"
              >
                {{ row[col.key] }}
              </span>
              <template v-else>{{ cellText(col, row) }}</template>
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
const columns = computed(() => props.config?.columns || [])

function open(name) {
  const route = props.config?.route
  const param = props.config?.routeParam
  if (!route || !param) return
  router.push({ name: route, params: { [param]: name } })
}

function money(row) {
  const value = Number(row.value || 0)
  return `${row.currency || ''} ${value.toLocaleString('id-ID', {
    maximumFractionDigits: 0,
  })}`.trim()
}

// Hitung mundur kadaluarsa. Negatif = sudah lewat, dan itu yang paling mendesak.
function expiry(days) {
  if (days == null) return '-'
  if (days < 0) return __('Expired')
  if (days === 0) return __('Today')
  return `${days}d`
}

function cellText(col, row) {
  const value = row[col.key]
  if (col.type === 'money') return money(row)
  if (col.type === 'expiry') return expiry(value)
  if (col.type === 'days') return value == null ? '-' : `${value}d`
  return value ?? '-'
}

function cellClass(col, row) {
  const base = [col.align === 'right' ? 'text-right tabular-nums' : '']
  if (col.type === 'id') base.push('whitespace-nowrap font-medium text-ink-gray-8')
  else if (col.type === 'truncate') base.push('max-w-[10rem] truncate text-ink-gray-7')
  else if (col.type === 'money') base.push('whitespace-nowrap text-ink-gray-8')
  else if (col.type === 'days') base.push('whitespace-nowrap text-ink-gray-6')
  else if (col.type === 'expiry') base.push('whitespace-nowrap', expiryTone(row[col.key]))
  return base
}

// Merah = mendesak: sudah lewat, hari ini, atau tinggal 1 hari lagi.
function expiryTone(days) {
  if (days == null) return 'text-ink-gray-4'
  if (days <= 1) return 'font-medium text-ink-red-3'
  if (days <= 7) return 'font-medium text-ink-amber-3'
  return 'text-ink-gray-6'
}
</script>
