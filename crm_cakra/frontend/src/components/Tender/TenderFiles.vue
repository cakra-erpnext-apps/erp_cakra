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
          {{ __('Belum ada berkas. Upload Excel, Word, atau PDF lewat tombol +.') }}
        </div>
      </div>
    </div>

    <!-- Excel apa adanya, bisa diedit, Save menulis balik ke file -->
    <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
      <!-- Di sini hanya dibaca; edit di tab baru supaya file tender tidak
           berubah tanpa sengaja waktu orang cuma melihat. -->
      <SpreadsheetView
        v-if="selectedFile?.editable"
        :key="selected"
        :file-name="selected"
        :label="selectedFile.file_name"
        max-height="none"
        readonly
        class="flex-1"
      >
        <template #actions>
          <FileUploader
            :upload-args="{
              doctype: 'CRM Tender',
              docname: tenderId,
              private: true,
            }"
            @success="onReuploaded"
          >
            <template #default="{ openFileSelector, uploading }">
              <Button
                :label="__('Re-upload')"
                icon-left="upload"
                :loading="uploading"
                @click="openFileSelector()"
              />
            </template>
          </FileUploader>
          <Dropdown :options="editOptions">
            <template #default="{ open }">
              <Button
                :label="__('Edit')"
                icon-left="external-link"
                :icon-right="open ? 'chevron-up' : 'chevron-down'"
              />
            </template>
          </Dropdown>
        </template>
      </SpreadsheetView>
      <div v-else-if="isPreviewable(selectedFile)" class="flex flex-1 flex-col">
        <div class="flex h-[45px] shrink-0 items-center gap-3 border-b px-4">
          <div class="min-w-0 flex-1 truncate text-base font-medium text-ink-gray-8">
            {{ selectedFile.file_name }}
          </div>
          <a :href="selectedFile.file_url" download>
            <Button :tooltip="__('Download')" icon="download" variant="ghost" />
          </a>
        </div>
        <img
          v-if="isImage(selectedFile)"
          :src="selectedFile.file_url"
          class="m-auto max-h-full max-w-full object-contain p-4"
        />
        <iframe v-else :src="selectedFile.file_url" class="w-full flex-1" />
      </div>
      <div
        v-else-if="selectedFile"
        class="flex flex-1 flex-col items-center justify-center gap-3"
      >
        <div class="text-ink-gray-5">
          {{ __('Berkas ini tidak bisa ditampilkan di sini.') }}
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
  Dropdown,
  FeatherIcon,
  FileUploader,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

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

const ext = (f) => (f?.file_name || '').split('.').pop().toLowerCase()
const isImage = (f) => ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext(f))
// PDF & gambar dibuka langsung oleh browser. Word butuh konversi, jadi diunduh.
const isPreviewable = (f) => f && (ext(f) === 'pdf' || isImage(f))

function openEditor(fileName) {
  window.open(router.resolve({ name: 'SpreadsheetEditor', params: { fileName } }).href, '_blank')
}

function downloadFile(f) {
  const a = document.createElement('a')
  a.href = f.file_url
  a.download = f.file_name
  a.click()
}

const editOptions = computed(() => [
  {
    label: __('Edit in Web'),
    onClick: () => openEditor(selected.value),
  },
  {
    label: __('Download & Edit on Your Device'),
    onClick: () => downloadFile(selectedFile.value),
  },
])

function onUploaded(f) {
  files.reload()
  selected.value = f.name
}

// Re-upload: file lama dihapus supaya tidak ada dua versi nyangkut di daftar berkas.
async function onReuploaded(f) {
  const oldName = selected.value
  selected.value = f.name
  files.reload()
  if (oldName && oldName !== f.name) {
    try {
      await call('frappe.client.delete', { doctype: 'File', name: oldName })
      files.reload()
    } catch (err) {
      toast.error(err.messages?.[0] || err.message || __('Gagal menghapus versi lama'))
    }
  }
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
