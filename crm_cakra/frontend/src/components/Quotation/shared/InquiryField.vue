<template>
  <div>
    <label class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">
      {{ label }}
    </label>
    <Autocomplete
      :modelValue="modelValue"
      :options="options"
      class="mt-1"
      :placeholder="__('Search won inquiry...')"
      @update:modelValue="onChange"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Autocomplete, createResource } from 'frappe-ui'

const props = defineProps({
  label: { type: String, default: 'Inquiry' },
  modelValue: String,
})

const emit = defineEmits(['update:modelValue', 'save', 'select'])  // ← tambah 'select'

const options = ref([])
const inquiries = ref([])  // ← simpan data inquiry lengkap

const resource = createResource({
  url: 'crm_cakra.api.quotation.get_available_inquiries',
  onSuccess(data) {
    inquiries.value = data  // ← simpan data lengkap
    options.value = data.map(d => ({
      label: `${d.name} — ${d.organization || ''}`,
      value: d.name,
    }))
  },
})

onMounted(() => {
  resource.submit()
})

function onChange(val) {
  const value = val?.value || val
  emit('update:modelValue', value)
  emit('save', value)

  // ← cari inquiry lengkap dan emit
  const selectedInquiry = inquiries.value.find(d => d.name === value)
  if (selectedInquiry) {
    emit('select', selectedInquiry)
  }
}
</script>