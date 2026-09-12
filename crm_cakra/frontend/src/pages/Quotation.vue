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

      <!-- Hilang begitu statusnya Waiting/Approved: permintaannya sudah jalan,
           dan tombol yang tetap ada mengundang permintaan dobel. -->
      <Button v-if="canRequestProcurement" :label="__('Request Procurement')"
        @click="showRequestProcurement = true" />

      <Button v-if="canConvert" variant="solid" theme="blue" :label="__('Convert to Estimation')"
        :loading="converting" @click="confirmConvert" />

      <!-- Margin tipis: tombolnya hanya muncul buat yang memang berwenang, tapi yang
           menjaga tetap server -- before_print menolak cetak tanpa persetujuan. -->
      <Button v-if="needsApproval && canApproveMargin" variant="solid" theme="green"
        :label="__('Approve Margin')" :loading="approving" @click="approveMargin" />

      <Button v-else-if="needsApproval" :label="__('Awaiting {0}', [__(quotation.doc.approval_required)])" disabled>
        <template #prefix>
          <IndicatorIcon class="text-ink-amber-3" />
        </template>
      </Button>

      <Button v-else-if="quotation.doc?.approved_by" variant="subtle" theme="green"
        :label="__('Margin Approved')" :tooltip="__('Approved by {0}', [quotation.doc.approved_by])"
        @click="revokeMargin" />

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

        <!-- Inquiry asal ditampilkan dengan layout milik CRM Inquiry sendiri,
             bukan salinan ringkasannya: satu sumber format, dan field yang
             ditambah di Inquiry ikut muncul di sini tanpa disentuh lagi. -->
        <div v-else-if="tab.name === 'Inquiry'" class="flex-1 overflow-y-auto px-5 pb-8">
          <DataFields
            v-if="quotation.doc?.inquiry"
            :key="quotation.doc.inquiry"
            doctype="CRM Inquiry"
            :docname="quotation.doc.inquiry"
          />
          <div v-else class="pt-8 text-center text-base text-ink-gray-5">
            {{ __('Quotation ini tidak berasal dari inquiry.') }}
          </div>
        </div>

        <ProcurementTab v-else-if="tab.name === 'Procurement'" :quotationId="props.quotationId" />

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
            <Button :tooltip="__('New Meeting')" :icon="CalendarIcon" @click="showMeetingModal = true" />
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

  <MeetingModal v-model="showMeetingModal" :prefill="meetingPrefill" />

  <RequestProcurementModal
    v-model="showRequestProcurement"
    :quotationId="props.quotationId"
    @sent="onProcurementRequested"
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
import InquiriesIcon from '@/components/Icons/InquiriesIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import AttachmentIcon from '@/components/Icons/AttachmentIcon.vue'
import Activities from '@/components/Activities/Activities.vue'
import ProcurementTab from '@/components/Procurement/ProcurementTab.vue'
import LucideShoppingCart from '~icons/lucide/shopping-cart'
import FilesUploader from '@/components/FilesUploader/FilesUploader.vue'
import SidePanelLayout from '@/components/SidePanelLayout.vue'
import DataFields from '@/components/Activities/DataFields.vue'
import AssignTo from '@/components/AssignTo.vue'
import { usersStore } from '@/stores/users'
import QuotationPrintContent from '@/components/Quotation/QuotationPrintContent.vue'
import LostReasonModal from '@/components/Modals/LostReasonModal.vue'
import MeetingModal from '@/components/Modals/MeetingModal.vue'
import RequestProcurementModal from '@/components/Modals/RequestProcurementModal.vue'
import CalendarIcon from '@/components/Icons/CalendarIcon.vue'
import MeetingIcon from '@/components/Icons/MeetingIcon.vue'
import { copyToClipboard } from '@/utils'
import { stashDuplicate } from '@/utils/duplicate'
import { getView } from '@/utils/view'
import { useDocument } from '@/data/document'
import { openGmapRoute, fetchDistance } from '@/utils/gmap'
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

const showMeetingModal = ref(false)
const meetingPrefill = computed(() => ({
  subject: `Meeting - ${quotation.doc?.account_name || quotation.doc?.account || ''}`.trim(),
  quotation: quotation.doc?.name || '',
  inquiry: quotation.doc?.inquiry || '',
  organization: quotation.doc?.account || '',
  contact: quotation.doc?.contact_name || '',
}))
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
const { document: gridDoc, assignees } = useDocument(
  'CRM Quotation',
  props.quotationId,
)

// Account read-only: Frappe menyembunyikan field read-only yang kosong. Paksa selalu
// tampil di detail (samakan dengan halaman New) supaya konsisten dan tidak "hilang".
if (!gridDoc.fieldPropertyOverrides) gridDoc.fieldPropertyOverrides = {}
gridDoc.fieldPropertyOverrides.account = {
  ...(gridDoc.fieldPropertyOverrides.account || {}),
  hidden: false,
}

// Tombol "Check in GMap" ditangani di sini, bukan di form script: Field.vue
// memanggil field.click langsung, sedangkan jalur triggerButton harus lolos
// controller dulu -- di halaman ini tombolnya berakhir tanpa reaksi apa pun.
gridDoc.fieldPropertyOverrides.check_gmap = {
  ...(gridDoc.fieldPropertyOverrides.check_gmap || {}),
  click: openGmapRoute,
}

// KM dihitung HANYA lewat tombol "Get KM". Dulu terisi otomatis tiap rute
// berubah, jadi angka ketikan user tertimpa diam-diam oleh mesin rute.
gridDoc.fieldPropertyOverrides.get_km = {
  ...(gridDoc.fieldPropertyOverrides.get_km || {}),
  error: '',
  click: (doc) => fetchDistance(doc, gridDoc.fieldPropertyOverrides),
}

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
// Convert hanya untuk quotation yang menang. Statusnya harus dinaikkan ke Win
// dulu -- estimasi dibuat dari pekerjaan yang jadi, bukan dari penawaran yang
// masih berjalan.
const canConvert = computed(
  () => quotation.doc?.state === 'Win' && !quotation.doc.is_void,
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
  { name: 'Inquiry', label: __('Inquiry'), icon: InquiriesIcon },
  { name: 'Procurement', label: __('Procurement'), icon: LucideShoppingCart },
  { name: 'Comments', label: __('Comments'), icon: CommentIcon },
  { name: 'Meetings', label: __('Meetings'), icon: MeetingIcon },
  { name: 'Notes', label: __('Notes'), icon: NoteIcon },
  { name: 'Attachments', label: __('Attachments'), icon: AttachmentIcon },
  { name: 'Activity', label: __('Activity'), icon: ActivityIcon },
])

const { tabIndex } = useActiveTabManager(tabs, 'lastQuotationTab', 'data')

function changeTabTo(name) {
  const idx = tabs.value.findIndex((t) => t.name === name)
  if (idx >= 0) tabIndex.value = idx
}

// Status yang bisa dipilih user dari dropdown header. 'Converted' sengaja tidak
// ada di sini: nilainya hanya di-set convert_to_estimation() untuk mengunci
// quotation, dan dokumen Converted ditangani cabang v-if di atas.
const SELECTABLE_STATES = ['Draft', 'Sent', 'Waiting', 'Approved', 'Win', 'Lose']

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
    Approved: 'text-ink-blue-3',
    Win: 'text-ink-green-3',
    Lose: 'text-ink-red-4',
    Converted: 'text-ink-green-3',
  }[state] || 'text-ink-gray-5'
}

const showRequestProcurement = ref(false)

// Hanya quotation yang belum diminta -- daftar statusnya sama dengan gerbang di
// server (REQUESTABLE_STATES di api/procurement.py).
const canRequestProcurement = computed(
  () => ['Draft', 'Sent'].includes(quotation.doc?.state) && !quotation.doc?.is_void,
)

// Persetujuan margin. `approval_required` diisi server tiap simpan; kosong berarti
// marginnya sehat, saklarnya mati, atau dokumennya tidak punya costing untuk dinilai.
const APPROVAL_TIERS = ['Sales Manager', 'Sales Master Manager']
const approving = ref(false)

const needsApproval = computed(
  () => Boolean(quotation.doc?.approval_required) && !quotation.doc?.approved_by,
)

// Tingkat yang lebih ketat boleh menyetujui yang lebih longgar, tidak sebaliknya --
// cerminan aturan yang sama di approve_pricing. Ini cuma menyembunyikan tombol;
// penolakannya tetap di server.
const canApproveMargin = computed(() => {
  const needed = quotation.doc?.approval_required
  if (!needed) return false
  const roles = usersStore().getUser()?.roles || []
  if (roles.includes('System Manager')) return true
  return APPROVAL_TIERS.slice(APPROVAL_TIERS.indexOf(needed)).some((r) =>
    roles.includes(r),
  )
})

async function approveMargin() {
  approving.value = true
  try {
    await call(
      'crm_cakra.fcrm.doctype.crm_quotation.crm_quotation.approve_pricing',
      { quotation: props.quotationId },
    )
    toast.success(__('Margin approved'))
    quotation.reload()
  } finally {
    approving.value = false
  }
}

async function revokeMargin() {
  await call(
    'crm_cakra.fcrm.doctype.crm_quotation.crm_quotation.revoke_pricing_approval',
    { quotation: props.quotationId },
  )
  toast.success(__('Margin approval revoked'))
  quotation.reload()
}

function onProcurementRequested() {
  quotation.reload()
  gridDoc.reload?.()
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

// Aturan cetak dibaca saat halaman dibuka, bukan saat tombol ditekan: jawaban
// yang datang setelah klik membuat window.open jatuh di luar gesture user dan
// diblokir browser tanpa bunyi.
const printRules = createResource({
  url: 'crm_cakra.api.quotation.get_print_rules',
  cache: 'quotation-print-rules',
  auto: true,
  initialData: { locked: false, states: [] },
})

function printQuotation() {
  const rules = printRules.data
  if (rules?.locked && !rules.states.includes(quotation.doc?.state)) {
    toast.error(
      __('Quotation berstatus {0} tidak bisa dicetak. Statusnya harus {1}.', [
        __(quotation.doc?.state || '-'),
        rules.states.join(' / '),
      ]),
    )
    return
  }
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
      'Isi quotation ini akan dipindahkan ke form estimasi baru untuk Anda periksa. Estimasinya baru tersimpan setelah Anda menekan Save di sana, dan saat itulah quotation ini dikunci sebagai Converted.',
    ),
    actions: [
      {
        label: __('Lanjut'),
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

// Convert TIDAK menyimpan apa pun. Server hanya menerjemahkan isi quotation ke
// bentuk estimasi, lalu form New Estimation dibuka dengan isian itu. Dokumennya
// lahir saat user menekan Save di sana -- dan di situ pula quotation dikunci
// (after_insert di CRM Estimation), jadi selama belum disimpan tidak ada yang
// berubah di sini.
async function doConvert() {
  converting.value = true
  try {
    const doc = await call(
      'crm_cakra.fcrm.doctype.crm_quotation.crm_quotation.build_estimation',
      { quotation: props.quotationId },
    )
    stashDuplicate('CRM Estimation', doc)
    router.push({ name: 'NewEstimation' })
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