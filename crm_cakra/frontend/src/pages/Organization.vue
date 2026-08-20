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
        <component
          :is="listViews[tab.label]"
          v-if="tab.label === currentTab && rows.length"
          v-model="pageLength"
          class="mt-4"
          :rows="rows"
          :columns="columns"
          :options="{
            selectable: false,
            showTooltip: false,
            rowCount: rows.length,
            totalCount: totalCount,
          }"
          @loadMore="loadMore"
        />
        <div
          v-if="tab.label === 'Summary'"
          class="flex-1 overflow-y-auto pt-4"
        >
          <SummaryArea
            doctype="CRM Organization"
            :docname="organization.doc.name"
          />
        </div>
        <EmptyState
          v-if="tab.label === currentTab && listViews[tab.label] && !rows.length"
          :icon="tab.icon"
          :name="__(tab.label)"
        />
      </template>
    </Tabs>
  </div>
  <ErrorPage
    v-else-if="errorTitle"
    :errorTitle="errorTitle"
    :errorMessage="errorMessage"
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
import WebsiteIcon from '@/components/Icons/WebsiteIcon.vue'
import CameraIcon from '@/components/Icons/CameraIcon.vue'
import InquiriesIcon from '@/components/Icons/InquiriesIcon.vue'
import ContactsIcon from '@/components/Icons/ContactsIcon.vue'
import QuotationIcon from '@/components/Icons/QuotationIcon.vue'
import DashboardIcon from '@/components/Icons/DashboardIcon.vue'
import SummaryArea from '@/components/Activities/SummaryArea.vue'
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
  createListResource,
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

const PAGE_LENGTH = 30

const tabIndex = ref(0)
const pageLength = ref(PAGE_LENGTH)
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
  {
    label: 'Summary',
    icon: DashboardIcon,
  },
]

const currentTab = computed(() => tabs[tabIndex.value]?.label)

const inquiries = createListResource({
  type: 'list',
  doctype: 'CRM Inquiry',
  cache: ['inquiries', props.organizationId],
  fields: [
    'name',
    'organization',
    'currency',
    'annual_revenue',
    'status',
    'email',
    'mobile_no',
    'inquiry_owner',
    'modified',
  ],
  filters: {
    organization: props.organizationId,
  },
  orderBy: 'modified desc',
  pageLength: PAGE_LENGTH,
  auto: true,
})

const quotations = createListResource({
  type: 'list',
  doctype: 'CRM Quotation',
  cache: ['quotations', props.organizationId],
  fields: [
    'name',
    'subject',
    'state',
    'date',
    'net_total',
    'currency',
    'modified',
  ],
  filters: {
    account: props.organizationId,
  },
  orderBy: 'modified desc',
  pageLength: PAGE_LENGTH,
  auto: true,
})

const contacts = createListResource({
  type: 'list',
  doctype: 'Contact',
  cache: ['contacts', props.organizationId],
  fields: [
    'name',
    'full_name',
    'image',
    'email_id',
    'mobile_no',
    'company_name',
    'modified',
  ],
  filters: {
    company_name: props.organizationId,
  },
  orderBy: 'modified desc',
  pageLength: PAGE_LENGTH,
  auto: true,
})

const listViews = {
  Inquiries: InquiriesListView,
  Quotations: QuotationsListView,
  Contacts: ContactsListView,
}

const listByTab = {
  Inquiries: [() => inquiries, (r) => getInquiryRowObject(r)],
  Quotations: [() => quotations, (r) => getQuotationRowObject(r)],
  Contacts: [() => contacts, (r) => getContactRowObject(r)],
}

const currentList = computed(() => listByTab[currentTab.value]?.[0]())

const rows = computed(() => {
  const entry = listByTab[currentTab.value]
  const list = entry?.[0]()
  if (!list?.data) return []
  return list.data.map(entry[1])
})

// Paging ala list view: 30 baris pertama, sisanya lewat tombol Load More
const totalCount = computed(() => counts[currentTab.value]?.data || 0)

function loadMore() {
  currentList.value?.next()
}

watch(pageLength, (value) => {
  const list = currentList.value
  if (!list) return
  list.pageLength = value
  list.start = 0
  list.reload()
})

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

function getInquiryRowObject(inquiry) {
  return {
    name: inquiry.name,
    organization: {
      label: inquiry.organization,
      logo: organization.doc?.organization_logo,
    },
    annual_revenue: getFormattedCurrency('annual_revenue', inquiry),
    status: {
      label: inquiry.status,
      color: getInquiryStatus(inquiry.status)?.color,
    },
    email: inquiry.email,
    mobile_no: inquiry.mobile_no,
    inquiry_owner: {
      label: inquiry.inquiry_owner && getUser(inquiry.inquiry_owner).full_name,
      ...(inquiry.inquiry_owner && getUser(inquiry.inquiry_owner)),
    },
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
    label: __('Organization'),
    key: 'organization',
    width: '11rem',
  },
  {
    label: __('Amount'),
    key: 'annual_revenue',
    align: 'right',
    width: '9rem',
  },
  {
    label: __('Status'),
    key: 'status',
    width: '10rem',
  },
  {
    label: __('Email'),
    key: 'email',
    width: '12rem',
  },
  {
    label: __('Mobile No.'),
    key: 'mobile_no',
    width: '11rem',
  },
  {
    label: __('Inquiry Owner'),
    key: 'inquiry_owner',
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
    label: __('Quotation'),
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
