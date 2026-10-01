<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="[{ label: __('Edit File') }]" />
    </template>
  </LayoutHeader>
  <!-- Editor excel satu halaman penuh, dibuka di tab baru dari tab File Tender. -->
  <SpreadsheetView :file-name="fileName" max-height="none" class="flex-1 overflow-hidden" />
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import SpreadsheetView from '@/components/SpreadsheetView.vue'
import { Breadcrumbs } from 'frappe-ui'

defineProps({ fileName: { type: String, required: true } })
</script>
