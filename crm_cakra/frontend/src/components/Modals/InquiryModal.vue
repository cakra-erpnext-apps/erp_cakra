<template>
  <Dialog v-model="show" :options="{ size: '3xl' }">
    <template #body>
      <div class="bg-surface-modal px-4 pb-6 pt-5 sm:px-6">
        <div class="mb-5 flex items-center justify-between">
          <div>
            <h3 class="text-2xl font-semibold leading-6 text-ink-gray-9">
              {{ __('Create Inquiry') }}
            </h3>
          </div>
          <div class="flex items-center gap-1">
            <Button
              v-if="isManager() && !isMobileView"
              variant="ghost"
              class="w-7"
              :tooltip="__('Edit Fields Layout')"
              :icon="EditIcon"
              @click="openQuickEntryModal"
            />
            <Button
              variant="ghost"
              class="w-7"
              icon="x"
              @click="show = false"
            />
          </div>
        </div>
        <div>
          <div
            v-if="hasOrganizationSections || hasContactSections"
            class="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-3"
          >
            <div
              v-if="hasOrganizationSections"
              class="flex items-center gap-3 text-sm text-ink-gray-5"
            >
              <div>{{ __('Choose Existing Organization') }}</div>
              <Switch v-model="chooseExistingOrganization" />
            </div>
            <div
              v-if="hasContactSections"
              class="flex items-center gap-3 text-sm text-ink-gray-5"
            >
              <div>{{ __('Choose Existing Contact') }}</div>
              <Switch v-model="chooseExistingContact" />
            </div>
          </div>
          <div
            v-if="hasOrganizationSections || hasContactSections"
            class="h-px w-full border-t my-5"
          />
          <FieldLayout
            v-if="tabs.data?.length"
            :tabs="tabs.data"
            :data="inquiry.doc"
            doctype="CRM Inquiry"
          />
          <ErrorMessage v-if="error" class="mt-4" :message="__(error)" />
        </div>
      </div>
      <div class="px-4 pb-7 pt-4 sm:px-6">
        <div class="flex flex-row-reverse gap-2">
          <Button
            variant="solid"
            :label="__('Create')"
            :loading="isInquiryCreating"
            @click="createInquiry"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import EditIcon from '@/components/Icons/EditIcon.vue'
import FieldLayout from '@/components/FieldLayout/FieldLayout.vue'
import { usersStore } from '@/stores/users'
import { statusesStore } from '@/stores/statuses'
import { isMobileView } from '@/composables/settings'
import { showQuickEntryModal, quickEntryProps } from '@/composables/modals'
import { useDocument } from '@/data/document'
import { useTelemetry } from 'frappe-ui/frappe'
import { Switch, createResource } from 'frappe-ui'
import { computed, ref, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  defaults: { type: Object, default: () => ({}) },
})

const { getUser, isManager } = usersStore()
const { getInquiryStatus, statusOptions } = statusesStore()

const show = defineModel({ type: Boolean })
const router = useRouter()
const error = ref(null)

const { document: inquiry, triggerOnBeforeCreate } = useDocument('CRM Inquiry')

const hasOrganizationSections = ref(true)
const hasContactSections = ref(true)

const isInquiryCreating = ref(false)
const chooseExistingContact = ref(false)
const chooseExistingOrganization = ref(false)
const { capture } = useTelemetry()

watch(
  [chooseExistingOrganization, chooseExistingContact],
  ([organization, contact]) => {
    tabs.data.forEach((tab) => {
      tab.sections.forEach((section) => {
        if (section.name === 'organization_section') {
          section.hidden = !organization
        } else if (section.name === 'organization_details_section') {
          section.hidden = organization
        } else if (section.name === 'contact_section') {
          section.hidden = !contact
        } else if (section.name === 'contact_details_section') {
          section.hidden = contact
        }
      })
    })
  },
)

const tabs = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout',
  cache: ['QuickEntry', 'CRM Inquiry'],
  params: { doctype: 'CRM Inquiry', type: 'Quick Entry' },
  auto: true,
  transform: (_tabs) => {
    hasOrganizationSections.value = false
    return _tabs.forEach((tab) => {
      tab.sections.forEach((section) => {
        section.columns.forEach((column) => {
          if (
            ['organization_section', 'organization_details_section'].includes(
              section.name,
            )
          ) {
            hasOrganizationSections.value = true
          } else if (
            ['contact_section', 'contact_details_section'].includes(
              section.name,
            )
          ) {
            hasContactSections.value = true
          }
          column.fields.forEach((field) => {
            if (field.fieldname == 'status') {
              field.fieldtype = 'Select'
              field.options = inquiryStatuses.value
              field.prefix = getInquiryStatus(inquiry.doc.status).color
            }

            if (field.fieldtype === 'Table') {
              inquiry.doc[field.fieldname] = []
            }
          })
        })
      })
    })
  },
})

const inquiryStatuses = computed(() => statusOptions('inquiry'))

async function createInquiry() {
  if (inquiry.doc.website && !inquiry.doc.website.startsWith('http')) {
    inquiry.doc.website = 'https://' + inquiry.doc.website
  }
  if (chooseExistingContact.value) {
    inquiry.doc['first_name'] = null
    inquiry.doc['last_name'] = null
    inquiry.doc['email'] = null
    inquiry.doc['mobile_no'] = null
  } else inquiry.doc['contact'] = null

  await triggerOnBeforeCreate?.()

  createResource({
    url: 'crm_cakra.fcrm.doctype.crm_inquiry.crm_inquiry.create_inquiry',
    params: { doc: inquiry.doc },
    auto: true,
    validate() {
      error.value = null
      if (inquiry.doc.annual_revenue) {
        if (typeof inquiry.doc.annual_revenue === 'string') {
          inquiry.doc.annual_revenue = inquiry.doc.annual_revenue.replace(/,/g, '')
        } else if (isNaN(inquiry.doc.annual_revenue)) {
          error.value = __('Annual Revenue should be a number')
          return error.value
        }
      }
      if (
        inquiry.doc.mobile_no &&
        isNaN(inquiry.doc.mobile_no.replace(/[-+() ]/g, ''))
      ) {
        error.value = __('Mobile No. should be a number')
        return error.value
      }
      if (inquiry.doc.email && !inquiry.doc.email.includes('@')) {
        error.value = __('Invalid email address')
        return error.value
      }
      if (!inquiry.doc.status) {
        error.value = __('Status is required')
        return error.value
      }
      isInquiryCreating.value = true
    },
    onSuccess(name) {
      capture('inquiry_created')
      isInquiryCreating.value = false
      show.value = false
      inquiry.doc = {} // reset cache dokumen "new" biar tidak bawa data lama
      router.push({ name: 'Inquiry', params: { inquiryId: name } })
    },
    onError(err) {
      isInquiryCreating.value = false
      if (!err.messages) {
        error.value = err.message
        return
      }
      error.value = err.messages.join('\n')
    },
  })
}

function openQuickEntryModal() {
  showQuickEntryModal.value = true
  quickEntryProps.value = { doctype: 'CRM Inquiry' }
  nextTick(() => (show.value = false))
}

onMounted(() => {
  inquiry.doc.no_of_employees = '1-10'
  Object.assign(inquiry.doc, props.defaults)

  if (!inquiry.doc.inquiry_owner) {
    inquiry.doc.inquiry_owner = getUser().name
  }
  if (!inquiry.doc.status && inquiryStatuses.value[0].value) {
    inquiry.doc.status = inquiryStatuses.value[0].value
  }
})
</script>
