<template>
  <!-- basis-0 + grow: lebar kolom mengikuti rasio span (1 = rata, 3 = tiga kali
       lebar kolom span 1). Tanpa span, semua kolom tetap sama rata seperti dulu. -->
  <div
    class="column flex flex-col gap-4 min-w-0 grow basis-0"
    :style="{ flexGrow: column.span || 1 }"
  >
    <div
      v-if="column.label && !column.hideLabel"
      class="text-ink-gray-9 max-w-fit text-base"
    >
      {{ column.label }}
    </div>
    <template v-for="field in column.fields" :key="field.fieldname">
      <Field :field="field" :data-name="field.fieldname" />
    </template>
  </div>
</template>
<script setup>
import Field from '@/components/FieldLayout/Field.vue'

defineProps({
  column: { type: Object, required: true },
})
</script>
