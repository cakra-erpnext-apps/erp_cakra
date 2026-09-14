<template>
  <div class="pr-2">
    <Link
      value=""
      doctype="Contact"
      :onCreate="
        (value, close) => {
          _contact = { first_name: value, company_name: organization }
          showContactModal = true
          close()
        }
      "
      @change="(e) => addContact(e)"
    >
      <template #target="{ togglePopover }">
        <Button
          class="h-7 px-3"
          variant="ghost"
          icon="plus"
          @click="togglePopover()"
        />
      </template>
    </Link>
  </div>
  <ContactModal
    v-if="showContactModal"
    v-model="showContactModal"
    :contact="_contact"
    :options="{
      redirect: false,
      afterInsert: (doc) => addContact(doc.name),
    }"
  />
</template>

<script setup>
import Link from '@/components/Controls/Link.vue'
import ContactModal from '@/components/Modals/ContactModal.vue'
import { useContacts } from '@/composables/contacts'
import { ref } from 'vue'

const props = defineProps({
  doctype: { type: String, required: true },
  docname: { type: String, required: true },
  // Dipakai untuk mengisi nama perusahaan saat kontak baru dibuat dari sini.
  organization: { type: String, default: '' },
})

const { addContact } = useContacts(props.doctype, props.docname)

const showContactModal = ref(false)
const _contact = ref({})
</script>
