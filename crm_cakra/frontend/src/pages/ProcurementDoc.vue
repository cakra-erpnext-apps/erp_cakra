<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs">
        <!-- Tanpa slot ini ikon view (garis tiga untuk List) tidak digambar --
             Breadcrumbs menyerahkan penggambaran prefix ke halamannya. -->
        <template #prefix="{ item }">
          <Icon v-if="item.icon" :icon="item.icon" class="mr-2 h-4" />
        </template>
      </Breadcrumbs>
    </template>
    <template v-if="procurement.doc?.name" #right-header>
      <AssignTo
        v-model="assignees.data"
        doctype="CRM Procurement"
        :docname="props.procurementId"
      />
      <Badge
        :label="__(procurement.doc.status)"
        :theme="STATUS_THEME[procurement.doc.status] || 'gray'"
        variant="subtle"
      />
      <Button
        v-if="procurement.doc.status !== 'Approve'"
        variant="solid"
        :label="__('Approve Cost')"
        :loading="approving"
        @click="approveCost"
      />
      <Button
        :tooltip="__('Delete')"
        variant="subtle"
        icon="trash-2"
        theme="red"
        @click="deleteRequest"
      />
    </template>
  </LayoutHeader>

  <div v-if="procurement.doc?.name" class="flex h-full overflow-hidden">
    <div class="flex-1 overflow-y-auto px-5 pb-8">
      <!-- Permintaan terakhir yang dikirim. Ditampilkan sebagai catatan, bukan
           kotak isian: yang menulisnya modal Submit to Procurement. -->
      <div
        v-if="procurement.doc.submitted_on"
        class="mt-5 rounded-lg border border-outline-gray-2 px-4 py-3"
      >
        <div class="text-sm text-ink-gray-5">
          {{ __('Dikirim ke') }} {{ procurement.doc.requested_to }} &middot;
          {{ formatDate(procurement.doc.submitted_on) }}
        </div>
        <div
          v-if="procurement.doc.remark"
          class="mt-1 whitespace-pre-wrap text-base text-ink-gray-8"
        >
          {{ procurement.doc.remark }}
        </div>
      </div>

      <!-- Inquiry-nya dirender dengan layout milik CRM Inquiry sendiri, bukan
           salinan ringkasannya: satu sumber format, apa pun yang berubah di
           inquiry langsung terlihat di sini, dan field yang ditambah di sana ikut
           muncul tanpa halaman ini disentuh lagi. -->
      <DataFields
        :key="procurement.doc.inquiry"
        doctype="CRM Inquiry"
        :docname="procurement.doc.inquiry"
        readonly
      />

      <!-- Biaya: satu-satunya yang benar-benar milik dokumen ini. Panel yang sama
           dipakai tab Procurement di halaman Inquiry. -->
      <ProcurementPanel
        class="border-t border-outline-gray-2 pt-6"
        :canEdit="isProcurement()"
        :procurementId="props.procurementId"
        :inquiry="procurement.doc.inquiry"
        @saved="procurement.reload()"
      />
    </div>

    <!-- Komentar + lampiran: dipakai bolak-balik marketing dan procurement,
         jadi ditaruh berdampingan dengan biayanya, bukan di tab lain. -->
    <Resizer
      side="right"
      :defaultWidth="420"
      :maxWidth="640"
      class="flex h-full flex-col overflow-hidden border-l"
    >
      <CommentPane doctype="CRM Procurement" :docname="props.procurementId" />
    </Resizer>
  </div>

  <ErrorPage v-else-if="errorTitle" :errorTitle="errorTitle" :errorMessage="errorMessage" />

</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  createDocumentResource,
  Breadcrumbs,
  Button,
  Badge,
  call,
  toast,
  usePageMeta,
} from 'frappe-ui'
import Icon from '@/components/Icon.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import ErrorPage from '@/components/ErrorPage.vue'
import AssignTo from '@/components/AssignTo.vue'
import DataFields from '@/components/Activities/DataFields.vue'
import ProcurementPanel from '@/components/Procurement/ProcurementPanel.vue'
import Resizer from '@/components/Resizer.vue'
import CommentPane from '@/components/CommentPane.vue'
import { usersStore } from '@/stores/users'
import { useDocument } from '@/data/document'
import { formatDate } from '@/utils'
import { getView } from '@/utils/view'

const route = useRoute()
const router = useRouter()
const { isProcurement } = usersStore()

const props = defineProps({
  procurementId: { type: String, required: true },
})

const errorTitle = ref('')
const errorMessage = ref('')
const approving = ref(false)

// Request = diminta Marketing, Reviewing = procurement sudah mengisi biaya,
// Approve = angkanya dinyatakan final.
const STATUS_THEME = {
  Draft: 'gray',
  Request: 'orange',
  Reviewing: 'blue',
  Approve: 'green',
}

const procurement = createDocumentResource({
  doctype: 'CRM Procurement',
  name: props.procurementId,
  cache: ['procurement', props.procurementId],
  auto: true,
  onError(err) {
    errorTitle.value = __(
      err.exc_type === 'DoesNotExistError' ? 'Procurement Not Found' : 'Error',
    )
    errorMessage.value = __(err.messages?.[0] || 'An Error Occurred')
  },
})

// Dipakai kotak AssignTo di header; costing-nya dipegang ProcurementPanel.
const { assignees } = useDocument('CRM Procurement', props.procurementId)

async function approveCost() {
  approving.value = true
  try {
    await call('crm_cakra.api.procurement.approve_cost', {
      procurement: props.procurementId,
    })
    procurement.reload()
    toast.success(__('Costing disetujui'))
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal menyetujui costing'))
  } finally {
    approving.value = false
  }
}

function deleteRequest() {
  if (!confirm(__('Hapus permintaan procurement ini?'))) return
  procurement.delete.submit().then(() => router.push({ name: 'Procurement' }))
}

const breadcrumbs = computed(() => {
  const items = [{ label: __('Procurement'), route: { name: 'Procurement' } }]

  // Segmen view (List) hanya muncul kalau datang dari daftar, persis seperti
  // halaman Quotation -- query-nya dibawa oleh tautan barisnya.
  if (route.query.view || route.query.viewType) {
    const view = getView(route.query.view, route.query.viewType, 'CRM Procurement')
    if (view) {
      items.push({
        label: __(view.label),
        icon: view.icon,
        route: {
          name: 'Procurement',
          params: { viewType: route.query.viewType },
          query: { view: route.query.view },
        },
      })
    }
  }

  items.push({ label: procurement.doc?.inquiry || props.procurementId })
  return items
})

usePageMeta(() => ({ title: procurement.doc?.inquiry || props.procurementId }))
</script>
