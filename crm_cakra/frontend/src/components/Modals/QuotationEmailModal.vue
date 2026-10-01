<template>
  <Dialog v-model="show" :options="{ size: '5xl' }">
    <template #body>
      <div class="flex flex-col gap-4 p-5">
        <div>
          <div class="text-2xl font-semibold text-ink-gray-9">
            {{ __('Kirim Quotation') }}
          </div>
          <div class="mt-1 text-p-sm text-ink-gray-5">
            {{
              __(
                'Periksa dulu dokumennya. PDF di bawah ini yang akan terlampir di email.',
              )
            }}
          </div>
        </div>

        <!-- Pratinjau memakai /printview, Print Format yang sama dengan tombol
             Print dan dengan PDF yang dilampirkan server. Satu sumber render:
             yang dilihat di sini itulah yang diterima customer. -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1">
          <div
            class="flex items-center justify-between border-b px-3 py-2 text-p-sm text-ink-gray-6"
          >
            <span>{{ __('Lampiran') }}: {{ quotationId }}.pdf</span>
            <Button
              :label="__('Buka di tab baru')"
              variant="ghost"
              @click="openInTab"
            />
          </div>
          <iframe
            :src="previewUrl"
            class="h-[45vh] w-full rounded-b-lg bg-white"
            :title="__('Pratinjau quotation')"
          />
        </div>

        <EmailEditor
          ref="editor"
          v-model="mailTo"
          v-model:content="body"
          :subject="defaultSubject"
          doctype="CRM Quotation"
          :editable="true"
          :submitButtonProps="{
            variant: 'solid',
            label: __('Kirim'),
            loading: sending,
            disabled: sending,
            onClick: send,
          }"
          :discardButtonProps="{ onClick: () => (show = false) }"
          :placeholder="
            __('Terlampir penawaran kami untuk pekerjaan berikut...')
          "
        />

        <ErrorMessage :message="error" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import EmailEditor from '@/components/EmailEditor.vue'
import { Dialog, ErrorMessage, call, toast } from 'frappe-ui'
import { computed, ref } from 'vue'

const props = defineProps({
  quotationId: { type: String, required: true },
  // Email customer, dipakai sebagai isian awal TO.
  email: { type: String, default: '' },
  subject: { type: String, default: '' },
})

const emit = defineEmits(['sent'])
const show = defineModel({ type: Boolean })

const editor = ref(null)
const body = ref('')
const error = ref('')
const sending = ref(false)

// EmailEditor mengisi TO dari `.email` model yang diberikan pemanggil.
const mailTo = ref({ email: props.email })

const defaultSubject = computed(
  () => props.subject || __('Penawaran {0}', [props.quotationId]),
)

const previewUrl = computed(() => {
  const params = new URLSearchParams({
    doctype: 'CRM Quotation',
    name: props.quotationId,
    format: 'Quotation Print Out',
    no_letterhead: '0',
  })
  return `/printview?${params.toString()}`
})

function openInTab() {
  window.open(previewUrl.value, '_blank')
}

async function send() {
  const to = editor.value?.toEmails || []
  if (!to.length) {
    error.value = __('Penerima email wajib diisi.')
    return
  }
  error.value = ''
  sending.value = true
  try {
    await call('crm_cakra.api.quotation.send_quotation_email', {
      quotation: props.quotationId,
      recipients: to.join(', '),
      cc: (editor.value?.ccEmails || []).join(', '),
      bcc: (editor.value?.bccEmails || []).join(', '),
      subject: editor.value?.subject || defaultSubject.value,
      content: body.value,
      sender: editor.value?.fromEmail || undefined,
    })
    toast.success(__('Email terkirim dengan lampiran PDF'))
    show.value = false
    emit('sent')
  } catch (e) {
    error.value = e?.messages?.[0] || e?.message || __('Email gagal dikirim.')
  } finally {
    sending.value = false
  }
}
</script>
