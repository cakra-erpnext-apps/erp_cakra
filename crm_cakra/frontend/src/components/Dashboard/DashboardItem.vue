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
      <AxisChart v-if="item.data" :config="item.data" />
    </div>
    <div
      v-else-if="item.type == 'donut_chart'"
      class="h-full w-full rounded-md bg-surface-white shadow overflow-hidden"
    >
      <DonutChart v-if="item.data" :config="item.data" />
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
import { AxisChart, DonutChart, NumberChart, Tooltip } from 'frappe-ui'
import OutstandingTable from '@/components/Dashboard/OutstandingTable.vue'

defineProps({
  index: { type: Number, required: true },
  item: { type: Object, required: true },
  editing: { type: Boolean, default: false },
})
</script>
