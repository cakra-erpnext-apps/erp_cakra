<template>
  <LayoutHeader>
    <template #left-header>
      <ViewBreadcrumbs v-model="viewControls" routeName="Procurement" />
    </template>
    <template #right-header>
      <Button
        variant="solid"
        :label="__('Add Inquiry')"
        iconLeft="plus"
        @click="showAdd = true"
      />
    </template>
  </LayoutHeader>

  <ViewControls
    ref="viewControls"
    v-model="requests"
    v-model:loadMore="loadMore"
    v-model:resizeColumn="triggerResize"
    v-model:updatedPageCount="updatedPageCount"
    doctype="CRM Procurement"
    :options="{ allowedViews: ['list'] }"
  />

  <ProcurementListView
    v-if="requests.data && rows.length"
    v-model="requests.data.page_length_count"
    v-model:list="requests"
    :rows="rows"
    :columns="columns"
    :options="{
      showTooltip: false,
      resizeColumn: true,
      rowCount: requests.data.row_count,
      totalCount: requests.data.total_count,
    }"
    @loadMore="() => loadMore++"
    @columnWidthUpdated="() => triggerResize++"
    @updatePageCount="(count) => (updatedPageCount = count)"
    @applyFilter="(data) => viewControls.applyFilter(data)"
    @applyLikeFilter="(data) => viewControls.applyLikeFilter(data)"
    @likeDoc="(data) => viewControls.likeDoc(data)"
    @selectionsChanged="(s) => viewControls.updateSelections(s)"
  />

  <EmptyState
    v-else-if="requests.data && !rows.length"
    name="Procurement"
    :title="__('Belum ada permintaan')"
    :description="__('Tekan Add Inquiry untuk memasukkan inquiry yang butuh harga.')"
    :icon="ProcurementIcon"
  />

  <Dialog v-model="showAdd" :options="{ title: __('Add Inquiry') }">
    <template #body-content>
      <div>
        <label class="mb-1.5 block text-xs text-ink-gray-5">
          {{ __('Inquiry') }}
        </label>
        <Link
          v-model="inquiry"
          doctype="CRM Inquiry"
          :placeholder="__('Pilih inquiry...')"
        />
        <!-- Inquiry yang sudah punya dokumen procurement tidak disaring dari
             daftar: server mengembalikan dokumen yang sudah ada, dan kita
             langsung mendarat di sana -- bukan membuat yang kedua. -->
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end">
        <Button
          variant="solid"
          :label="__('Add')"
          :disabled="!inquiry"
          :loading="adding"
          @click="add"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import ViewBreadcrumbs from '@/components/ViewBreadcrumbs.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import ProcurementListView from '@/components/ListViews/ProcurementListView.vue'
import EmptyState from '@/components/ListViews/EmptyState.vue'
import ViewControls from '@/components/ViewControls.vue'
import Link from '@/components/Controls/Link.vue'
import ProcurementIcon from '~icons/lucide/shopping-cart'
import { getMeta } from '@/stores/meta'
import { formatDate, timeAgo } from '@/utils'
import { Button, Dialog, call, toast, usePageMeta } from 'frappe-ui'
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'

const { getFormattedCurrency, getFormattedFloat } = getMeta('CRM Procurement')

const router = useRouter()
const requests = ref({})
const loadMore = ref(false)
const triggerResize = ref(false)
const updatedPageCount = ref(20)
const viewControls = ref(null)

const rows = computed(() => {
  if (!requests.value?.data?.data) return []
  return parseRows(requests.value.data.data, requests.value.data.columns)
})

const columns = computed(() => {
  let _columns = requests.value?.data?.columns || []
  if (_columns.length) {
    _columns = _columns.map((col, index) => {
      if (index === _columns.length - 1) return { ...col, align: 'right' }
      return col
    })
  }
  return _columns
})

function parseRows(rowsData, columns = []) {
  return rowsData.map((r) => {
    let _rows = {}
    requests.value.data.rows.forEach((row) => {
      _rows[row] = r[row]
      let fieldType = columns?.find((c) => (c.key || c.value) == row)?.type

      if (
        fieldType &&
        ['Date', 'Datetime'].includes(fieldType) &&
        !['modified', 'creation'].includes(row)
      ) {
        _rows[row] = formatDate(r[row], '', true, fieldType == 'Datetime')
      }
      if (fieldType === 'Currency') _rows[row] = getFormattedCurrency(row, r)
      if (fieldType === 'Float') _rows[row] = getFormattedFloat(row, r)

      if (['modified', 'creation'].includes(row)) {
        _rows[row] = { label: formatDate(r[row]), timeAgo: __(timeAgo(r[row])) }
      }
    })
    return _rows
  })
}

// Add Inquiry: satu-satunya cara dokumen procurement lahir. Dokumennya tidak
// dibuat lewat form kosong seperti doctype lain -- selalu menempel pada inquiry.
const showAdd = ref(false)
const inquiry = ref(null)
const adding = ref(false)

watch(showAdd, (open) => {
  if (open) inquiry.value = null
})

async function add() {
  adding.value = true
  try {
    const name = await call('crm_cakra.api.procurement.add_inquiry', {
      inquiry: inquiry.value,
    })
    showAdd.value = false
    router.push({ name: 'ProcurementDoc', params: { procurementId: name } })
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal menambahkan inquiry'))
  } finally {
    adding.value = false
  }
}

usePageMeta(() => ({ title: __('Procurement') }))
</script>
