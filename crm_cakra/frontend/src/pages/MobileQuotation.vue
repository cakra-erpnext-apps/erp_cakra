<template>
  <LayoutHeader>
    <header
      class="relative flex h-10.5 items-center justify-between gap-2 py-2.5 pl-2"
    >
      <Breadcrumbs :items="breadcrumbs">
        <template #prefix="{ item }">
          <Icon v-if="item.icon" :icon="item.icon" class="mr-2 h-4" />
        </template>
      </Breadcrumbs>
      <div class="absolute right-0 flex items-center gap-2 pr-1">
        <Button
          v-if="gridDoc?.isDirty && !isLocked"
          variant="solid"
          :label="__('Save')"
          :loading="gridDoc?.save?.loading"
          @click="saveQuotation"
        />
        <Dropdown
          v-if="quotation.doc && stateOptions.length"
          :options="stateOptions"
          placement="right"
        >
          <template #default="{ open }">
            <Button
              v-if="quotation.doc.state"
              :label="quotation.doc.state"
              :iconRight="open ? 'chevron-up' : 'chevron-down'"
            >
              <template #prefix>
                <IndicatorIcon :class="getStateColor(quotation.doc.state)" />
              </template>
            </Button>
          </template>
        </Dropdown>
        <Button v-else-if="quotation.doc?.state" :label="quotation.doc.state" disabled>
          <template #prefix>
            <IndicatorIcon :class="getStateColor(quotation.doc.state)" />
          </template>
        </Button>
      </div>
    </header>
  </LayoutHeader>

  <div
    v-if="quotation.doc?.name"
    class="flex h-12 items-center justify-between gap-2 border-b px-3 py-2.5"
  >
    <AssignTo v-model="assignees.data" doctype="CRM Quotation" :docname="quotationId" />
    <div class="flex items-center gap-1.5">
      <Button :tooltip="__('Print')" icon="printer" @click="printQuotation" />
      <Button :tooltip="__('Duplicate')" icon="copy" :loading="duplicating" @click="duplicateQuotation" />
      <Button
        v-if="!isConverted"
        :tooltip="quotation.doc?.is_void ? __('Unvoid') : __('Void')"
        variant="subtle"
        icon="slash"
        :theme="quotation.doc?.is_void ? 'gray' : 'orange'"
        @click="toggleVoid"
      />
      <Button
        v-if="canConvert"
        :label="__('Convert')"
        variant="solid"
        :loading="converting"
        @click="confirmConvert"
      />
      <Button
        :tooltip="__('Delete')"
        variant="subtle"
        icon="trash-2"
        theme="red"
        @click="deleteQuotation"
      />
    </div>
  </div>

  <div v-if="quotation.doc?.name" class="flex h-full overflow-hidden">
    <Tabs
      v-model="tabIndex"
      as="div"
      :tabs="tabs"
      class="flex flex-1 overflow-auto flex-col [&_[role='tab']]:px-0 [&_[role='tab']]:shrink-0 [&_[role='tablist']]:px-3 [&_[role='tablist']]:min-h-[45px] [&_[role='tablist']]:gap-7.5 [&_[role='tabpanel']:not([hidden])]:flex [&_[role='tabpanel']:not([hidden])]:grow"
    >
      <template #tab-panel="{ tab }">
        <div v-if="tab.name === 'Data'" class="flex-1 overflow-y-auto px-3 pb-8">
          <div v-if="sections.data" class="mb-4">
            <SidePanelLayout
              :sections="sections.data"
              doctype="CRM Quotation"
              :docname="quotationId"
              @reload="sections.reload"
            />
          </div>
          <DataFields doctype="CRM Quotation" :docname="quotationId" :readonly="isLocked" />
        </div>

        <Activities
          v-else
          ref="activities"
          v-model:reload="reload"
          v-model:tabIndex="tabIndex"
          doctype="CRM Quotation"
          :docname="quotationId"
          :tabs="tabs"
        />
      </template>
    </Tabs>
  </div>

  <ErrorPage
    v-else-if="errorTitle"
    :errorTitle="errorTitle"
    :errorMessage="errorMessage"
  />

  <FilesUploader
    v-model="showFilesUploader"
    doctype="CRM Quotation"
    :docname="quotationId"
    @after="
      () => {
        activities?.all_activities?.reload()
        changeTabTo('Attachments')
      }
    "
  />

  <NegativeMarginModal
    v-if="showNegativeMargin"
    v-model="showNegativeMargin"
    :quotationId="props.quotationId"
    :margin="quotation.doc?.margin || 0"
    :reason="quotation.doc?.negative_margin_reason || ''"
    @submitted="onMarginReasonSaved"
  />

  <!-- Konten cetak (tersembunyi di layar, tampil hanya saat print). Baru dipasang
       sesudah server meluluskan cetaknya -- lihat printSheetReady. -->
  <Teleport to="body">
    <div v-if="quotation.doc?.name && printSheetReady" id="qp-print-root">
      <QuotationPrintContent :doc="quotation.doc" />
    </div>
  </Teleport>
</template>

<script setup>
import { printQuotation as doPrintQuotation } from '@/utils/printQuotation'
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  createDocumentResource,
  createResource,
  Breadcrumbs,
  Button,
  Dropdown,
  Tabs,
  toast,
  call,
} from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import ErrorPage from '@/components/ErrorPage.vue'
import Icon from '@/components/Icon.vue'
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import ActivityIcon from '@/components/Icons/ActivityIcon.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import DetailsIcon from '@/components/Icons/DetailsIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import AttachmentIcon from '@/components/Icons/AttachmentIcon.vue'
import Activities from '@/components/Activities/Activities.vue'
import FilesUploader from '@/components/FilesUploader/FilesUploader.vue'
import SidePanelLayout from '@/components/SidePanelLayout.vue'
import DataFields from '@/components/Activities/DataFields.vue'
import NegativeMarginModal from '@/components/Modals/NegativeMarginModal.vue'
import AssignTo from '@/components/AssignTo.vue'
import QuotationPrintContent from '@/components/Quotation/QuotationPrintContent.vue'
import { getView } from '@/utils/view'
import { stashDuplicate } from '@/utils/duplicate'
import { useDocument } from '@/data/document'
import { getMeta } from '@/stores/meta'
import { createDialog } from '@/utils/dialogs'
import { useActiveTabManager } from '@/composables/useActiveTabManager'

const router = useRouter()
const route = useRoute()

const props = defineProps({
  quotationId: { type: String, required: true },
})

const errorTitle = ref('')
const errorMessage = ref('')
const reload = ref(false)
const showFilesUploader = ref(false)
const activities = ref(null)
const converting = ref(false)

const { getFields } = getMeta('CRM Quotation')
const productMeta = getMeta('CRM Quotation Product')

const quotation = createDocumentResource({
  doctype: 'CRM Quotation',
  name: props.quotationId,
  cache: ['quotation', props.quotationId],
  auto: true,
  onError(err) {
    errorTitle.value = __(
      err.exc_type === 'DoesNotExistError' ? 'Quotation Not Found' : 'Error',
    )
    errorMessage.value = __(err.messages?.[0] || 'An Error Occurred')
  },
})

const sections = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections',
  params: { doctype: 'CRM Quotation' },
  auto: true,
})

const { document: gridDoc, assignees } = useDocument('CRM Quotation', props.quotationId)
watch(
  () => (gridDoc.doc?.products || []).map((p) => `${p.qty}|${p.price}|${p.rate}`).join(';'),
  () => {
    if (!gridDoc.doc) return
    let total = 0
    ;(gridDoc.doc.products || []).forEach((p) => {
      p.amount = (Number(p.qty) || 0) * (Number(p.price) || 0) * (Number(p.rate) || 1)
      total += p.amount
    })
    gridDoc.doc.net_total = total
  },
)

// Quotation Converted -> semua field read-only.
function lockField(key) {
  if (!gridDoc.fieldPropertyOverrides) gridDoc.fieldPropertyOverrides = {}
  gridDoc.fieldPropertyOverrides[key] = {
    ...(gridDoc.fieldPropertyOverrides[key] || {}),
    read_only: 1,
  }
}

function applyConvertedLock() {
  if (gridDoc.doc?.state !== 'Converted') return
  const fields = getFields ? getFields({ restrictNoValueFields: false }) : []
  if (!fields.length) return
  fields.forEach((f) => {
    if (!f.fieldname) return
    lockField(f.fieldname)
    if (f.fieldtype === 'Table' && f.options) {
      const cm = getMeta(f.options)
      const childFields = cm?.getFields
        ? cm.getFields({ restrictNoValueFields: false })
        : []
      childFields.forEach((cf) => cf.fieldname && lockField(`${f.fieldname}.${cf.fieldname}`))
    }
  })
}

watch(
  () => [
    gridDoc.doc?.state,
    getFields ? getFields({ restrictNoValueFields: false }).length : 0,
    productMeta?.getFields ? productMeta.getFields({ restrictNoValueFields: false }).length : 0,
  ],
  () => applyConvertedLock(),
  { immediate: true },
)

const title = computed(() => quotation.doc?.subject || props.quotationId)
const isConverted = computed(() => quotation.doc?.state === 'Converted')

// Sama dengan halaman desktop: status final membekukan isi dokumen.
const FINAL_STATES = ['Win', 'Lose', 'Converted']
const isLocked = computed(() => FINAL_STATES.includes(quotation.doc?.state))
const canConvert = computed(
  () => quotation.doc && !quotation.doc.is_void && quotation.doc.state !== 'Converted',
)

const breadcrumbs = computed(() => {
  const items = [{ label: __('Quotations'), route: { name: 'Quotations' } }]
  if (route.query.view || route.query.viewType) {
    const view = getView(route.query.view, route.query.viewType, 'CRM Quotation')
    if (view) {
      items.push({
        label: __(view.label),
        icon: view.icon,
        route: {
          name: 'Quotations',
          params: { viewType: route.query.viewType },
          query: { view: route.query.view },
        },
      })
    }
  }
  items.push({ label: title.value })
  return items
})

const tabs = computed(() => [
  { name: 'Data', label: __('Data'), icon: DetailsIcon },
  { name: 'Comments', label: __('Comments'), icon: CommentIcon },
  { name: 'Notes', label: __('Notes'), icon: NoteIcon },
  { name: 'Attachments', label: __('Attachments'), icon: AttachmentIcon },
  { name: 'Activity', label: __('Activity'), icon: ActivityIcon },
])

const { tabIndex } = useActiveTabManager(tabs, 'lastQuotationTab', 'data')

function changeTabTo(name) {
  const idx = tabs.value.findIndex((t) => t.name === name)
  if (idx >= 0) tabIndex.value = idx
}

const stateOptions = computed(() => {
  // Daftar yang sama dengan desktop. 'Converted' tidak ada: itu hanya di-set
  // saat konversi ke estimasi.
  const SELECTABLE_STATES = ['Inquired', 'Negotiation', 'Follow Up', 'Win', 'Lose']
  const current = quotation.doc?.state || 'Inquired'
  const targets = SELECTABLE_STATES.filter((state) => state !== current)
  return targets.map((newState) => ({
    label: newState,
    onClick: () => updateState(newState),
  }))
})

function getStateColor(state) {
  return {
    Inquired: 'text-ink-gray-5',
    Negotiation: 'text-ink-blue-3',
    'Follow Up': 'text-ink-amber-3',
    Win: 'text-ink-green-3',
    Lose: 'text-ink-red-4',
    Converted: 'text-ink-green-3',
  }[state] || 'text-ink-gray-5'
}

function updateState(newState) {
  quotation.setValue.submit({ state: newState }).then(() => {
    toast.success(__(`State updated to ${newState}`))
  })
}

async function saveQuotation() {
  try {
    await gridDoc.save.submit()
    toast.success(__('Saved'))
  } catch (e) {
    toast.error(e.message || __('Failed to save'))
  }
}

const duplicating = ref(false)
function duplicateQuotation() {
  stashDuplicate('CRM Quotation', gridDoc.doc, [
    'number', 'inquiry', 'account', 'account_name', 'printed_by',
  ])
  router.push({ name: 'NewQuotation' })
}

// Aturan cetak yang sama dengan halaman desktop. Halaman ini bukan varian tampilan
// belaka -- router memilihnya lewat handleMobileView(), jadi di HP inilah satu-satunya
// halaman quotation yang ada. Gerbang yang cuma dipasang di Quotation.vue berarti
// tidak ada gerbang sama sekali buat orang lapangan.
const printSheetReady = ref(false)
const showNegativeMargin = ref(false)

async function onMarginReasonSaved() {
  await quotation.reload()
  toast.success(__('Alasan tersimpan. Tekan Print sekali lagi untuk mencetak.'))
}

watch(
  () => quotation.doc?.modified,
  () => (printSheetReady.value = false),
)

async function printQuotation() {
  // Margin minus tanpa alasan: kotak alasan dulu. Ini cuma menghindari klik yang
  // sudah pasti ditolak -- yang mengikat tetap before_print di server, termasuk
  // untuk /printview yang dibuka langsung lewat URL.
  if ((quotation.doc?.margin || 0) < 0 && !quotation.doc?.negative_margin_reason) {
    showNegativeMargin.value = true
    return
  }

  const error = await doPrintQuotation(props.quotationId)
  if (!error) {
    printSheetReady.value = true
    return
  }
  createDialog({
    title: __('Tidak bisa dicetak'),
    html: error,
    actions: [{ label: __('Tutup'), variant: 'solid', onClick: (close) => close() }],
  })
}

function deleteQuotation() {
  if (confirm(__('Delete this quotation?'))) {
    quotation.delete.submit().then(() => {
      router.push({ name: 'Quotations' })
    })
  }
}

function confirmConvert() {
  createDialog({
    title: __('Convert to Estimation'),
    message: __(
      'Apakah anda yakin untuk convert ini? Setelah di-convert ke estimasi, quotation ini dianggap final dan tidak bisa diubah.',
    ),
    actions: [
      {
        label: __('Convert'),
        variant: 'solid',
        onClick: async (close) => {
          const ok = await doConvert()
          if (ok) close()
        },
      },
      {
        label: __('Batal'),
        onClick: (close) => close(),
      },
    ],
  })
}

async function doConvert() {
  converting.value = true
  try {
    const name = await call(
      'crm_cakra.fcrm.doctype.crm_quotation.crm_quotation.convert_to_estimation',
      { quotation: props.quotationId },
    )
    toast.success(__('Quotation converted to estimation'))
    router.push({ name: 'Estimation', params: { estimationId: name } })
    return true
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Failed to convert'))
    return false
  } finally {
    converting.value = false
  }
}

async function toggleVoid() {
  const isVoid = quotation.doc?.is_void
  let reason = null
  if (isVoid) {
    if (!confirm(__('Unvoid this quotation?'))) return
  } else {
    reason = prompt(__('Reason for voiding this quotation?'))
    if (reason === null) return
  }
  try {
    await call('crm_cakra.api.void.void_document', {
      doctype: 'CRM Quotation',
      name: props.quotationId,
      void: isVoid ? 0 : 1,
      reason,
    })
    quotation.reload()
    toast.success(isVoid ? __('Quotation unvoided') : __('Quotation voided'))
  } catch (e) {
    toast.error(e.message || __('Failed'))
  }
}
</script>

<style>
#qp-print-root {
  display: none;
}
/* Aturan sembunyikan-app hanya berlaku saat lembar cetaknya memang terpasang.
   Kalau tidak dibatasi begini, print dari menu browser di halaman yang belum lolos
   check_printable menyembunyikan seluruh app dan mencetak lembar kosong tanpa
   keterangan. #qp-print-root di-teleport ke body, jadi dia anak langsungnya. */
@media print {
  body:has(> #qp-print-root) > *:not(#qp-print-root) {
    display: none !important;
  }
  #qp-print-root {
    display: block !important;
  }
}
</style>
