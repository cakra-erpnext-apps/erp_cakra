<template>
  <LayoutHeader>
    <template #left-header>
      <ViewBreadcrumbs v-model="viewControls" routeName="CostTypes" />
    </template>
    <template #right-header>
      <Button variant="solid" :label="__('Create')" iconLeft="plus" @click="openCreate" />
    </template>
  </LayoutHeader>

  <ViewControls ref="viewControls" v-model="types" v-model:loadMore="loadMore"
    v-model:resizeColumn="triggerResize" v-model:updatedPageCount="updatedPageCount"
    doctype="CRM Cost Type" :options="{ allowedViews: ['list', 'group_by'] }" />

  <ProductsListView v-if="types.data && rows.length" v-model="types.data.page_length_count"
    v-model:list="types" :rows="rows" :columns="columns" doctype="CRM Cost Type" :options="{
      showTooltip: false,
      resizeColumn: true,
      rowCount: types.data.row_count,
      totalCount: types.data.total_count,
    }" @loadMore="() => loadMore++" @columnWidthUpdated="() => triggerResize++"
    @updatePageCount="(count) => (updatedPageCount = count)" @applyFilter="(data) => viewControls.applyFilter(data)"
    @applyLikeFilter="(data) => viewControls.applyLikeFilter(data)" @likeDoc="(data) => viewControls.likeDoc(data)"
    @selectionsChanged="(s) => viewControls.updateSelections(s)" @rowClick="openEdit" />

  <EmptyState v-else-if="types.data && !rows.length" name="Cost Types" :icon="TypeIcon" />
</template>

<script setup>
import ViewBreadcrumbs from '@/components/ViewBreadcrumbs.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import ProductsListView from '@/components/ListViews/ProductsListView.vue'
import EmptyState from '@/components/ListViews/EmptyState.vue'
import ViewControls from '@/components/ViewControls.vue'
import { useDoctypeModal } from '@/composables/doctypeModal'
import { getMeta } from '@/stores/meta'
import { formatDate, timeAgo } from '@/utils'
import { Button } from 'frappe-ui'
import { ref, computed } from 'vue'
import LucideTags from '~icons/lucide/tags'

const { getFormattedCurrency, getFormattedFloat } = getMeta('CRM Cost Type')
const { showModal } = useDoctypeModal()

const TypeIcon = LucideTags

const types = ref({})
const loadMore = ref(false)
const triggerResize = ref(false)
const updatedPageCount = ref(20)
const viewControls = ref(null)

// Master kecil tanpa tabel anak, jadi cukup modal Quick Entry -- tidak perlu
// halaman penuh seperti Cost Component.
const callbacks = {
  afterInsert: () => types.value?.reload?.(),
  afterUpdate: () => types.value?.reload?.(),
}

function openCreate() {
  showModal({ doctype: 'CRM Cost Type', title: 'Cost Type', callbacks })
}

function openEdit(name) {
  showModal({ name, doctype: 'CRM Cost Type', title: 'Cost Type', callbacks })
}

const rows = computed(() => {
  if (!types.value?.data?.data) return []
  return parseRows(types.value.data.data, types.value.data.columns)
})

const columns = computed(() => {
  let _columns = types.value?.data?.columns || []
  if (_columns.length) {
    _columns = _columns.map((col, index) => {
      if (index === _columns.length - 1) return { ...col, align: 'right' }
      return col
    })
  }
  return _columns
})

function parseRows(rowsData, cols = []) {
  return rowsData.map((q) => {
    let _rows = {}
    types.value.data.rows.forEach((row) => {
      _rows[row] = q[row]
      let fieldType = cols?.find((c) => (c.key || c.value) == row)?.type

      if (
        fieldType &&
        ['Date', 'Datetime'].includes(fieldType) &&
        !['modified', 'creation'].includes(row)
      ) {
        _rows[row] = formatDate(q[row], '', true, fieldType == 'Datetime')
      }
      if (fieldType === 'Currency') _rows[row] = getFormattedCurrency(row, q)
      if (fieldType === 'Float') _rows[row] = getFormattedFloat(row, q)

      if (['modified', 'creation'].includes(row)) {
        _rows[row] = { label: formatDate(q[row]), timeAgo: __(timeAgo(q[row])) }
      }
    })
    return _rows
  })
}
</script>
