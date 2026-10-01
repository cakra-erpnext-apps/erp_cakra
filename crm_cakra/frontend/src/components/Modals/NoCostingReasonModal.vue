<template>
  <Dialog
    v-model="show"
    :options="{ title: __('Quotation tanpa costing procurement') }"
  >
    <template #body-content>
      <div class="flex flex-col gap-4">
        <p class="text-p-base text-ink-gray-6">
          {{
            __(
              'Costing untuk inquiry ini belum disetujui procurement. Sebutkan alasannya supaya penawaran tanpa perhitungan tetap bisa ditelusuri.',
            )
          }}
        </p>

        <div>
          <label class="mb-1.5 block text-xs text-ink-gray-5">
            {{ __('Alasan') }}
            <span class="text-ink-red-2">*</span>
          </label>
          <Link
            v-model="reason"
            doctype="CRM No Costing Reason"
            :placeholder="__('Pilih alasan...')"
          />
        </div>

        <FormControl
          v-model="notes"
          type="textarea"
          :rows="4"
          :label="__('Keterangan')"
          :placeholder="__('Penjelasan singkat, mis. permintaan mendesak dari customer')"
        />
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Batal')" @click="show = false" />
        <Button
          variant="solid"
          :label="__('Lanjut Buat Quotation')"
          :disabled="!reason"
          @click="lanjut"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import Link from '@/components/Controls/Link.vue'
import { Dialog, FormControl, Button } from 'frappe-ui'
import { ref, watch } from 'vue'

const emit = defineEmits(['confirm'])
const show = defineModel({ type: Boolean })

const reason = ref(null)
const notes = ref('')

// Dikosongkan tiap kali dibuka: alasan penawaran berikutnya belum tentu sama,
// dan alasan lama yang tertinggal di kotak akan ikut tersimpan tanpa disadari.
watch(show, (terbuka) => {
  if (terbuka) {
    reason.value = null
    notes.value = ''
  }
})

function lanjut() {
  if (!reason.value) return
  emit('confirm', { reason: reason.value, notes: notes.value.trim() })
  show.value = false
}
</script>
