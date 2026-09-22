<template>
  <LayoutHeader v-if="organization.doc">
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs">
        <template #prefix="{ item }">
          <Icon v-if="item.icon" :icon="item.icon" class="mr-2 h-4" />
        </template>
      </Breadcrumbs>
    </template>
    <template #right-header>
      <CustomActions
        v-if="organization._actions?.length"
        :actions="organization._actions"
      />
      <Button
        v-if="currentTab === 'Contacts'"
        variant="solid"
        icon-left="plus"
        :label="__('Create')"
        @click="showContactModal = true"
      />
    </template>
  </LayoutHeader>
  <div v-if="organization.doc" ref="parentRef" class="flex h-full">
    <Resizer
      v-if="organization.doc"
      :parent="$refs.parentRef"
      class="flex h-full flex-col overflow-hidden border-r"
    >
      <div class="border-b">
        <FileUploader
          :validateFile="validateIsImageFile"
          @success="changeOrganizationImage"
        >
          <template #default="{ openFileSelector, error }">
            <div class="flex flex-col items-start justify-start gap-4 p-5">
              <div class="flex gap-4 items-center">
                <div class="group relative h-15.5 w-15.5">
                  <Avatar
                    size="3xl"
                    class="h-15.5 w-15.5"
                    :label="organization.doc.organization_name"
                    :image="organization.doc.organization_logo"
                  />
                  <component
                    :is="organization.doc.organization_logo ? Dropdown : 'div'"
                    v-bind="
                      organization.doc.organization_logo
                        ? {
                            options: [
                              {
                                icon: 'upload',
                                label: organization.doc.organization_logo
                                  ? __('Change Image')
                                  : __('Upload Image'),
                                onClick: openFileSelector,
                              },
                              {
                                icon: 'trash-2',
                                label: __('Remove Image'),
                                onClick: () => changeOrganizationImage(''),
                              },
                            ],
                          }
                        : { onClick: openFileSelector }
                    "
                    class="!absolute bottom-0 left-0 right-0"
                  >
                    <div
                      class="z-1 absolute bottom-0 left-0 right-0 flex h-14 cursor-pointer items-center justify-center rounded-b-full bg-black bg-opacity-40 pt-5 opacity-0 duration-300 ease-in-out group-hover:opacity-100"
                      style="
                        -webkit-clip-path: inset(22px 0 0 0);
                        clip-path: inset(22px 0 0 0);
                      "
                    >
                      <CameraIcon class="h-6 w-6 cursor-pointer text-white" />
                    </div>
                  </component>
                </div>
                <div class="flex flex-col gap-2 truncate">
                  <div class="truncate text-2xl font-medium text-ink-gray-9">
                    <span>{{ organization.doc.name }}</span>
                  </div>
                  <div
                    v-if="organization.doc.website"
                    class="flex items-center gap-1.5 text-base text-ink-gray-8"
                  >
                    <WebsiteIcon class="size-4" />
                    <span>{{ website(organization.doc.website) }}</span>
                  </div>
                  <ErrorMessage :message="__(error)" />
                </div>
              </div>
              <div class="flex gap-1.5">
                <Button
                  v-if="canDelete"
                  :label="__('Delete')"
                  theme="red"
                  size="sm"
                  iconLeft="trash-2"
                  @click="deleteOrganization()"
                />
                <Button
                  :tooltip="__('Open Website')"
                  icon="link"
                  @click="openWebsite"
                />
              </div>
            </div>
          </template>
        </FileUploader>
      </div>
      <div
        v-if="sections.data"
        class="flex flex-1 flex-col justify-between overflow-hidden"
      >
        <SidePanelLayout
          :sections="sections.data"
          doctype="CRM Organization"
          :docname="organization.doc.name"
          @reload="sections.reload"
          @beforeFieldChange="beforeFieldChange"
        />
      </div>
    </Resizer>
    <Tabs
      v-model="tabIndex"
      as="div"
      :tabs="tabs"
      class="flex flex-1 overflow-hidden flex-col [&_[role='tablist']]:gap-7.5 [&_[role='tablist']]:px-5 [&_[role='tablist']::-webkit-scrollbar]:h-0 [&_[role='tablist']]:min-h-[45px] [&_[role='tabpanel']:not([hidden])]:flex [&_[role='tabpanel']:not([hidden])]:grow"
    >
      <template #tab-item="{ tab, selected }">
        <button
          class="group flex items-center gap-2 border-b border-transparent py-2.5 text-base text-ink-gray-5 duration-300 ease-in-out hover:text-ink-gray-9"
          :class="{ 'text-ink-gray-9': selected }"
        >
          <component :is="tab.icon" v-if="tab.icon" class="h-5" />
          {{ __(tab.label) }}
          <Badge
            v-if="tab.count !== undefined"
            class="group-hover:bg-surface-gray-7"
            :class="[selected ? 'bg-surface-gray-7' : 'bg-gray-600']"
            variant="solid"
            theme="gray"
            size="sm"
          >
            {{ tab.count }}
          </Badge>
        </button>
      </template>
      <template #tab-panel="{ tab }">
        <div
          v-if="tab.label === currentTab"
          class="flex flex-1 flex-col overflow-hidden"
        >
          <div class="px-5 pt-4">
            <TextInput
              v-model="search"
              :placeholder="__('Search')"
              class="w-44"
              :debounce="300"
            >
              <template #prefix>
                <FeatherIcon name="search" class="h-4 w-4 text-ink-gray-5" />
              </template>
            </TextInput>
          </div>
          <component
            :is="listViews[tab.label]"
            v-if="rows.length"
            class="mt-4"
            :rows="rows"
            :columns="columns"
            :options="{ selectable: false, showTooltip: false }"
          />
          <EmptyState v-else :icon="tab.icon" :name="__(tab.label)" />
          <div
            v-if="totalCount > PAGE_LENGTH"
            class="flex items-center justify-end gap-2 border-t px-5 py-2 text-base text-ink-gray-5"
          >
            <span>{{ pageInfo }}</span>
            <Button
              icon="chevron-left"
              :disabled="page === 0"
              @click="page--"
            />
            <Button
              icon="chevron-right"
              :disabled="(page + 1) * PAGE_LENGTH >= totalCount"
              @click="page++"
            />
          </div>
        </div>
      </template>
    </Tabs>
  </div>
  <ErrorPage
    v-else-if="errorTitle"
    :errorTitle="errorTitle"
    :errorMessage="errorMessage"
  />
  <ContactModal
    v-if="showContactModal"
    v-model="showContactModal"
    :contact="{ company_name: props.organizationId }"
    :options="{ redirect: false, afterInsert: reloadContacts }"
  />
  <DeleteLinkedDocModal
    v-if="showDeleteLinkedDocModal"
    v-model="showDeleteLinkedDocModal"
    :doctype="'CRM Organization'"
    :docname="props.organizationId"
    name="Organizations"
  />
</template>

<script setup>
import ErrorPage from '@/components/ErrorPage.vue'
import Resizer from '@/components/Resizer.vue'
import SidePanelLayout from '@/components/SidePanelLayout.vue'
import Icon from '@/components/Icon.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import InquiriesListView from '@/components/ListViews/InquiriesListView.vue'
import QuotationsListView from '@/components/ListViews/QuotationsListView.vue'
import ContactsListView from '@/components/ListViews/ContactsListView.vue'
import ContactModal from '@/components/Modals/ContactModal.vue'
import WebsiteIcon from '@/components/Icons/WebsiteIcon.vue'
import CameraIcon from '@/components/Icons/CameraIcon.vue'
import InquiriesIcon from '@/components/Icons/InquiriesIcon.vue'
import ContactsIcon from '@/components/Icons/ContactsIcon.vue'
import QuotationIcon from '@/components/Icons/QuotationIcon.vue'
import EmptyState from '@/components/ListViews/EmptyState.vue'
import DeleteLinkedDocModal from '@/components/DeleteLinkedDocModal.vue'
import CustomActions from '@/components/CustomActions.vue'
import { useDocument } from '@/data/document'
import { getSettings } from '@/stores/settings'
import { globalStore } from '@/stores/global'
import { getMeta } from '@/stores/meta'
import { usersStore } from '@/stores/users'
import { statusesStore } from '@/stores/statuses'
import { getView } from '@/utils/view'
import {
  formatDate,
  timeAgo,
  validateIsImageFile,
  setupCustomizations,
  openWebsite as openExternalWebsite,
} from '@/utils'
import {
  Breadcrumbs,
  Avatar,
  FileUploader,
  Dropdown,
  Tabs,
  TextInput,
  FeatherIcon,
  usePageMeta,
  createResource,
  toast,
  call,
} from 'frappe-ui'
import { useDoctypeModal } from '@/composables/doctypeModal'
import { useTelemetry } from 'frappe-ui/frappe'
import { computed, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const props = defineProps({
  organizationId: { type: String, required: true },
})

const { brand } = getSettings()
const { $dialog, $socket } = globalStore()
const { getUser } = usersStore()
const { getInquiryStatus } = statusesStore()
const { doctypeMeta } = getMeta('CRM Organization')
const { capture } = useTelemetry()

const route = useRoute()
const router = useRouter()

const errorTitle = ref('')
const errorMessage = ref('')

const showDeleteLinkedDocModal = ref(false)
const showContactModal = ref(false)

const {
  document: organization,
  permissions,
  scripts,
  triggerOnRender,
} = useDocument('CRM Organization', props.organizationId)

const canDelete = computed(() => permissions.data?.permissions?.delete || false)

onMounted(async () => {
  if (organization.doc) await triggerOnRender()
})

const breadcrumbs = computed(() => {
  let items = [{ label: __('Organizations'), route: { name: 'Organizations' } }]

  if (route.query.view || route.query.viewType) {
    let view = getView(
      route.query.view,
      route.query.viewType,
      'CRM Organization',
    )
    if (view) {
      items.push({
        label: __(view.label),
        icon: view.icon,
        route: {
          name: 'Organizations',
          params: { viewType: route.query.viewType },
          query: { view: route.query.view },
        },
      })
    }
  }

  items.push({
    label: title.value,
    route: {
      name: 'Organization',
      params: { organizationId: props.organizationId },
    },
  })
  return items
})

const title = computed(() => {
  let t = doctypeMeta.value?.title_field || 'name'
  return organization.doc?.[t] || props.organizationId
})

usePageMeta(() => {
  return {
    title: title.value,
    icon: brand.favicon,
  }
})

async function deleteOrganization() {
  showDeleteLinkedDocModal.value = true
}

function changeOrganizationImage(file) {
  organization.setValue.submit({
    organization_logo: file?.file_url || null,
  })
}

function beforeFieldChange(data) {
  if (Object.hasOwn(data ?? {}, 'organization_name')) {
    call('frappe.client.rename_doc', {
      doctype: 'CRM Organization',
      old_name: props.organizationId,
      new_name: data.organization_name,
    }).then(() => {
      router.push({
        name: 'Organization',
        params: { organizationId: data.organization_name },
      })
    })
  } else {
    organization.save.submit()
  }
}

function website(url) {
  return url && url.replace(/^(?:https?:\/\/)?(?:www\.)?/i, '')
}

function openWebsite() {
  if (!organization.doc.website) {
    toast.error(__('No Website Found'))
    return
  }

  openExternalWebsite(organization.doc.website)
}

const sections = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections',
  cache: ['sidePanelSections', 'CRM Organization'],
  params: { doctype: 'CRM Organization' },
  auto: true,
  transform: (data) => getParsedSections(data),
})

function getParsedSections(_sections) {
  return _sections.map((section) => {
    section.columns = section.columns.map((column) => {
      column.fields = column.fields.map((field) => {
        if (field.fieldname === 'address') {
          return {
            ...field,
            create: (value, close) => {
              showAddressModal()
              close()
            },
            edit: (address) => showAddressModal(address),
          }
        } else {
          return field
        }
      })
      return column
    })
    return section
  })
}

const PAGE_LENGTH = 10

const tabIndex = ref(0)
const search = ref('')
const page = ref(0)

// Total sebenarnya per tab — data yang termuat cuma sehalaman, jadi jangan pakai data.length
const docCount = (doctype, filters) =>
  createResource({
    url: 'frappe.client.get_count',
    params: { doctype, filters },
    auto: true,
  })

const counts = {
  Inquiries: docCount('CRM Inquiry', { organization: props.organizationId }),
  Quotations: docCount('CRM Quotation', { account: props.organizationId }),
  Contacts: docCount('Contact', { company_name: props.organizationId }),
}

const tabs = [
  {
    label: 'Inquiries',
    icon: InquiriesIcon,
    count: computed(() => counts.Inquiries.data),
  },
  {
    label: 'Quotations',
    icon: QuotationIcon,
    count: computed(() => counts.Quotations.data),
  },
  {
    label: 'Contacts',
    icon: ContactsIcon,
    count: computed(() => counts.Contacts.data),
  },
]

const currentTab = computed(() => tabs[tabIndex.value]?.label)

// Satu halaman (PAGE_LENGTH baris) + total-nya, ikut kotak search
const tabList = (doctype, filters, fields) =>
  createResource({
    url: 'crm_cakra.api.doc.get_linked_list',
    makeParams: () => ({
      doctype,
      filters,
      fields,
      search: search.value || undefined,
      start: page.value * PAGE_LENGTH,
      page_length: PAGE_LENGTH,
    }),
  })

const lists = {
  Inquiries: tabList(
    'CRM Inquiry',
    { organization: props.organizationId },
    [
      'name',
      'subject',
      'inquiry_date',
      'net_total',
      'currency',
      'status',
      '_assign',
      'modified',
    ],
  ),
  Quotations: tabList(
    'CRM Quotation',
    { account: props.organizationId },
    [
      'name',
      'subject',
      'date',
      'net_total',
      'currency',
      'state',
      '_assign',
      'modified',
    ],
  ),
  Contacts: tabList(
    'Contact',
    { company_name: props.organizationId },
    [
      'name',
      'full_name',
      'image',
      'email_id',
      'mobile_no',
      'company_name',
      'modified',
    ],
  ),
}

const listViews = {
  Inquiries: InquiriesListView,
  Quotations: QuotationsListView,
  Contacts: ContactsListView,
}

const rowObject = {
  Inquiries: (r) => getInquiryRowObject(r),
  Quotations: (r) => getQuotationRowObject(r),
  Contacts: (r) => getContactRowObject(r),
}

// Ganti tab = mulai dari halaman 1 dengan search kosong (jalan sebelum watcher fetch di bawah)
watch(currentTab, () => {
  search.value = ''
  page.value = 0
})

// Search mengubah jumlah baris, jadi balik ke halaman 1
watch(search, () => (page.value = 0))

watch([currentTab, search, page], () => lists[currentTab.value]?.fetch(), {
  immediate: true,
})

const rows = computed(() => {
  const data = lists[currentTab.value]?.data?.data || []
  return data.map(rowObject[currentTab.value])
})

const totalCount = computed(
  () => lists[currentTab.value]?.data?.total_count || 0,
)

const pageInfo = computed(() => {
  const from = page.value * PAGE_LENGTH + 1
  const to = Math.min(from + PAGE_LENGTH - 1, totalCount.value)
  return `${from} - ${to} ${__('of')} ${totalCount.value}`
})

function reloadContacts() {
  lists.Contacts.fetch()
  counts.Contacts.reload()
}

const { getFormattedCurrency } = getMeta('CRM Inquiry')
const { getFormattedCurrency: getQuotationCurrency } = getMeta('CRM Quotation')

const columns = computed(
  () =>
    ({
      Inquiries: inquiryColumns,
      Quotations: quotationColumns,
      Contacts: contactColumns,
    })[currentTab.value] || [],
)

// _assign disimpan sebagai JSON string berisi email
function getAssignees(_assign) {
  return JSON.parse(_assign || '[]').map((user) => ({
    name: user,
    image: getUser(user).user_image,
    label: getUser(user).full_name,
  }))
}

function getInquiryRowObject(inquiry) {
  return {
    name: inquiry.name,
    subject: inquiry.subject,
    inquiry_date: inquiry.inquiry_date ? formatDate(inquiry.inquiry_date) : '',
    net_total: getFormattedCurrency('net_total', inquiry),
    status: {
      label: inquiry.status,
      color: getInquiryStatus(inquiry.status)?.color,
    },
    _assign: getAssignees(inquiry._assign),
    modified: {
      label: formatDate(inquiry.modified),
      timeAgo: __(timeAgo(inquiry.modified)),
    },
  }
}

function getQuotationRowObject(quotation) {
  return {
    name: quotation.name,
    subject: quotation.subject,
    state: quotation.state,
    date: quotation.date ? formatDate(quotation.date) : '',
    net_total: getQuotationCurrency('net_total', quotation),
    _assign: getAssignees(quotation._assign),
    modified: {
      label: formatDate(quotation.modified),
      timeAgo: __(timeAgo(quotation.modified)),
    },
  }
}

function getContactRowObject(contact) {
  return {
    name: contact.name,
    full_name: {
      label: contact.full_name,
      image_label: contact.full_name,
      image: contact.image,
    },
    email: contact.email_id,
    mobile_no: contact.mobile_no,
    company_name: {
      label: contact.company_name,
      logo: organization.doc?.organization_logo,
    },
    modified: {
      label: formatDate(contact.modified),
      timeAgo: __(timeAgo(contact.modified)),
    },
  }
}

const inquiryColumns = [
  {
    label: __('Inquiry No'),
    key: 'name',
    width: '12rem',
  },
  {
    label: __('Subject'),
    key: 'subject',
    width: '14rem',
  },
  {
    label: __('Date'),
    key: 'inquiry_date',
    width: '8rem',
  },
  {
    label: __('Amount'),
    key: 'net_total',
    align: 'right',
    width: '10rem',
  },
  {
    label: __('Status'),
    key: 'status',
    width: '10rem',
  },
  {
    label: __('Assign To'),
    key: '_assign',
    width: '10rem',
  },
  {
    label: __('Last Modified'),
    key: 'modified',
    width: '8rem',
  },
]

const quotationColumns = [
  {
    label: __('Quotation No'),
    key: 'name',
    width: '12rem',
  },
  {
    label: __('Subject'),
    key: 'subject',
    width: '14rem',
  },
  {
    label: __('Date'),
    key: 'date',
    width: '8rem',
  },
  {
    label: __('Amount'),
    key: 'net_total',
    align: 'right',
    width: '10rem',
  },
  {
    label: __('Status'),
    key: 'state',
    width: '9rem',
  },
  {
    label: __('Assign To'),
    key: '_assign',
    width: '10rem',
  },
  {
    label: __('Last Modified'),
    key: 'modified',
    width: '8rem',
  },
]

const contactColumns = [
  {
    label: __('Name'),
    key: 'full_name',
    width: '17rem',
  },
  {
    label: __('Email'),
    key: 'email',
    width: '12rem',
  },
  {
    label: __('Phone'),
    key: 'mobile_no',
    width: '12rem',
  },
  {
    label: __('Organization'),
    key: 'company_name',
    width: '12rem',
  },
  {
    label: __('Last Modified'),
    key: 'modified',
    width: '8rem',
  },
]

const { showModal } = useDoctypeModal()

function showAddressModal(_address) {
  showModal({
    name: _address || null,
    doctype: 'Address',
    callbacks: {
      afterInsert: (d) => {
        capture('address_created')
        organization.doc.address = d.name
        organization.save.submit()
      },
    },
  })
}

// Setup custom actions from Form Scripts
watch(
  () => organization.doc,
  async (_doc) => {
    if (scripts.data?.length) {
      let s = await setupCustomizations(scripts.data, {
        doc: _doc,
        $dialog,
        $socket,
        router,
        toast,
        updateField: organization.setValue.submit,
        createToast: toast.create,
        deleteDoc: deleteOrganization,
        call,
      })
      organization._actions = s.actions || []
    }
  },
  { once: true },
)
</script>
