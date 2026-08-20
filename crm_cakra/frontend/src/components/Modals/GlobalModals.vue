<template>
  <CreateDocumentModal
    v-if="showCreateDocumentModal"
    v-model="showCreateDocumentModal"
    :doctype="createDocumentDoctype"
    :data="createDocumentData"
    @callback="(data) => createDocumentCallback(data)"
  />
  <QuickEntryModal
    v-if="showQuickEntryModal"
    v-model="showQuickEntryModal"
    v-bind="quickEntryProps"
  />
  <ChangePasswordModal
    v-if="showChangePasswordModal"
    v-model="showChangePasswordModal"
  />
  <AboutModal v-model="showAboutModal" />
  <GlobalSearchModal v-model="showGlobalSearchModal" />
  <FleetLocationModal
    v-if="showFleetLocationModal"
    v-model="showFleetLocationModal"
    v-bind="fleetLocationProps"
  />
  <FieldLayoutDialogContainer />
</template>
<script setup>
import FieldLayoutDialogContainer from '@/components/Modals/FieldLayoutDialogContainer.vue'
import FleetLocationModal from '@/components/Modals/FleetLocationModal.vue'
import ChangePasswordModal from '@/components/Modals/ChangePasswordModal.vue'
import CreateDocumentModal from '@/components/Modals/CreateDocumentModal.vue'
import QuickEntryModal from '@/components/Modals/QuickEntryModal.vue'
import AboutModal from '@/components/Modals/AboutModal.vue'
import GlobalSearchModal from '@/components/Modals/GlobalSearchModal.vue'
import {
  showCreateDocumentModal,
  createDocumentDoctype,
  createDocumentData,
  createDocumentCallback,
  showFleetLocationModal,
  fleetLocationProps,
} from '@/composables/document'
import {
  showQuickEntryModal,
  quickEntryProps,
  showAboutModal,
  showChangePasswordModal,
  showGlobalSearchModal,
} from '@/composables/modals'
</script>
