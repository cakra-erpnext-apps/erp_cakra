<template>
  <Dialog v-model="show" :options="{ title: __('Request Procurement') }">
    <template #body-content>
      <div class="flex flex-col gap-4">
        <div>
          <label class="mb-1.5 block text-xs text-ink-gray-5">
            {{ __('Assign To') }}
          </label>
          <div class="group rounded bg-surface-gray-2 p-2 hover:bg-surface-gray-3">
            <MultiSelectUserInput
              v-model="assignees"
              class="flex-1"
              inputClass="!bg-surface-gray-2 hover:!bg-surface-gray-3 group-hover:!bg-surface-gray-3"
              :placeholder="__('Pilih user')"
            />
          </div>
        </div>

        <FormControl
          v-model="note"
          type="textarea"
          :rows="4"
          :label="__('Note')"
          :placeholder="__('Yang perlu diketahui tim procurement')"
        />
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end">
        <Button
          variant="solid"
          :label="__('Kirim')"
          :disabled="!assignees.length"
          :loading="sending"
          @click="send"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import MultiSelectUserInput from '@/components/Controls/MultiSelectUserInput.vue'
import { call, toast } from 'frappe-ui'
import { ref, watch } from 'vue'

const props = defineProps({
  quotationId: { type: String, required: true },
})

const emit = defineEmits(['sent'])

const show = defineModel({ type: Boolean })

const assignees = ref([])
const note = ref('')
const sending = ref(false)

// Isian dikosongkan tiap kali modal dibuka: permintaan berikutnya adalah
// permintaan yang berbeda, dan catatan lama yang tertinggal di kotak akan
// terkirim lagi tanpa disadari.
watch(show, (open) => {
  if (open) {
    assignees.value = []
    note.value = ''
  }
})

async function send() {
  sending.value = true
  try {
    await call('crm_cakra.api.procurement.request_procurement', {
      quotation: props.quotationId,
      assignees: assignees.value,
      note: note.value,
    })
    show.value = false
    toast.success(__('Permintaan procurement terkirim'))
    emit('sent')
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal mengirim permintaan'))
  } finally {
    sending.value = false
  }
}
</script>
