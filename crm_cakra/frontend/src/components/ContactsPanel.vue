<template>
  <div class="contacts-area">
    <div
      v-if="contacts?.loading && contacts?.data?.length == 0"
      class="flex min-h-20 flex-1 items-center justify-center gap-3 text-base text-ink-gray-4"
    >
      <LoadingIndicator class="h-4 w-4" />
      <span>{{ __('Loading...') }}</span>
    </div>
    <div
      v-for="(contact, i) in contacts.data"
      v-else-if="contacts?.data?.length"
      :key="contact.name"
    >
      <div class="px-2 pb-2.5" :class="[i == 0 ? 'pt-5' : 'pt-2.5']">
        <Section :opened="contact.opened">
          <template #header="{ opened, toggle }">
            <div
              class="flex cursor-pointer items-center justify-between gap-2 pr-1 text-base leading-5 text-ink-gray-7"
            >
              <div
                class="flex h-7 items-center gap-2 truncate"
                @click="toggle()"
              >
                <Avatar
                  :label="contact.full_name"
                  :image="contact.image"
                  size="md"
                />
                <div class="truncate">
                  {{ contact.full_name }}
                </div>
                <Badge
                  v-if="contact.is_primary"
                  class="ml-2"
                  variant="outline"
                  :label="__('Primary')"
                  theme="green"
                />
                <Badge
                  v-if="contact.role"
                  class="ml-2"
                  variant="outline"
                  :label="__(contact.role)"
                  theme="blue"
                />
              </div>
              <div class="flex items-center">
                <Dropdown :options="contactOptions(contact)">
                  <Button
                    icon="more-horizontal"
                    class="text-ink-gray-5"
                    variant="ghost"
                  />
                </Dropdown>
                <Button
                  variant="ghost"
                  :tooltip="__('View Contact')"
                  :icon="ArrowUpRightIcon"
                  @click="
                    router.push({
                      name: 'Contact',
                      params: { contactId: contact.name },
                    })
                  "
                />
                <Button
                  variant="ghost"
                  class="transition-all duration-300 ease-in-out"
                  :class="{ 'rotate-90': opened }"
                  icon="chevron-right"
                  @click="toggle()"
                />
              </div>
            </div>
          </template>
          <div class="flex flex-col gap-1.5 text-base">
            <div
              v-if="contact.email"
              class="flex items-center gap-3 pb-1.5 pl-1 pt-4 text-ink-gray-8"
            >
              <Email2Icon class="h-4 w-4" />
              {{ contact.email }}
            </div>
            <div
              v-if="contact.mobile_no"
              class="flex items-center gap-3 p-1 py-1.5 text-ink-gray-8"
            >
              <PhoneIcon class="h-4 w-4" />
              {{ contact.mobile_no }}
            </div>
            <div
              v-if="!contact.email && !contact.mobile_no"
              class="flex items-center justify-center py-4 text-sm text-ink-gray-4"
            >
              {{ __('No Details Added') }}
            </div>
          </div>
        </Section>
      </div>
      <div
        v-if="i != contacts.data.length - 1"
        class="mx-2 h-px border-t border-outline-gray-modals"
      />
    </div>
    <div
      v-else
      class="flex h-20 items-center justify-center text-base text-ink-gray-5"
    >
      {{ __('No Contacts Added') }}
    </div>
  </div>
</template>

<script setup>
import LoadingIndicator from '@/components/Icons/LoadingIndicator.vue'
import Email2Icon from '@/components/Icons/Email2Icon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import ArrowUpRightIcon from '@/components/Icons/ArrowUpRightIcon.vue'
import SuccessIcon from '@/components/Icons/SuccessIcon.vue'
import Section from '@/components/Section.vue'
import { useContacts } from '@/composables/contacts'
import { Avatar, Badge, Dropdown } from 'frappe-ui'
import { h } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  doctype: { type: String, required: true },
  docname: { type: String, required: true },
})

const router = useRouter()

const {
  contacts,
  CONTACT_ROLES,
  removeContact,
  setPrimaryContact,
  setContactRole,
} = useContacts(props.doctype, props.docname)

function contactOptions(contact) {
  let options = [
    {
      label: __('Remove'),
      icon: 'trash-2',
      onClick: () => removeContact(contact.name),
    },
  ]

  if (!contact.is_primary) {
    options.push({
      label: __('Set as Primary Contact'),
      icon: h(SuccessIcon, { class: 'h-4 w-4' }),
      onClick: () => setPrimaryContact(contact.name),
    })
  }

  // Peran kontak (§4 Alur CRM). Semua opsi dijadikan grup: Dropdown menyimpulkan
  // mode bergrup dari options[0].group dan hanya kalau truthy -- campuran item polos
  // dengan satu grup di belakang akan dirender sebagai item rusak tanpa label.
  return [
    { group: __('Contact'), hideLabel: true, items: options },
    {
      group: __('Role'),
      items: CONTACT_ROLES.map((role) => ({
        label: role ? __(role) : __('No Role'),
        onClick: () => setContactRole(contact.name, role),
      })),
    },
  ]
}
</script>
