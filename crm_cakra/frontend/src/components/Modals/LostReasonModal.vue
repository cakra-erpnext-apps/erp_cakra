<template>
  <Dialog
    v-model="show"
    :options="{ title: __('Lost Reason') }"
    @close="cancel"
  >
    <template #body-content>
      <div class="-mt-3 mb-4 text-p-base text-ink-gray-7">
        {{
          __('Please provide a reason for marking this {0} as lost', [
            doctype.toLowerCase().replace('crm ', ''),
          ])
        }}
      </div>
      <div class="flex flex-col gap-3">
        <div>
          <div class="mb-2 text-sm text-ink-gray-5">
            {{ __('Lost Notes') }}
            <span class="text-ink-red-2">*</span>
          </div>
          <FormControl
            class="form-control flex-1 truncate"
            type="textarea"
            :value="lostNotes"
            @change="(e) => (lostNotes = e.target.value)"
          />
        </div>
      </div>
    </template>
    <template #actions>
      <div class="flex justify-between items-center gap-2">
        <div><ErrorMessage :message="error" /></div>
        <div class="flex gap-2">
          <Button :label="__('Cancel')" @click="cancel" />
          <Button variant="solid" :label="__('Save')" @click="save" />
        </div>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
import { Dialog } from 'frappe-ui'
import { ref } from 'vue'

const props = defineProps({
  doctype: { type: String, default: 'CRM Lead' },
  // Wajib untuk pemakaian bawaan (Lead / Inquiry): alasan ditulis ke dokumen ini.
  document: { type: Object, default: null },
  // Bila diisi, modal hanya mengumpulkan alasan lalu menyerahkan penyimpanan ke
  // pemanggil. Dipakai Quotation, yang menulis alasannya ke inquiry — bukan ke
  // dirinya sendiri — dan tidak punya field `status` untuk dipulihkan saat batal.
  onSave: { type: Function, default: null },
})

const show = defineModel({ type: Boolean })

const doc = props.document?.doc || {}
const lostNotes = ref(doc.lost_notes || '')
const error = ref('')

function cancel() {
  show.value = false
  error.value = ''
  lostNotes.value = ''
  if (!props.onSave && props.document) {
    doc.status = props.document.originalDoc.status
  }
}

function save() {
  // Master CRM Lost Reason tidak lagi dipakai: alasannya ditulis bebas di sini,
  // jadi catatannya yang wajib -- tanpa itu modal ini tidak mengumpulkan apa pun.
  if (!lostNotes.value.trim()) {
    error.value = __('Lost Notes is required')
    return
  }

  error.value = ''
  show.value = false

  if (props.onSave) {
    props.onSave({ lostNotes: lostNotes.value })
    return
  }

  doc.lost_notes = lostNotes.value
  props.document.save.submit()
}
</script>
