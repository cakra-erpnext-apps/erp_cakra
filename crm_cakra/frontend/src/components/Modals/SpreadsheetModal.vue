<template>
  <Dialog v-model="show" :options="{ size: '7xl' }">
    <template #body>
      <SpreadsheetView
        v-if="show"
        :file-name="fileName"
        :label="label"
        @error="show = false"
      />
    </template>
  </Dialog>
</template>

<script setup>
import SpreadsheetView from '@/components/SpreadsheetView.vue'
import { Dialog } from 'frappe-ui'

defineProps({
  fileName: { type: String, required: true },
  label: { type: String, default: '' },
})

const show = defineModel({ type: Boolean })
</script>
