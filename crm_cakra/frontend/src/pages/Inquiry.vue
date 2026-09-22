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
      <CustomActions
        v-if="document._actions?.length"
        :actions="document._actions"
      />
      <CustomActions
        v-if="document.actions?.length"
        :actions="document.actions"
      />
      <AssignTo
        v-model="assignees.data"
        doctype="CRM Inquiry"
        :docname="inquiryId"
      />
      <Button
        :label="__('Submit to Procurement')"
        :loading="preparingProcurement"
        @click="submitToProcurement"
      />
      <Dropdown v-if="doc?.status" :options="statuses" placement="right">
        <template #default="{ open }">
          <Button
            v-if="doc.status"
            :label="statusLabel(doc.status)"
            :iconRight="open ? 'chevron-up' : 'chevron-down'"
          >
            <template #prefix>
              <IndicatorIcon :class="getInquiryStatus(doc.status).color" />
            </template>
          </Button>
        </template>
      </Dropdown>
    </template>
  </LayoutHeader>
  <div v-if="doc.name" class="flex h-full overflow-hidden">
    <Tabs
      v-model="tabIndex"
      as="div"
      :tabs="tabs"
      class="flex flex-1 overflow-hidden flex-col [&_[role='tab']]:px-0 [&_[role='tab']]:shrink-0 [&_[role='tablist']]:px-5 [&_[role='tablist']::-webkit-scrollbar]:h-0 [&_[role='tablist']]:min-h-[45px] [&_[role='tablist']]:gap-7.5 [&_[role='tabpanel']:not([hidden])]:flex [&_[role='tabpanel']:not([hidden])]:grow"
    >
      <template #tab-panel="{ tab }">
        <ProcurementInquiryTab
          v-if="tab.name === 'Procurement'"
          :inquiry="inquiryId"
          :info="procurementInfo.data?.name ? procurementInfo.data : null"
        />
        <Activities
          v-else
          ref="activities"
          v-model:reload="reload"
          v-model:tabIndex="tabIndex"
          doctype="CRM Inquiry"
          :docname="inquiryId"
          :tabs="tabs"
          :dataReadonly="dataLocked"
          @beforeSave="beforeStatusChange"
          @afterSave="reloadResources"
        />
      </template>
    </Tabs>
    <Resizer side="right" class="flex flex-col justify-between border-l">
      <div
        class="flex h-[45px] cursor-copy items-center border-b px-5 py-2.5 text-lg font-medium text-ink-gray-9"
        @click="copyToClipboard(inquiryId)"
      >
        {{ __(inquiryId) }}
      </div>
      <div class="flex items-center justify-start gap-5 border-b p-5">
        <Tooltip :text="__('Organization Logo')">
          <div class="group relative size-12">
            <Avatar
              size="3xl"
              class="size-12"
              :label="title"
              :image="organization?.organization_logo"
            />
          </div>
        </Tooltip>
        <div class="flex flex-col gap-2.5 truncate text-ink-gray-9">
          <Tooltip :text="organization?.name || __('Set an Organization')">
            <div class="truncate text-2xl font-medium">
              {{ title }}
            </div>
          </Tooltip>
          <div class="flex gap-1.5">
            <Button
              v-if="callEnabled"
              :tooltip="__('Make a Call')"
              :icon="PhoneIcon"
              @click="triggerCall"
            />

            <Button
              :tooltip="__('Send an Email')"
              :icon="Email2Icon"
              @click="
                doc.email
                  ? openEmailBox()
                  : toast.error(
                      __('Please set an email address to send emails'),
                    )
              "
            />

            <Button
              :tooltip="__('New Meeting')"
              :icon="CalendarIcon"
              @click="showMeetingModal = true"
            />

            <Button
              :tooltip="__('Print')"
              icon="printer"
              @click="printInquiry"
            />

            <Button
              :tooltip="__('Duplicate')"
              icon="copy"
              :loading="duplicating"
              @click="duplicateInquiry"
            />

            <Button
              :tooltip="__('Go to Website')"
              :icon="LinkIcon"
              @click="
                doc.website
                  ? openWebsite(doc.website)
                  : toast.error(__('Please set a website to visit'))
              "
            />

            <Button
              :tooltip="__('Attach a File')"
              :icon="AttachmentIcon"
              @click="showFilesUploader = true"
            />

            <Button
              v-if="canDelete"
              :tooltip="__('Delete')"
              variant="subtle"
              icon="trash-2"
              theme="red"
              @click="deleteInquiry"
            />
          </div>
        </div>
      </div>
      <SLASection
        v-if="doc.sla_status"
        v-model="doc"
        @updateField="updateField"
      />
      <div
        v-if="sections.data"
        class="flex flex-1 flex-col justify-between overflow-hidden"
      >
        <SidePanelLayout
          :sections="sections.data"
          doctype="CRM Inquiry"
          :docname="inquiryId"
          @reload="sections.reload"
          @beforeFieldChange="beforeStatusChange"
          @afterFieldChange="reloadResources"
        >
          <template #actions="{ section }">
            <ContactsAddButton
              v-if="section.name == 'contacts_section'"
              doctype="CRM Inquiry"
              :docname="inquiryId"
              :organization="doc.organization"
            />
          </template>
          <template #default="{ section }">
            <ContactsPanel
              v-if="section.name == 'contacts_section'"
              doctype="CRM Inquiry"
              :docname="inquiryId"
            />
          </template>
        </SidePanelLayout>
      </div>
    </Resizer>
  </div>
  <ErrorPage
    v-else-if="errorTitle"
    :errorTitle="errorTitle"
    :errorMessage="errorMessage"
  />
  <OrganizationModal
    v-if="showOrganizationModal"
    v-model="showOrganizationModal"
    :data="_organization"
    :options="{
      redirect: false,
      afterInsert: (_doc) => updateField('organization', _doc.name),
    }"
  />
  <MeetingModal v-model="showMeetingModal" :prefill="meetingPrefill" />
  <FilesUploader
    v-model="showFilesUploader"
    doctype="CRM Inquiry"
    :docname="inquiryId"
    @after="
      () => {
        activities?.all_activities?.reload()
        changeTabTo('attachments')
      }
    "
  />
  <DeleteLinkedDocModal
    v-if="showDeleteLinkedDocModal"
    v-model="showDeleteLinkedDocModal"
    :doctype="'CRM Inquiry'"
    :docname="inquiryId"
    name="Inquiries"
  />
  <LostReasonModal
    v-if="showLostReasonModal"
    v-model="showLostReasonModal"
    doctype="CRM Inquiry"
    :document="document"
  />
  <SubmitProcurementModal
    v-if="procurementInfo.data?.name"
    v-model="showSubmitProcurement"
    :procurementId="procurementInfo.data.name"
    :inquiry="inquiryId"
    @sent="procurementInfo.reload()"
  />
</template>
<script setup>
import DeleteLinkedDocModal from '@/components/DeleteLinkedDocModal.vue'
import ErrorPage from '@/components/ErrorPage.vue'
import Icon from '@/components/Icon.vue'
import Resizer from '@/components/Resizer.vue'
import ActivityIcon from '@/components/Icons/ActivityIcon.vue'
import EmailIcon from '@/components/Icons/EmailIcon.vue'
import Email2Icon from '@/components/Icons/Email2Icon.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import DetailsIcon from '@/components/Icons/DetailsIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import WhatsAppIcon from '@/components/Icons/WhatsAppIcon.vue'
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import LinkIcon from '@/components/Icons/LinkIcon.vue'
import AttachmentIcon from '@/components/Icons/AttachmentIcon.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import Activities from '@/components/Activities/Activities.vue'
import OrganizationModal from '@/components/Modals/OrganizationModal.vue'
import LostReasonModal from '@/components/Modals/LostReasonModal.vue'
import AssignTo from '@/components/AssignTo.vue'
import FilesUploader from '@/components/FilesUploader/FilesUploader.vue'
import MeetingModal from '@/components/Modals/MeetingModal.vue'
import CalendarIcon from '@/components/Icons/CalendarIcon.vue'
import MeetingIcon from '@/components/Icons/MeetingIcon.vue'
import Link from '@/components/Controls/Link.vue'
import MoneyIcon from '@/components/Icons/MoneyIcon.vue'
import ProcurementInquiryTab from '@/components/Procurement/ProcurementInquiryTab.vue'
import SubmitProcurementModal from '@/components/Modals/SubmitProcurementModal.vue'
import SidePanelLayout from '@/components/SidePanelLayout.vue'
import ContactsPanel from '@/components/ContactsPanel.vue'
import ContactsAddButton from '@/components/ContactsAddButton.vue'
import SLASection from '@/components/SLASection.vue'
import CustomActions from '@/components/CustomActions.vue'
import {
  openWebsite,
  setupCustomizations,
  copyToClipboard,
  isTranslatable,
} from '@/utils'
import { stashDuplicate } from '@/utils/duplicate'
import { getView } from '@/utils/view'
import { getSettings } from '@/stores/settings'
import { globalStore } from '@/stores/global'
import { statusesStore } from '@/stores/statuses'
import { getMeta } from '@/stores/meta'
import { useDocument } from '@/data/document'
import { useContacts } from '@/composables/contacts'
import { whatsappEnabled } from '@/composables/whatsapp'
import { callEnabled } from '@/composables/telephony'
import { useBroadcast } from '@/composables/useBroadcast'
import {
  createResource,
  Dropdown,
  Tooltip,
  Avatar,
  Tabs,
  Breadcrumbs,
  call,
  usePageMeta,
  toast,
} from 'frappe-ui'
import { useOnboarding } from 'frappe-ui/frappe'
import {
  ref,
  computed,
  h,
  onMounted,
  onBeforeUnmount,
  nextTick,
  watch,
} from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useActiveTabManager } from '@/composables/useActiveTabManager'

const { on } = useBroadcast()
const { brand } = getSettings()
const { $dialog, $socket, makeCall } = globalStore()
const { statusOptions, getInquiryStatus } = statusesStore()
const { doctypeMeta } = getMeta('CRM Inquiry')

const { updateOnboardingStep, isOnboardingStepsCompleted } =
  useOnboarding('frappecrm')

const route = useRoute()
const router = useRouter()

const props = defineProps({
  inquiryId: { type: String, required: true },
})

const errorTitle = ref('')
const errorMessage = ref('')
const showDeleteLinkedDocModal = ref(false)

const {
  triggerOnChange,
  triggerOnRender,
  assignees,
  permissions,
  document,
  scripts,
  error,
} = useDocument('CRM Inquiry', props.inquiryId)

const canDelete = computed(() => permissions.data?.permissions?.delete || false)

const doc = computed(() => document.doc || {})

const duplicating = ref(false)
function duplicateInquiry() {
  // Salin isi ke form New Inquiry (belum disimpan, nomor belum di-generate).
  stashDuplicate('CRM Inquiry', document.doc)
  router.push({ name: 'NewInquiry' })
}

function printInquiry() {
  // Pakai Print Format Frappe "Inquiry Print Out" (mirip flow Quotation).
  const params = new URLSearchParams({
    doctype: 'CRM Inquiry',
    name: props.inquiryId,
    format: 'Inquiry Print Out',
    trigger_print: '1',
  })
  window.open(`/printview?${params.toString()}`, '_blank')
}

watch(error, (err) => {
  if (err) {
    errorTitle.value = __(
      err.exc_type == 'DoesNotExistError'
        ? 'Document Not Found'
        : 'Error Occurred',
    )
    errorMessage.value = __(err.messages?.[0] || 'An Error Occurred')
  } else {
    errorTitle.value = ''
    errorMessage.value = ''
  }
})

watch(
  () => document.doc,
  async (_doc) => {
    if (scripts.data?.length) {
      let s = await setupCustomizations(scripts.data, {
        doc: _doc,
        $dialog,
        $socket,
        router,
        toast,
        updateField,
        createToast: toast.create,
        deleteDoc: deleteInquiry,
        call,
      })
      document._actions = s.actions || []
      document._statuses = s.statuses || []
    }
  },
  { once: true },
)

const organizationDocument = ref(null)

watch(
  () => doc.value.organization,
  (org) => {
    if (org && !organizationDocument.value?.doc) {
      let { document: _organizationDocument } = useDocument(
        'CRM Organization',
        org,
      )
      organizationDocument.value = _organizationDocument
    }
  },
  { immediate: true },
)

const organization = computed(() => organizationDocument.value?.doc || {})

onMounted(async () => {
  $socket.on('crm_customer_created', () => {
    toast.success(__('Customer Created Successfully'))
  })
  if (document.doc) await triggerOnRender()
})

onBeforeUnmount(() => {
  $socket.off('crm_customer_created')
})

const reload = ref(false)
const showOrganizationModal = ref(false)
const showFilesUploader = ref(false)

const showMeetingModal = ref(false)
const meetingPrefill = computed(() => ({
  subject: `Meeting - ${doc.value?.organization || ''}`.trim(),
  inquiry: doc.value?.name || '',
  organization: doc.value?.organization || '',
  contact: doc.value?.contact || '',
}))
const _organization = ref({})

const breadcrumbs = computed(() => {
  let items = [{ label: __('Inquiries'), route: { name: 'Inquiries' } }]

  if (route.query.view || route.query.viewType) {
    let view = getView(route.query.view, route.query.viewType, 'CRM Inquiry')
    if (view) {
      items.push({
        label: __(view.label),
        icon: view.icon,
        route: {
          name: 'Inquiries',
          params: { viewType: route.query.viewType },
          query: { view: route.query.view },
        },
      })
    }
  }

  items.push({
    label: title.value,
    route: { name: 'Inquiry', params: { inquiryId: props.inquiryId } },
  })
  return items
})

const title = computed(() => {
  let t = doctypeMeta.value?.title_field || 'name'
  return doc.value?.[t] || props.inquiryId
})

const statuses = computed(() => {
  let customStatuses = document.statuses?.length
    ? document.statuses
    : document._statuses || []
  return statusOptions('inquiry', customStatuses, triggerStatusChange).map(
    (opt) => ({ ...opt, label: opt.value }),
  )
})

usePageMeta(() => {
  return {
    title: title.value,
    icon: brand.favicon,
  }
})

const tabs = computed(() => {
  let tabOptions = [
    {
      name: 'Data',
      label: __('Data'),
      icon: DetailsIcon,
    },
    {
      name: 'Procurement',
      label: __('Procurement'),
      icon: MoneyIcon,
    },
    {
      name: 'Emails',
      label: __('Emails'),
      icon: EmailIcon,
    },
    {
      name: 'WhatsApp',
      label: __('WhatsApp'),
      icon: WhatsAppIcon,
      condition: () => whatsappEnabled.value,
    },
    {
      name: 'Comments',
      label: __('Comments'),
      icon: CommentIcon,
    },
    {
      name: 'Tasks',
      label: __('Tasks'),
      icon: TaskIcon,
    },
    {
      name: 'Meetings',
      label: __('Meetings'),
      icon: MeetingIcon,
    },
    {
      name: 'Notes',
      label: __('Notes'),
      icon: NoteIcon,
    },
    {
      name: 'Attachments',
      label: __('Attachments'),
      icon: AttachmentIcon,
    },
    {
      name: 'Calls',
      label: __('Calls'),
      icon: PhoneIcon,
    },
    {
      name: 'Activity',
      label: __('Activity'),
      icon: ActivityIcon,
    },
  ]
  return tabOptions.filter((tab) => (tab.condition ? tab.condition() : true))
})

const { tabIndex, changeTabTo } = useActiveTabManager(
  tabs,
  'lastInquiryTab',
  'data',
)

// Dokumen CRM Procurement inquiry ini, kalau sudah ada. Dibaca sekali di sini
// dan dipakai berdua: tombol Submit di header dan tab Procurement. Dibaca, bukan
// dibuat -- dokumen baru lahir saat orangnya menekan Submit, kalau tidak setiap
// inquiry yang kebetulan dibuka akan menambah baris kosong di daftar Procurement.
const procurementInfo = createResource({
  url: 'frappe.client.get_value',
  params: {
    doctype: 'CRM Procurement',
    filters: { inquiry: props.inquiryId },
    fieldname: ['name', 'status', 'requested_to', 'submitted_on', 'remark'],
  },
  auto: true,
})

// Sejak dikirim ke procurement, isi inquiry dibekukan -- yang sedang dihargai
// harus sama dengan yang dibaca procurement. Penolakan sungguhannya di server
// (CRM Inquiry.protect_locked_status); ini supaya orang tidak mengetik sia-sia.
const LOCKED_STATUSES = ['Submit', 'Approved']
const dataLocked = computed(() => LOCKED_STATUSES.includes(doc.value?.status))

const showSubmitProcurement = ref(false)
const preparingProcurement = ref(false)

async function submitToProcurement() {
  preparingProcurement.value = true
  try {
    if (!procurementInfo.data?.name) {
      // add_inquiry idempoten: kalau orang lain sudah menambahkan inquiry ini,
      // yang kembali dokumen yang sama, bukan error.
      await call('crm_cakra.api.procurement.add_inquiry', {
        inquiry: props.inquiryId,
      })
      await procurementInfo.reload()
    }
    showSubmitProcurement.value = true
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Error'))
  } finally {
    preparingProcurement.value = false
  }
}

const sections = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections',
  params: { doctype: 'CRM Inquiry' },
  transform: (data) => getParsedSections(data),
})

on('reload-inquiry-sections', () => sections.reload())

if (!sections.data) sections.fetch()

function getParsedSections(_sections) {
  _sections.forEach((section) => {
    if (section.name == 'contacts_section') return
    section.columns[0].fields.forEach((field) => {
      if (field.fieldname == 'organization') {
        field.create = (value, close) => {
          _organization.value.organization_name = value
          showOrganizationModal.value = true
          close()
        }
        field.link = (org) =>
          router.push({
            name: 'Organization',
            params: { organizationId: org },
          })
      }
    })
  })
  return _sections
}

const { contacts: inquiryContacts } = useContacts(
  'CRM Inquiry',
  props.inquiryId,
)

function triggerCall() {
  let primaryContact = inquiryContacts.data?.find((c) => c.is_primary)
  let mobile_no = primaryContact.mobile_no || null

  if (!primaryContact) {
    toast.error(__('No Primary Contact Set'))
    return
  }

  if (!mobile_no) {
    toast.error(__('No Mobile Number Set'))
    return
  }

  makeCall(mobile_no)
}

async function triggerStatusChange(value) {
  await triggerOnChange('status', value)
  setLostReason()
}

function updateField(name, value) {
  if (name == 'status' && !isOnboardingStepsCompleted.value) {
    updateOnboardingStep('change_inquiry_status')
  }

  value = Array.isArray(name) ? '' : value
  let oldValues = Array.isArray(name) ? {} : doc.value[name]

  if (Array.isArray(name)) {
    name.forEach((field) => (doc.value[field] = value))
  } else {
    doc.value[name] = value
  }

  document.save.submit(null, {
    onSuccess: () => (reload.value = true),
    onError: (err) => {
      if (Array.isArray(name)) {
        name.forEach((field) => (doc.value[field] = oldValues[field]))
      } else {
        doc.value[name] = oldValues
      }
      toast.error(err.messages?.[0] || __('Error updating field'))
    },
  })
}

function deleteInquiry() {
  showDeleteLinkedDocModal.value = true
}

const activities = ref(null)

async function openEmailBox() {
  let currentTab = tabs.value[tabIndex.value]
  if (!['Emails', 'Comments', 'Activities'].includes(currentTab.name)) {
    // Tab Procurement tidak merender Activities, jadi pindah tabnya lewat
    // manager -- activities.value masih null selama tab itu yang aktif.
    changeTabTo('emails')
    await nextTick()
  }
  nextTick(() => (activities.value.emailBox.show = true))
}

function statusLabel(status) {
  // Sengaja tidak diterjemahkan: lihat catatan di computed `statuses`.
  return status
}

const showLostReasonModal = ref(false)

function setLostReason() {
  if (
    getInquiryStatus(document.doc.status).type !== 'Lost' ||
    // Dropdown Lost Reason sudah dihapus: yang menentukan modal perlu dibuka
    // atau tidak cuma catatannya.
    (document.doc.lost_notes || '').trim()
  ) {
    document.save.submit(null, {
      onSuccess: () => sections.reload(),
    })
    return
  }

  showLostReasonModal.value = true
}

function beforeStatusChange(data) {
  if (
    Object.hasOwn(data ?? {}, 'status') &&
    getInquiryStatus(data.status).type == 'Lost'
  ) {
    setLostReason()
  } else {
    document.save.submit(null, {
      onSuccess: () => reloadResources(data),
    })
  }
}

function reloadResources(data) {
  if (Object.hasOwn(data ?? {}, 'inquiry_owner')) {
    assignees.reload()
  }
  if (
    Object.hasOwn(data ?? {}, 'status') &&
    getInquiryStatus(data.status).type != 'Lost'
  ) {
    sections.reload()
  }
}
</script>
