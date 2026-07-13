<template>
  <Dialog v-model="show" :options="{ size: 'xl' }">
    <template #body-header>
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h3 class="text-2xl font-semibold leading-6 text-ink-gray-9">
            {{ __('Convert to Inquiry') }}
          </h3>
        </div>
        <!-- Tombol "Edit mandatory fields layout" dibuang: layout itu tidak lagi
             dirender di modal ini, jadi tombolnya menyunting sesuatu yang tak terlihat. -->
        <div class="flex items-center gap-1">
          <Button icon="x" variant="ghost" @click="show = false" />
        </div>
      </div>
    </template>
    <template #body-content>
      <div class="mb-4 flex items-center gap-2 text-ink-gray-5">
        <OrganizationsIcon class="h-4 w-4" />
        <label class="block text-base">{{ __('Organization') }}</label>
      </div>
      <div class="ml-6 text-ink-gray-9">
        <div class="flex items-center justify-between text-base">
          <div>{{ __('Choose Existing') }}</div>
          <Switch v-model="existingOrganizationChecked" />
        </div>
        <Link
          v-if="existingOrganizationChecked"
          class="form-control mt-2.5"
          size="md"
          :value="existingOrganization"
          doctype="CRM Organization"
          @change="(data) => (existingOrganization = data)"
        />
        <div v-else class="mt-2.5 text-base">
          {{
            __(
              'New organization will be created based on the data in details section',
            )
          }}
        </div>
      </div>

      <div class="mb-4 mt-6 flex items-center gap-2 text-ink-gray-5">
        <ContactsIcon class="h-4 w-4" />
        <label class="block text-base">{{ __('Contact') }}</label>
      </div>
      <div class="ml-6 text-ink-gray-9">
        <div class="flex items-center justify-between text-base">
          <div>{{ __('Choose Existing') }}</div>
          <Switch v-model="existingContactChecked" />
        </div>
        <Link
          v-if="existingContactChecked"
          class="form-control mt-2.5"
          size="md"
          :value="existingContact"
          doctype="Contact"
          @change="(data) => (existingContact = data)"
        />
        <div v-else class="mt-2.5 text-base">
          {{ __("New contact will be created based on the person's details") }}
        </div>
      </div>

      <div class="mb-4 mt-6 flex items-center gap-2 text-ink-gray-5">
        <IndicatorIcon :class="getInquiryStatus(inquiryStatus).color" />
        <label class="block text-base">{{ __('Status') }}</label>
      </div>
      <div class="ml-6">
        <Dropdown :options="statusDropdownOptions">
          <template #default="{ open }">
            <Button
              class="w-full justify-between"
              :label="inquiryStatus"
              :iconRight="open ? 'chevron-up' : 'chevron-down'"
            >
              <template #prefix>
                <IndicatorIcon :class="getInquiryStatus(inquiryStatus).color" />
              </template>
            </Button>
          </template>
        </Dropdown>
      </div>

      <!-- Field wajib CRM Inquiry lainnya sengaja TIDAK dirender di sini.
           Convert hanya membentuk kerangka: Organization, Contact, Status. Detail
           kargo/rute/service digali di tahap Inquiry, bukan saat lead dikualifikasi --
           memaksanya sekarang hanya membuat user mengarang isian agar bisa lanjut. -->
      <ErrorMessage class="mt-4" :message="error" />
    </template>
    <template #actions>
      <div class="flex justify-end">
        <Button :label="__('Convert')" variant="solid" @click="convertToInquiry" />
      </div>
    </template>
  </Dialog>
</template>
<script setup>
import OrganizationsIcon from '@/components/Icons/OrganizationsIcon.vue'
import ContactsIcon from '@/components/Icons/ContactsIcon.vue'
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import Link from '@/components/Controls/Link.vue'
import { useDocument } from '@/data/document'
import { sessionStore } from '@/stores/session'
import { statusesStore } from '@/stores/statuses'
import { useOnboarding, useTelemetry } from 'frappe-ui/frappe'
import { Switch, Dialog, Dropdown, call } from 'frappe-ui'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  lead: { type: Object, required: true },
})

const show = defineModel({ type: Boolean })

const router = useRouter()

const { statusOptions, getInquiryStatus } = statusesStore()
const { user } = sessionStore()
const { updateOnboardingStep } = useOnboarding('frappecrm')

const existingContactChecked = ref(false)
const existingOrganizationChecked = ref(false)

const existingContact = ref('')
const existingOrganization = ref('')
const error = ref('')
const { capture } = useTelemetry()

const { triggerConvertToInquiry } = useDocument('CRM Lead', props.lead.name)
const { document: inquiry } = useDocument('CRM Inquiry')

async function convertToInquiry() {
  error.value = ''

  if (existingContactChecked.value && !existingContact.value) {
    error.value = __('Please select an existing contact')
    return
  }

  if (existingOrganizationChecked.value && !existingOrganization.value) {
    error.value = __('Please select an existing organization')
    return
  }

  if (!existingContactChecked.value && existingContact.value) {
    existingContact.value = ''
  }

  if (!existingOrganizationChecked.value && existingOrganization.value) {
    existingOrganization.value = ''
  }

  // Hanya status yang dikirim dari modal. Field wajib lain sengaja dibiarkan kosong
  // dan diisi user di form Inquiry (server memakai ignore_mandatory saat convert).
  inquiry.doc.status = inquiryStatus.value

  await triggerConvertToInquiry?.(props.lead, inquiry.doc, () => (show.value = false))

  let _inquiry = await call('crm_cakra.fcrm.doctype.crm_lead.crm_lead.convert_to_inquiry', {
    lead: props.lead.name,
    inquiry: inquiry.doc,
    existing_contact: existingContact.value,
    existing_organization: existingOrganization.value,
  }).catch((err) => {
    if (err.exc_type == 'MandatoryError') {
      const errorMessage = err.messages
        .map((msg) => {
          let arr = msg.split(': ')
          return arr[arr.length - 1].trim()
        })
        .join(', ')

      if (errorMessage.toLowerCase().includes('required')) {
        error.value = __(errorMessage)
      } else {
        error.value = __('{0} is required', [errorMessage])
      }
      return
    }
    error.value = __('Error converting to inquiry: {0}', [err.messages?.[0]])
  })
  if (_inquiry) {
    show.value = false
    existingContactChecked.value = false
    existingOrganizationChecked.value = false
    existingContact.value = ''
    existingOrganization.value = ''
    error.value = ''
    updateOnboardingStep('convert_lead_to_inquiry', true, false, () => {
      localStorage.setItem('firstInquiry' + user, _inquiry)
    })
    capture('convert_lead_to_inquiry')
    router.push({ name: 'Inquiry', params: { inquiryId: _inquiry } })
  }
}

// Status inquiry awal. Default "Qualification" — sama dengan yang di-set
// CRM Inquiry.validate_status() bila dibiarkan kosong, jadi UI dan server sepakat.
const inquiryStatus = ref('Qualification')

const statusDropdownOptions = computed(() =>
  statusOptions('inquiry').map((option) => ({
    ...option,
    onClick: () => (inquiryStatus.value = option.value),
  })),
)

</script>
