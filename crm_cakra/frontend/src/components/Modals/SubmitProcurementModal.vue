<template>
  <Dialog v-model="show" :options="{ title: props.title || __('Submit to Procurement') }">
    <template #body-content>
      <div class="flex flex-col gap-4">
        <div>
          <label class="mb-1.5 block text-xs text-ink-gray-5">
            {{ __('Inquiry') }}
          </label>
          <div class="rounded bg-surface-gray-2 px-2 py-1.5 text-base text-ink-gray-8">
            {{ inquiry }}
          </div>
        </div>

        <div>
          <label class="mb-1.5 block text-xs text-ink-gray-5">
            {{ __('Kirim ke') }}
          </label>
          <div class="group rounded bg-surface-gray-2 p-2 hover:bg-surface-gray-3">
            <MultiSelectUserInput
              v-model="recipients"
              class="flex-1"
              inputClass="!bg-surface-gray-2 hover:!bg-surface-gray-3 group-hover:!bg-surface-gray-3"
              :placeholder="__('Pilih user')"
            />
          </div>
        </div>

        <FormControl
          v-model="remark"
          type="textarea"
          :rows="4"
          :label="__('Remark')"
          :placeholder="__('Yang perlu diketahui tim procurement')"
        />

        <div>
          <div class="mb-1.5 flex items-center justify-between">
            <label class="text-xs text-ink-gray-5">{{ __('Lampiran') }}</label>
            <FileUploader
              :upload-args="{
                doctype: 'CRM Procurement',
                docname: props.procurementId,
                private: true,
              }"
              @success="(file) => attachments.push(file)"
            >
              <template #default="{ openFileSelector, uploading }">
                <Button
                  :label="__('Attach a File')"
                  iconLeft="paperclip"
                  :loading="uploading"
                  @click="openFileSelector()"
                />
              </template>
            </FileUploader>
          </div>

          <div v-if="attachments.length" class="flex flex-col gap-1">
            <div
              v-for="f in attachments"
              :key="f.name"
              class="flex items-center gap-2 rounded bg-surface-gray-2 px-2 py-1.5 text-base"
            >
              <LucidePaperclip class="size-4 shrink-0 text-ink-gray-5" />
              <span class="min-w-0 flex-1 truncate text-ink-gray-8">
                {{ f.file_name }}
              </span>
              <button class="text-ink-gray-4 hover:text-ink-red-3" @click="remove(f)">
                <LucideX class="size-4" />
              </button>
            </div>
          </div>
          <div v-else class="text-sm text-ink-gray-5">
            {{ __('Belum ada lampiran.') }}
          </div>
        </div>
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end">
        <Button
          variant="solid"
          :label="__('Kirim')"
          :disabled="!recipients.length"
          :loading="sending"
          @click="send"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import MultiSelectUserInput from '@/components/Controls/MultiSelectUserInput.vue'
import { call, toast, FileUploader } from 'frappe-ui'
import { ref, watch } from 'vue'
import LucidePaperclip from '~icons/lucide/paperclip'
import LucideX from '~icons/lucide/x'

const props = defineProps({
  procurementId: { type: String, required: true },
  title: { type: String, default: '' },
  inquiry: { type: String, default: '' },
})

const emit = defineEmits(['sent'])

const show = defineModel({ type: Boolean })

const recipients = ref([])
const remark = ref('')
const attachments = ref([])
const sending = ref(false)

// Isian dikosongkan tiap kali modal dibuka: permintaan berikutnya adalah
// permintaan yang berbeda, dan catatan lama yang tertinggal di kotak akan
// terkirim lagi tanpa disadari.
//
// Lampiran yang terlanjur diunggah TIDAK ikut dihapus -- berkasnya sudah
// menempel di dokumen procurement dan tetap bisa dibuka dari situ; yang tidak
// diulang cuma pengirimannya lewat email.
watch(show, (open) => {
  if (open) {
    recipients.value = []
    remark.value = ''
    attachments.value = []
  }
})

async function remove(file) {
  try {
    await call('frappe.client.delete', { doctype: 'File', name: file.name })
    attachments.value = attachments.value.filter((f) => f.name !== file.name)
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal menghapus lampiran'))
  }
}

async function send() {
  sending.value = true
  try {
    const res = await call('crm_cakra.api.procurement.submit_to_procurement', {
      procurement: props.procurementId,
      recipients: recipients.value,
      remark: remark.value,
      attachments: attachments.value.map((f) => f.name),
    })
    show.value = false
    toast.success(__('Permintaan procurement terkirim'))
    emit('sent', res)
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal mengirim permintaan'))
  } finally {
    sending.value = false
  }
}
</script>
