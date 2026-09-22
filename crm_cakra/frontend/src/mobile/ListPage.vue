<template>
  <div class="sticky top-0 z-10 bg-surface-white">
    <div class="flex h-12 items-center justify-between gap-2 border-b px-4">
      <div class="flex items-center gap-2 truncate">
        <component :is="cfg.icon" class="size-4 text-ink-gray-7" />
        <span class="truncate text-base font-semibold text-ink-gray-8">
          {{ __(cfg.label) }}
        </span>
        <span v-if="total !== null" class="text-sm text-ink-gray-5">{{ total }}</span>
      </div>
      <Button
        v-if="cfg.newRoute || cfg.modal"
        variant="solid"
        icon="plus"
        :label="__('Create')"
        @click="create"
      />
    </div>
    <div class="border-b px-4 py-2">
      <TextInput
        v-model="search"
        type="text"
        :placeholder="__('Search')"
      >
        <template #prefix>
          <FeatherIcon name="search" class="size-4 text-ink-gray-5" />
        </template>
      </TextInput>
    </div>
  </div>

  <div v-if="rows.length" class="divide-y">
    <button
      v-for="row in rows"
      :key="row.name"
      class="flex w-full items-start justify-between gap-3 px-4 py-3 text-left active:bg-surface-gray-2"
      @click="open(row)"
    >
      <div class="min-w-0 flex-1">
        <div class="truncate text-base font-medium text-ink-gray-8">
          {{ cfg.title(row) }}
        </div>
        <div class="truncate text-sm text-ink-gray-5">
          {{ cfg.subtitle(row) }}
        </div>
      </div>
      <div class="flex shrink-0 flex-col items-end gap-1">
        <div
          v-if="cfg.badge"
          class="flex items-center gap-1.5 text-sm text-ink-gray-7"
        >
          <IndicatorIcon :class="cfg.badge(row, statuses).class" />
          <span class="max-w-28 truncate">{{ cfg.badge(row, statuses).label }}</span>
        </div>
        <span class="text-xs text-ink-gray-4">{{ stamp(row) }}</span>
      </div>
    </button>
  </div>

  <div
    v-else-if="!list.loading"
    class="flex flex-col items-center gap-2 py-20 text-ink-gray-4"
  >
    <component :is="cfg.icon" class="size-8" />
    <span class="text-base">{{ __('No {0} found', [__(cfg.label)]) }}</span>
  </div>

  <div class="p-4">
    <Button
      v-if="rows.length && rows.length < total"
      class="w-full"
      :label="__('Load more')"
      :loading="list.loading"
      @click="loadMore"
    />
    <div v-else-if="list.loading" class="text-center text-sm text-ink-gray-4">
      {{ __('Loading') }}...
    </div>
  </div>

  <!-- Meeting tidak punya halaman detail, jadi baris & tombol Create sama-sama
       membuka modal yang dipakai halaman desktop. -->
  <component
    :is="modalComponent"
    v-if="modalComponent"
    v-model="showModal"
    v-bind="cfg.modal === 'MeetingModal' ? { meetingId: editId } : {}"
    @created="reload"
    @updated="reload"
  />
</template>

<script setup>
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import LeadModal from '@/components/Modals/LeadModal.vue'
import MeetingModal from '@/components/Modals/MeetingModal.vue'
import ContactModal from '@/components/Modals/ContactModal.vue'
import OrganizationModal from '@/components/Modals/OrganizationModal.vue'
import { lists } from '@/mobile/lists'
import { statusesStore } from '@/stores/statuses'
import { formatDate, timeAgo } from '@/utils'
import { Button, TextInput, FeatherIcon, createResource } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const PAGE_LENGTH = 20
const MODALS = { LeadModal, MeetingModal, ContactModal, OrganizationModal }

const route = useRoute()
const router = useRouter()
const statuses = statusesStore()

const cfg = computed(() => lists[route.params.list])
const rows = ref([])
const total = ref(null)
const start = ref(0)
const search = ref('')
const showModal = ref(false)
const editId = ref('')

const modalComponent = computed(() => MODALS[cfg.value.modal])

const list = createResource({
  url: 'crm_cakra.api.doc.get_linked_list',
  makeParams: () => ({
    doctype: cfg.value.doctype,
    filters: cfg.value.filters || {},
    fields: cfg.value.fields,
    search: search.value || undefined,
    order_by: cfg.value.orderBy || 'modified desc',
    start: start.value,
    page_length: PAGE_LENGTH,
  }),
  onSuccess: (data) => {
    // start=0 berarti daftar baru (ganti menu / search), bukan halaman berikutnya
    rows.value = start.value ? [...rows.value, ...data.data] : data.data
    total.value = data.total_count
  },
})

list.fetch()

function reload() {
  start.value = 0
  list.fetch()
}

// watch, bukan @input: listener native menyala sebelum v-model menulis nilainya,
// jadi pencariannya selalu tertinggal satu ketikan.
let timer = null
watch(search, () => {
  clearTimeout(timer)
  timer = setTimeout(reload, 300)
})

function loadMore() {
  start.value = rows.value.length
  list.fetch()
}

function open(row) {
  if (cfg.value.route) return router.push(cfg.value.route(row))
  editId.value = row.name
  showModal.value = true
}

function create() {
  if (cfg.value.newRoute) return router.push({ name: cfg.value.newRoute })
  editId.value = ''
  showModal.value = true
}

function stamp(row) {
  const field = cfg.value.dateField
  return field ? formatDate(row[field], 'D MMM, hh:mm a') : timeAgo(row.modified)
}
</script>
