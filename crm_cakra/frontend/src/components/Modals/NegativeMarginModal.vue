<template>
  <Dialog v-model="show" :options="{ title: __('Margin minus') }">
    <template #body-content>
      <div class="-mt-3 mb-4 text-p-base text-ink-gray-7">
        {{
          __('Margin quotation ini {0}. Tulis alasannya dulu sebelum dicetak.', [
            formattedMargin,
          ])
        }}
      </div>
      <div class="mb-2 text-sm text-ink-gray-5">
        {{ __('Alasan') }}
        <span class="text-ink-red-2">*</span>
      </div>
      <FormControl
        type="textarea"
        :value="reasonText"
        @change="(e) => (reasonText = e.target.value)"
      />
    </template>
    <template #actions>
      <div class="flex items-center justify-between gap-2">
        <ErrorMessage :message="error" />
        <div class="flex gap-2">
          <Button :label="__('Batal')" @click="show = false" />
          <Button
            variant="solid"
            :label="__('Simpan')"
            :loading="saving"
            @click="save"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { Dialog, ErrorMessage, FormControl, call } from 'frappe-ui'
import { computed, ref } from 'vue'

const props = defineProps({
  quotationId: { type: String, required: true },
  margin: { type: Number, default: 0 },
  reason: { type: String, default: '' },
})

const emit = defineEmits(['submitted'])
const show = defineModel({ type: Boolean })

const reasonText = ref(props.reason)
const error = ref('')
const saving = ref(false)

const formattedMargin = computed(() =>
  new Intl.NumberFormat('id-ID', { maximumFractionDigits: 0 }).format(
    props.margin,
  ),
)

async function save() {
  if (!reasonText.value.trim()) {
    error.value = __('Alasannya wajib diisi.')
    return
  }
  saving.value = true
  try {
    await call(
      'crm_cakra.fcrm.doctype.crm_quotation.crm_quotation.submit_negative_margin_reason',
      { quotation: props.quotationId, reason: reasonText.value },
    )
    error.value = ''
    show.value = false
    emit('submitted')
  } finally {
    saving.value = false
  }
}
</script>
