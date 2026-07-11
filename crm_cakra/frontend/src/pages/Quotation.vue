<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs">
        <template #prefix="{ item }">
          <Icon v-if="item.icon" :icon="item.icon" class="mr-2 h-4" />
        </template>
      </Breadcrumbs>
    </template>
    <template v-if="!errorTitle" #right-header>
      <AssignTo v-model="assignees.data" doctype="CRM Quotation" :docname="props.quotationId" />

      <Button v-if="canConvert" variant="solid" theme="blue" :label="__('Convert to Estimation')"
        :loading="converting" @click="confirmConvert" />

      <Button v-if="gridDoc?.isDirty && !isConverted" variant="solid" :label="__('Save')" :loading="gridDoc?.save?.loading"
        @click="saveQuotation" />

      <Button v-if="isConverted" :label="__('Converted')" disabled>
        <template #prefix>
          <IndicatorIcon class="text-ink-green-3" />
        </template>
      </Button>

      <!-- Tanpa syarat stateOptions.length: kalau tidak, badge status ikut hilang
           dari header begitu quotation mencapai status final. -->
      <Dropdown v-else-if="quotation.doc" :options="stateOptions" placement="right">
        <template #default="{ open }">
          <Button v-if="quotation.doc.state" :label="quotation.doc.state"
            :iconRight="open ? 'chevron-up' : 'chevron-down'">
            <template #prefix>
              <IndicatorIcon :class="getStateColor(quotation.doc.state)" />
            </template>
          </Button>
        </template>
      </Dropdown>
    </template>
  </LayoutHeader>

  <div v-if="quotation.doc?.name" class="flex h-full overflow-hidden">
    <!-- LEFT: Tabs -->
    <Tabs v-model="tabIndex" as="div" :tabs="tabs"
      class="flex flex-1 overflow-hidden flex-col [&_[role='tab']]:px-0 [&_[role='tab']]:shrink-0 [&_[role='tablist']]:px-5 [&_[role='tablist']::-webkit-scrollbar]:h-0 [&_[role='tablist']]:min-h-[45px] [&_[role='tablist']]:gap-7.5 [&_[role='tabpanel']:not([hidden])]:flex [&_[role='tabpanel']:not([hidden])]:grow">
      <template #tab-panel="{ tab }">
        <div v-if="tab.name === 'Data'" class="flex-1 overflow-y-auto px-5 pb-8">
          <DataFields doctype="CRM Quotation" :docname="props.quotationId" />
        </div>

        <Activities v-else ref="activities" v-model:reload="reload" v-model:tabIndex="tabIndex" doctype="CRM Quotation"
          :docname="props.quotationId" :tabs="tabs" />
      </template>
    </Tabs>

    <!-- RIGHT: Sidebar -->
    <Resizer side="right" class="flex flex-col justify-between border-l">
      <!-- ID Header -->
      <div class="flex h-[45px] cursor-copy items-center border-b px-5 py-2.5 text-lg font-medium text-ink-gray-9"
        @click="copyToClipboard(props.quotationId)">
        {{ props.quotationId }}
      </div>

      <!-- Title + Actions -->
      <div class="flex items-center justify-start gap-5 border-b p-5">
        <Tooltip :text="__('Quotation')">
          <div class="group relative size-12">
            <Avatar size="3xl" class="size-12" :label="title" />
          </div>
        </Tooltip>
        <div class="flex flex-col gap-2.5 truncate text-ink-gray-9">
          <Tooltip :text="quotation.doc?.subject || __('Set a Subject')">
            <div class="truncate text-2xl font-medium">
              {{ title }}
              <span v-if="quotation.doc?.is_void" class="text-base font-semibold text-ink-red-4">({{ __('VOID') }})</span>
            </div>
          </Tooltip>
          <div class="flex gap-1.5">
            <Button :tooltip="__('Print')" icon="printer" @click="printQuotation" />
            <Button :tooltip="__('Duplicate')" icon="copy" :loading="duplicating" @click="duplicateQuotation" />
            <Button :tooltip="__('Attach a File')" :icon="AttachmentIcon" @click="showFilesUploader = true" />
            <Button v-if="!isConverted" :tooltip="quotation.doc?.is_void ? __('Unvoid') : __('Void')" variant="subtle"
              icon="slash" :theme="quotation.doc?.is_void ? 'gray' : 'orange'" @click="toggleVoid" />
            <Button :tooltip="__('Delete')" variant="subtle" icon="trash-2" theme="red" @click="deleteQuotation" />
          </div>
        </div>
      </div>

      <!-- Sidebar sections (Side Panel layout from DB) -->
      <div v-if="sections.data" class="flex flex-1 flex-col justify-between overflow-hidden">
        <SidePanelLayout :sections="sections.data" doctype="CRM Quotation" :docname="props.quotationId"
          @reload="sections.reload" />
      </div>
    </Resizer>
  </div>

  <ErrorPage v-else-if="errorTitle" :errorTitle="errorTitle" :errorMessage="errorMessage" />

  <FilesUploader v-model="showFilesUploader" doctype="CRM Quotation" :docname="props.quotationId" @after="
    () => {
      activities?.all_activities?.reload()
      changeTabTo('Attachments')
    }
  " />

  <!-- v-if selain v-model: modal membaca lost_reason saat setup, jadi harus
       dibuat ulang tiap kali dibuka supaya isiannya tidak tertinggal. -->
  <LostReasonModal
    v-if="showLoseModal"
    v-model="showLoseModal"
    doctype="CRM Quotation"
    :onSave="markLose"
  />

  <!-- Konten cetak (tersembunyi di layar, tampil hanya saat print) -->
  <Teleport to="body">
    <div v-if="quotation.doc?.name" id="qp-print-root">
      <QuotationPrintContent :doc="quotation.doc" />
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  createDocumentResource,
  createResource,
  Breadcrumbs,
  Button,
  Dropdown,
  Tabs,
  Tooltip,
  Avatar,
  toast,
  call,
} from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import Resizer from '@/components/Resizer.vue'
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
import AssignTo from '@/components/AssignTo.vue'
import QuotationPrintContent from '@/components/Quotation/QuotationPrintContent.vue'
import LostReasonModal from '@/components/Modals/LostReasonModal.vue'
import { copyToClipboard } from '@/utils'
import { stashDuplicate } from '@/utils/duplicate'
import { getView } from '@/utils/view'
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
const isDirty = ref(false)
const originalDoc = ref(null)
const reload = ref(false)
const showFilesUploader = ref(false)
const activities = ref(null)
const converting = ref(false)

const { getFields } = getMeta('CRM Quotation')
// Preload meta child produk supaya lock kolom grid bisa dipasang.
const productMeta = getMeta('CRM Quotation Product')

// Quotation document
const quotation = createDocumentResource({
  doctype: 'CRM Quotation',
  name: props.quotationId,
  cache: ['quotation', props.quotationId],
  auto: true,
  onSuccess(doc) {
    originalDoc.value = JSON.stringify(doc)
    isDirty.value = false
  },
  onError(err) {
    errorTitle.value = __(
      err.exc_type === 'DoesNotExistError' ? 'Quotation Not Found' : 'Error',
    )
    errorMessage.value = __(err.messages?.[0] || 'An Error Occurred')
  },
})

// Sidebar layout (Side Panel from DB)
const sections = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections',
  params: { doctype: 'CRM Quotation' },
  auto: true,
})

watch(
  () => quotation.doc,
  (newDoc) => {
    if (newDoc && originalDoc.value) {
      isDirty.value = JSON.stringify(newDoc) !== originalDoc.value
    }
  },
  { deep: true },
)

// Kalkulasi live amount + net_total pada dokumen yang dipakai grid (DataFields).
const {
  document: gridDoc,
  assignees,
  setFieldHtml,
} = useDocument('CRM Quotation', props.quotationId)

// Account read-only: Frappe menyembunyikan field read-only yang kosong. Paksa selalu
// tampil di detail (samakan dengan halaman New) supaya konsisten dan tidak "hilang".
if (!gridDoc.fieldPropertyOverrides) gridDoc.fieldPropertyOverrides = {}
gridDoc.fieldPropertyOverrides.account = {
  ...(gridDoc.fieldPropertyOverrides.account || {}),
  hidden: false,
}

// Panel "Inquiry Details" di sidebar.
//
// Sengaja diisi dari halaman ini, bukan dari form script (doctypes/crm_quotation/form.js).
// setupFormScript() memanggil triggerOnRender() tanpa await, sehingga kegagalan apa pun
// di onRender() lenyap sebagai unhandled rejection dan field-nya diam-diam tetap kosong.
// setFieldHtml di sini menulis ke objek useDocument yang sama persis dengan yang dibaca
// SidePanelLayout, jadi tidak ada lagi perantara yang bisa gagal tanpa jejak.
const escapeHtml = (v) =>
  String(v).replace(
    /[&<>"]/g,
    (s) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[s],
  )

// Status inquiry diberi warna: hijau bila menang, merah bila kalah, netral selama
// masih berjalan. Nilai lain apa pun jatuh ke netral, jadi aman kalau master
// CRM Inquiry Status ditambah.
function statusToneClass(status) {
  if (status === 'Won') return 'text-ink-green-3'
  if (status === 'Lost') return 'text-ink-red-3'
  return 'text-ink-gray-7'
}

function inquiryDetailsHtml(detail) {
  const href = `/crm/inquiries/${encodeURIComponent(detail.name)}`
  const header =
    `<a href="${href}" class="mb-2 flex items-center justify-between gap-2 rounded bg-surface-gray-1 px-2 py-1.5 hover:bg-surface-gray-2">` +
    `<span class="shrink-0 text-xs text-ink-gray-5">Inquiry</span>` +
    `<span class="truncate text-xs font-medium text-ink-blue-3">${escapeHtml(detail.name)}</span>` +
    `</a>`

  const row = ({ label, value }) => {
    const isStatus = label === 'Status'
    let valueHtml
    if (!value) {
      valueHtml = `<span class="text-ink-gray-4">-</span>`
    } else if (isStatus) {
      valueHtml =
        `<span class="inline-flex rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs font-medium ${statusToneClass(value)}">` +
        `${escapeHtml(value)}</span>`
    } else {
      valueHtml = escapeHtml(value)
    }
    // border-t + first:border-t-0, bukan divide-y: palet divideColor Tailwind belum
    // tentu memuat outline-gray-2, sedangkan borderColor pasti.
    return (
      `<div class="flex items-start gap-2 border-t border-outline-gray-2 px-2 py-1.5 first:border-t-0">` +
      `<span class="w-[45%] shrink-0 text-xs leading-5 text-ink-gray-5">${escapeHtml(label)}</span>` +
      `<span class="flex-1 whitespace-pre-line break-words text-xs leading-5 text-ink-gray-8">${valueHtml}</span>` +
      `</div>`
    )
  }

  const rows = (detail.rows || []).map(row).join('')
  return (
    `<div class="w-full">${header}` +
    `<div class="rounded border border-outline-gray-2">${rows}</div>` +
    `</div>`
  )
}

watch(
  () => gridDoc.doc?.inquiry,
  async (inquiry) => {
    if (!inquiry) {
      setFieldHtml('inquiry_details', '')
      return
    }
    try {
      const detail = await call('crm_cakra.api.quotation.get_inquiry_detail', {
        name: inquiry,
      })
      setFieldHtml('inquiry_details', detail?.name ? inquiryDetailsHtml(detail) : '')
    } catch (e) {
      setFieldHtml('inquiry_details', '')
      console.error('[Quotation] gagal memuat detail inquiry:', e)
    }
  },
  { immediate: true },
)
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

// Quotation yang sudah Converted → semua field (termasuk kolom grid produk) read-only.
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
  if (!fields.length) return // meta belum termuat; watcher akan fire lagi saat siap.
  fields.forEach((f) => {
    if (!f.fieldname) return
    lockField(f.fieldname)
    // Tabel child: kunci tiap kolom via dot-notation parent.child (Grid baca key ini).
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

// Tabs
const tabs = computed(() => [
  { name: 'Data', label: __('Data'), icon: DetailsIcon },
  { name: 'Activity', label: __('Activity'), icon: ActivityIcon },
  { name: 'Comments', label: __('Comments'), icon: CommentIcon },
  { name: 'Notes', label: __('Notes'), icon: NoteIcon },
  { name: 'Attachments', label: __('Attachments'), icon: AttachmentIcon },
])

const { tabIndex } = useActiveTabManager(tabs, 'lastQuotationTab')

function changeTabTo(name) {
  const idx = tabs.value.findIndex((t) => t.name === name)
  if (idx >= 0) tabIndex.value = idx
}

// Status yang bisa dipilih user dari dropdown header. 'Converted' sengaja tidak
// ada di sini: nilainya hanya di-set convert_to_estimation() untuk mengunci
// quotation, dan dokumen Converted ditangani cabang v-if di atas.
const SELECTABLE_STATES = ['Draft', 'Sent', 'Waiting', 'Win', 'Lose']

const stateOptions = computed(() => {
  const current = quotation.doc?.state || 'Draft'
  return SELECTABLE_STATES.filter((state) => state !== current).map((state) => ({
    label: state,
    onClick: () => updateState(state),
  }))
})

function getStateColor(state) {
  return {
    Draft: 'text-ink-gray-5',
    Sent: 'text-ink-blue-3',
    // amber, bukan orange: text-ink-orange-* tidak ada di palet dan tidak
    // pernah ter-generate ke CSS (warnanya diam-diam tidak muncul).
    Waiting: 'text-ink-amber-3',
    Win: 'text-ink-green-3',
    Lose: 'text-ink-red-4',
    Converted: 'text-ink-green-3',
  }[state] || 'text-ink-gray-5'
}

const showLoseModal = ref(false)

const stateError = (e) =>
  toast.error(e?.messages?.[0] || e?.message || __('Gagal mengubah status'))

function updateState(newState) {
  // Lose butuh Lost Reason di inquiry-nya, jadi tanyakan dulu lewat modal
  // daripada membiarkan server menolak setelah user memilih.
  if (newState === 'Lose') {
    showLoseModal.value = true
    return
  }
  quotation.setValue
    .submit({ state: newState })
    .then(() => toast.success(__('Status diubah ke {0}', [newState])))
    // Tanpa catch, penolakan server hilang dan status seolah gagal tanpa sebab.
    .catch(stateError)
}

// Alasan kalah ditulis ke inquiry dan status quotation diubah dalam satu panggilan,
// supaya tidak ada keadaan setengah jadi (alasan tersimpan tapi status tidak, atau
// sebaliknya) yang membuat inquiry menolak penyimpanan berikutnya.
function markLose({ lostReason, lostNotes }) {
  call('crm_cakra.api.quotation.mark_quotation_lost', {
    quotation: props.quotationId,
    lost_reason: lostReason,
    lost_notes: lostNotes,
  })
    .then(() => {
      quotation.reload()
      toast.success(__('Status diubah ke {0}', ['Lose']))
    })
    .catch(stateError)
}

async function saveQuotation() {
  // Simpan gridDoc (dokumen yang benar-benar diedit form/grid), bukan objek
  // `quotation` terpisah — biar konsisten dengan tombol Save di tab Data.
  try {
    await gridDoc.save.submit()
    toast.success(__('Saved'))
  } catch (e) {
    toast.error(e.message || __('Failed to save'))
  }
}

const duplicating = ref(false)
function duplicateQuotation() {
  // Salin isi ke form New (belum disimpan, nomor belum di-generate).
  // Kosongkan inquiry & account sesuai permintaan.
  stashDuplicate('CRM Quotation', gridDoc.doc, [
    'number', 'inquiry', 'account', 'account_name', 'printed_by',
  ])
  router.push({ name: 'NewQuotation' })
}

function printQuotation() {
  // Pakai Print Format Frappe "Print Out" (bukan cetak Vue in-page).
  const params = new URLSearchParams({
    doctype: 'CRM Quotation',
    name: props.quotationId,
    format: 'Quotation Print Out',
    trigger_print: '1',
  })
  window.open(`/printview?${params.toString()}`, '_blank')
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
/* Print in-page: sembunyikan UI app, tampilkan hanya dokumen cetak. */
#qp-print-root {
  display: none;
}
@media print {
  body > *:not(#qp-print-root) {
    display: none !important;
  }
  #qp-print-root {
    display: block !important;
  }
}
</style>