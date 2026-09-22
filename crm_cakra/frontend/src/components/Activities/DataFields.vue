<template>
  <div
    class="my-3 flex items-center justify-between text-lg font-medium sm:mb-4 sm:mt-8"
  >
    <div class="flex h-8 items-center text-xl font-semibold text-ink-gray-8">
      {{ __('Data') }}
      <Badge
        v-if="document.isDirty && !readonly"
        class="ml-3"
        :label="__('Not Saved')"
        theme="orange"
      />
    </div>
    <div v-if="!readonly" class="flex gap-1">
      <Button
        v-if="isManager() && !isMobileView"
        :tooltip="__('Edit Fields Layout')"
        :icon="EditIcon"
        @click="showDataFieldsModal = true"
      />
      <Button
        label="Save"
        :disabled="!document.isDirty"
        variant="solid"
        :loading="document.save.loading"
        @click="saveChanges"
      />
    </div>
  </div>
  <div
    v-if="document.get.loading"
    class="flex flex-1 flex-col items-center justify-center gap-3 text-xl font-medium text-ink-gray-6"
  >
    <LoadingIndicator class="h-6 w-6" />
    <span>{{ __('Loading...') }}</span>
  </div>
  <div v-else class="pb-8">
    <!-- Bar tahapan: ditaruh di sini supaya ikut terbawa ke mana pun layout
         dirender (tab Data, halaman Procurement, halaman mobile). Inquiry
         mengambil tahapannya dari master CRM Inquiry Status; quotation statusnya
         Select biasa, jadi tahapannya dikirim dari sini. -->
    <StatusSteps
      v-if="doctype === 'CRM Inquiry'"
      :status="document.doc?.status"
    />
    <StatusSteps
      v-else-if="doctype === 'CRM Quotation'"
      :status="document.doc?.state"
      :steps="quotationSteps"
    />
    <FieldLayout
      v-if="tabs.data"
      :tabs="tabs.data"
      :data="document.doc"
      :doctype="doctype"
      :readonly="readonly"
    />
  </div>
  <DataFieldsModal
    v-if="showDataFieldsModal"
    v-model="showDataFieldsModal"
    :doctype="doctype"
    @reload="
      () => {
        tabs.reload()
        document.reload()
      }
    "
  />
</template>

<script setup>
import EditIcon from '@/components/Icons/EditIcon.vue'
import DataFieldsModal from '@/components/Modals/DataFieldsModal.vue'
import FieldLayout from '@/components/FieldLayout/FieldLayout.vue'
import StatusSteps from '@/components/StatusSteps.vue'
import { Badge, createResource, toast } from 'frappe-ui'
import LoadingIndicator from '@/components/Icons/LoadingIndicator.vue'
import { usersStore } from '@/stores/users'
import { useDocument } from '@/data/document'
import { isMobileView } from '@/composables/settings'
import { computed, ref, getCurrentInstance } from 'vue'

const props = defineProps({
  doctype: { type: String, required: true },
  docname: { type: String, required: true },
  // Layout dipinjam halaman lain yang cuma menumpang baca (Procurement merender
  // data Inquiry): semua field terkunci dan tombol Save tidak dirender.
  readonly: { type: Boolean, default: false },
})

const emit = defineEmits(['beforeSave', 'afterSave'])

const { isManager } = usersStore()

const instance = getCurrentInstance()
const attrs = instance?.vnode?.props ?? {}

const showDataFieldsModal = ref(false)

const { document } = useDocument(props.doctype, props.docname)

// Tahapan quotation. Warnanya disamakan dengan badge status di header dan list
// (Quotation.vue getStateColor) supaya satu dokumen tidak tampil dua warna.
// Win/Lose/Converted bukan tahap -- itu akhir cerita, jadi cuma ikut berbaris
// kalau quotation-nya memang sedang di sana, sama seperti Won/Lost di inquiry.
const QUOTATION_STEPS = [
  { name: 'Inquired', color: 'text-gray-600' },
  { name: 'Negotiation', color: 'text-blue-600' },
  { name: 'Follow Up', color: 'text-amber-600' },
]
const QUOTATION_FINAL_COLOR = {
  Win: 'text-green-600',
  Lose: 'text-red-600',
  Converted: 'text-green-600',
}

const quotationSteps = computed(() => {
  const state = document.doc?.state
  if (!state || QUOTATION_STEPS.some((s) => s.name === state)) return QUOTATION_STEPS
  return [...QUOTATION_STEPS, { name: state, color: QUOTATION_FINAL_COLOR[state] }]
})

const tabs = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout',
  cache: ['DataFields', props.doctype],
  params: { doctype: props.doctype, type: 'Data Fields' },
  auto: true,
})

function saveChanges() {
  if (!document.isDirty) return

  const updatedDoc = { ...document.doc }
  const oldDoc = { ...document.originalDoc }

  const changes = Object.keys(updatedDoc).reduce((acc, key) => {
    if (JSON.stringify(updatedDoc[key]) !== JSON.stringify(oldDoc[key])) {
      acc[key] = updatedDoc[key]
    }
    return acc
  }, {})

  const hasListener = attrs['onBeforeSave'] !== undefined

  if (hasListener) {
    emit('beforeSave', changes)
  } else {
    document.save.submit(null, {
      onSuccess: () => emit('afterSave', changes),
      onError: (err) => {
        const msgs = err?.messages || []
        if (msgs.length) {
          msgs.forEach((m) => toast.error(m))
        } else {
          toast.error(err?.message || __('Failed to save'))
        }
        document.save.loading = false
        console.error(err)
      },
    })
  }
}

</script>
