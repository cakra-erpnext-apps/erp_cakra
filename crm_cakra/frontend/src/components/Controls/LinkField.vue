<template>
  <div>
    <label v-if="label" class="mb-1.5 block text-xs text-ink-gray-5">{{ __(label) }}</label>
    <Link class="form-control" :doctype="doctype" :value="modelValue" :filters="filters"
      @change="(v) => emit('update:modelValue', v || '')" />
  </div>
</template>

<script setup>
// Bungkus Controls/Link.vue jadi v-model + label, karena FormControl type="autocomplete"
// tidak mengambil opsi dari doctype (dropdown kosong).
import Link from '@/components/Controls/Link.vue'

defineProps({
  label: { type: String, default: '' },
  doctype: { type: String, required: true },
  modelValue: { type: String, default: '' },
  filters: { type: [Array, Object, String], default: () => [] },
})
const emit = defineEmits(['update:modelValue'])
</script>
