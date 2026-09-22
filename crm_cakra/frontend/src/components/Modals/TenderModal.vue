<template>
  <Dialog v-model="show" :options="{ size: '3xl' }">
    <template #body>
      <div class="bg-surface-modal px-4 pb-6 pt-5 sm:px-6">
        <div class="mb-5 flex items-center justify-between">
          <h3 class="text-2xl font-semibold leading-6 text-ink-gray-9">
            {{ __('Create Tender') }}
          </h3>
          <Button variant="ghost" class="w-7" icon="x" @click="show = false" />
        </div>
        <div
          v-if="tabs.loading"
          class="flex flex-col items-center gap-3 py-10 text-ink-gray-6"
        >
          <LoadingIndicator class="h-6 w-6" />
          <span>{{ __('Loading...') }}</span>
        </div>
        <div v-else-if="tabs.data?.length">
          <FieldLayout
            :tabs="tabs.data"
            :data="tender.doc"
            doctype="CRM Tender"
          />
          <ErrorMessage v-if="error" class="mt-4" :message="__(error)" />
        </div>
      </div>
      <div class="px-4 pb-7 pt-4 sm:px-6">
        <div class="flex flex-row-reverse gap-2">
          <Button
            variant="solid"
            :label="__('Create')"
            :loading="creating"
            @click="createTender"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import FieldLayout from '@/components/FieldLayout/FieldLayout.vue'
import LoadingIndicator from '@/components/Icons/LoadingIndicator.vue'
import { useDocument } from '@/data/document'
import { getMeta } from '@/stores/meta'
import { usersStore } from '@/stores/users'
import { findMissingMandatory } from '@/utils/fieldTransforms'
import { Button, Dialog, ErrorMessage, createResource } from 'frappe-ui'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const show = defineModel({ type: Boolean })
const router = useRouter()
const { getUser } = usersStore()
const { doctypeMeta } = getMeta('CRM Tender')

const error = ref(null)
const creating = ref(false)

const { document: tender, triggerOnBeforeCreate } = useDocument('CRM Tender')

// useDocument menyimpan draft tanpa nama di cache level modul, jadi isinya bertahan
// setelah modal ditutup. Direset di setup (Tenders.vue memasang modal dengan v-if,
// jadi setup jalan tiap kali dibuka) supaya draft batal tidak muncul lagi.
tender.doc = { __newDocument: true, doctype: 'CRM Tender' }
tender.fieldPropertyOverrides = {}
tender.doc.assigned_to = getUser().name
tender.doc.status = 'Draft'
tender.doc.currency = 'IDR'

// Sengaja memakai layout "Data Fields", bukan "Quick Entry": form New Tender harus
// selalu sama persis dengan tab Data, jadi keduanya dibaca dari satu record layout.
// Cache key-nya disamakan dengan DataFields.vue supaya sekali edit kena dua-duanya.
const tabs = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout',
  cache: ['DataFields', 'CRM Tender'],
  params: { doctype: 'CRM Tender', type: 'Data Fields' },
  auto: true,
})

const insertTender = createResource({ url: 'frappe.client.insert' })

async function createTender() {
  error.value = null

  // Wajib-isi diambil dari meta, bukan dihardcode: kalau nanti ada field reqd baru,
  // pesannya tetap muncul inline, bukan lolos ke server jadi MandatoryError mentah.
  const missing = findMissingMandatory(
    doctypeMeta.value?.fields || [],
    tender.doc,
  )
  if (missing.length) {
    error.value = __('Mandatory fields required: {0}', [missing.join(', ')])
    return
  }

  await triggerOnBeforeCreate?.()

  const doc = { ...tender.doc, doctype: 'CRM Tender' }
  delete doc.__newDocument

  creating.value = true
  insertTender.submit(
    { doc },
    {
      onSuccess(created) {
        creating.value = false
        show.value = false
        tender.doc = { __newDocument: true, doctype: 'CRM Tender' }
        router.push({ name: 'Tender', params: { tenderId: created.name } })
      },
      onError(err) {
        creating.value = false
        error.value = err.messages?.length
          ? err.messages.join('\n')
          : err.message
      },
    },
  )
}
</script>
