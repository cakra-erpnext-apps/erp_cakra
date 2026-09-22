<template>
  <div class="flex min-w-0">
    <!-- Daftar berkas: xlsx dibuka di grid, sisanya diunduh -->
    <div class="flex w-60 shrink-0 flex-col border-r">
      <div class="flex h-[45px] items-center justify-between border-b px-4">
        <span class="text-base font-medium text-ink-gray-8">
          {{ __('Berkas') }}
        </span>
        <FileUploader
          :upload-args="{
            doctype: 'CRM Tender',
            docname: tenderId,
            private: true,
          }"
          @success="onUploaded"
        >
          <template #default="{ openFileSelector, uploading }">
            <Button
              :tooltip="__('Upload')"
              icon="plus"
              variant="ghost"
              :loading="uploading"
              @click="openFileSelector()"
            />
          </template>
        </FileUploader>
      </div>

      <div class="flex-1 overflow-y-auto p-2">
        <div
          v-for="f in files.data || []"
          :key="f.name"
          class="group flex cursor-pointer items-center gap-2.5 rounded px-2 py-2"
          :class="
            f.name === selected
              ? 'bg-surface-gray-3'
              : 'hover:bg-surface-gray-2'
          "
          @click="selected = f.name"
        >
          <div
            class="flex size-8 shrink-0 items-center justify-center rounded border bg-surface-white"
          >
            <FileSpreadsheetIcon
              v-if="f.editable"
              class="size-4 text-ink-gray-7"
            />
            <FileIcon v-else class="size-4 text-ink-gray-7" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="truncate text-base text-ink-gray-8">
              {{ f.file_name }}
            </div>
            <div class="text-sm text-ink-gray-5">
              {{ convertSize(f.file_size) }}
            </div>
          </div>
          <Button
            class="!size-5 opacity-0 group-hover:opacity-100"
            :tooltip="__('Delete')"
            @click.stop="removeFile(f)"
          >
            <template #icon>
              <FeatherIcon name="trash-2" class="size-3 text-ink-gray-7" />
            </template>
          </Button>
        </div>

        <div
          v-if="files.data && !files.data.length"
          class="px-3 py-10 text-center text-sm text-ink-gray-5"
        >
          {{ __('Belum ada berkas. Upload excel tender lewat tombol +.') }}
        </div>
      </div>
    </div>

    <!-- Excel apa adanya, bisa diedit, Save menulis balik ke file -->
    <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
      <SpreadsheetView
        v-if="selectedFile?.editable"
        :key="selected"
        :file-name="selected"
        :label="selectedFile.file_name"
        max-height="none"
        class="flex-1"
      />
      <div
        v-else-if="selectedFile"
        class="flex flex-1 flex-col items-center justify-center gap-3"
      >
        <div class="text-ink-gray-5">
          {{ __('Berkas ini bukan excel, tidak bisa diedit di sini.') }}
        </div>
        <a :href="selectedFile.file_url" target="_blank">
          <Button :label="__('Download')" />
        </a>
      </div>
      <div
        v-else
        class="flex flex-1 items-center justify-center text-ink-gray-5"
      >
        {{ __('Pilih berkas di kiri') }}
      </div>
    </div>
  </div>
</template>

<script setup>
import SpreadsheetView from '@/components/SpreadsheetView.vue'
import FileSpreadsheetIcon from '@/components/Icons/FileSpreadsheetIcon.vue'
import FileIcon from '@/components/Icons/FileIcon.vue'
import { convertSize } from '@/utils'
import {
  Button,
  FeatherIcon,
  FileUploader,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import { computed, ref } from 'vue'

const props = defineProps({ tenderId: { type: String, required: true } })

const selected = ref('')

const files = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_tender.crm_tender.get_attachments',
  params: { tender: props.tenderId },
  auto: true,
  onSuccess(list) {
    // Excel pertama langsung dibuka; itu alasan orang membuka tab ini.
    if (!list.find((f) => f.name === selected.value)) {
      selected.value = list.find((f) => f.editable)?.name || list[0]?.name || ''
    }
  },
})

const selectedFile = computed(() =>
  (files.data || []).find((f) => f.name === selected.value),
)

function onUploaded(f) {
  files.reload()
  selected.value = f.name
}

async function removeFile(f) {
  if (!confirm(__('Hapus {0}?', [f.file_name]))) return
  try {
    await call('frappe.client.delete', { doctype: 'File', name: f.name })
    if (selected.value === f.name) selected.value = ''
    files.reload()
  } catch (err) {
    toast.error(err.messages?.[0] || err.message || __('Gagal menghapus'))
  }
}
</script>
