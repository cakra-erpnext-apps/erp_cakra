<template>
  <div class="h-full w-full">
    <!-- item.data bisa null bila chart tidak punya fungsi backend-nya. Tooltip dulu
         membaca item.data.tooltip TANPA penjagaan, sehingga satu chart bermasalah
         menjatuhkan seluruh dashboard ("Cannot read properties of undefined"). -->
    <div
      v-if="item.type == 'number_chart' && item.data"
      class="flex h-full w-full rounded shadow overflow-hidden cursor-pointer"
    >
      <Tooltip :text="__(item.data.tooltip)">
        <NumberChart :key="index" class="!items-start" :config="item.data" />
      </Tooltip>
    </div>
    <div
      v-else-if="item.type == 'spacer'"
      class="rounded bg-surface-white h-full overflow-hidden text-ink-gray-5 flex items-center justify-center"
      :class="editing ? 'border border-dashed border-outline-gray-2' : ''"
    >
      {{ editing ? __('Spacer') : '' }}
    </div>
    <div
      v-else-if="item.type == 'axis_chart'"
      class="h-full w-full rounded-md bg-surface-white shadow"
    >
      <!-- Chart tanpa baris data TIDAK boleh dirender: chart trend membangun
           `series` dari datanya, dan AxisChart error bila series kosong (terjadi
           saat filter user/branch tidak punya data). Tampilkan placeholder. -->
      <AxisChart v-if="hasRows" :config="item.data" />
      <EmptyChart v-else-if="item.data" :title="item.data.title" />
    </div>
    <div
      v-else-if="item.type == 'donut_chart'"
      class="h-full w-full rounded-md bg-surface-white shadow overflow-hidden"
    >
      <DonutChart v-if="hasRows" :config="item.data" />
      <EmptyChart v-else-if="item.data" :title="item.data.title" />
    </div>
    <div
      v-else-if="item.type == 'outstanding_table'"
      class="h-full w-full overflow-hidden rounded-md bg-surface-white shadow"
    >
      <OutstandingTable v-if="item.data" :config="item.data" />
    </div>
  </div>
</template>
<script setup>
import { computed, h } from 'vue'
import { AxisChart, DonutChart, NumberChart, Tooltip } from 'frappe-ui'
import OutstandingTable from '@/components/Dashboard/OutstandingTable.vue'

const props = defineProps({
  index: { type: Number, required: true },
  item: { type: Object, required: true },
  editing: { type: Boolean, default: false },
})

const hasRows = computed(
  () =>
    Array.isArray(props.item?.data?.data) && props.item.data.data.length > 0,
)

// Placeholder ringan untuk chart yang datanya kosong (mis. setelah filter
// user/branch): judul tetap tampil supaya user tahu chart apa yang kosong.
const EmptyChart = (p) =>
  h(
    'div',
    { class: 'flex h-full flex-col items-center justify-center gap-1 p-4 text-center' },
    [
      h('div', { class: 'text-sm font-medium text-ink-gray-6' }, __(p.title || '')),
      h('div', { class: 'text-sm text-ink-gray-4' }, __('No data for this filter')),
    ],
  )
EmptyChart.props = { title: { type: String, default: '' } }
</script>
