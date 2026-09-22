<template>
  <div
    class="rounded-lg border border-outline-gray-2 bg-surface-white focus-within:border-outline-gray-3"
  >
    <TextEditor
      ref="textEditor"
      :content="content"
      :placeholder="placeholder"
      :mentions="users"
      editor-class="prose-sm max-w-none px-3 py-2 min-h-[2rem] max-h-56 overflow-y-auto"
      @change="content = $event"
    />

    <div v-if="attachments.length" class="flex flex-wrap gap-1 px-2 pb-2">
      <AttachmentItem
        v-for="a in attachments"
        :key="a.file_url"
        :label="a.file_name"
      >
        <template #suffix>
          <FeatherIcon class="h-3.5" name="x" @click.stop="removeAttachment(a)" />
        </template>
      </AttachmentItem>
    </div>

    <div class="flex items-center justify-between gap-2 border-t px-2 py-1.5">
      <FileUploader
        :upload-args="{ doctype, docname, private: true }"
        @success="(f) => attachments.push(f)"
      >
        <template #default="{ openFileSelector, uploading }">
          <Button
            :tooltip="__('Attach a File')"
            variant="ghost"
            :icon="AttachmentIcon"
            :loading="uploading"
            @click="openFileSelector()"
          />
        </template>
      </FileUploader>

      <div class="flex items-center gap-1">
        <Button
          v-if="cancellable"
          :label="__('Cancel')"
          variant="ghost"
          @click="emit('cancel')"
        />
        <Button
          variant="solid"
          :label="submitLabel || __('Comment')"
          :disabled="isEmpty"
          :loading="saving"
          @click="submit"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import AttachmentItem from '@/components/AttachmentItem.vue'
import AttachmentIcon from '@/components/Icons/AttachmentIcon.vue'
import { usersStore } from '@/stores/users'
import { TextEditor, FileUploader, Button, FeatherIcon } from 'frappe-ui'
import { ref, computed, nextTick } from 'vue'

const props = defineProps({
  doctype: { type: String, required: true },
  docname: { type: String, required: true },
  placeholder: { type: String, default: '' },
  submitLabel: { type: String, default: '' },
  cancellable: { type: Boolean, default: false },
  initialContent: { type: String, default: '' },
  autofocus: { type: Boolean, default: false },
})

const emit = defineEmits(['submit', 'cancel'])

const { users: usersList } = usersStore()

const textEditor = ref(null)
const content = ref(props.initialContent)
const attachments = ref([])
const saving = ref(false)

const isEmpty = computed(() => {
  const text = content.value.replace(/<[^>]*>/g, '').trim()
  return !text && !attachments.value.length
})

const users = computed(
  () =>
    usersList.data?.crmUsers
      ?.filter((user) => user.enabled)
      .map((user) => ({ label: user.full_name.trimEnd(), value: user.name })) ||
    [],
)

function removeAttachment(attachment) {
  attachments.value = attachments.value.filter((a) => a !== attachment)
}

function submit() {
  if (isEmpty.value) return
  saving.value = true
  // done() dipanggil induk setelah simpan selesai -- emit sendiri tidak bisa ditunggu.
  emit('submit', {
    content: content.value,
    attachments: attachments.value.map((a) => a.name),
    done: (ok) => {
      saving.value = false
      if (ok !== false) reset()
    },
  })
}

function reset() {
  content.value = ''
  attachments.value = []
}

if (props.autofocus) {
  nextTick(() => textEditor.value?.editor?.commands.focus())
}

defineExpose({ reset })
</script>
