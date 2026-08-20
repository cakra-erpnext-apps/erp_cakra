<template>
  <LayoutHeader>
    <template #left-header>
      <ViewBreadcrumbs v-model="viewControls" routeName="Locations" />
    </template>
    <template #right-header>
      <Button variant="solid" :label="__('Create')" iconLeft="plus" @click="openCreate" />
    </template>
  </LayoutHeader>

  <ViewControls ref="viewControls" v-model="locations" v-model:loadMore="loadMore"
    v-model:resizeColumn="triggerResize" v-model:updatedPageCount="updatedPageCount"
    doctype="Fleet Location" :options="{ allowedViews: ['list', 'group_by'] }" />

  <ProductsListView v-if="locations.data && rows.length" v-model="locations.data.page_length_count"
    v-model:list="locations" :rows="rows" :columns="columns" doctype="Fleet Location" :options="{
      showTooltip: false,
      resizeColumn: true,
      rowCount: locations.data.row_count,
      totalCount: locations.data.total_count,
    }" @loadMore="() => loadMore++" @columnWidthUpdated="() => triggerResize++"
    @updatePageCount="(count) => (updatedPageCount = count)" @applyFilter="(data) => viewControls.applyFilter(data)"
    @applyLikeFilter="(data) => viewControls.applyLikeFilter(data)" @likeDoc="(data) => viewControls.likeDoc(data)"
    @selectionsChanged="(s) => viewControls.updateSelections(s)" @rowClick="openEdit" />

  <EmptyState v-else-if="locations.data && !rows.length" name="Locations" :icon="LocationIcon" />
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
import LucideMapPin from '~icons/lucide/map-pin'

const { getFormattedCurrency, getFormattedFloat } = getMeta('Fleet Location')
const { showModal } = useDoctypeModal()

const LocationIcon = LucideMapPin

const locations = ref({})
const loadMore = ref(false)
const triggerResize = ref(false)
const updatedPageCount = ref(20)
const viewControls = ref(null)

// Master milik modul Fleet di app erp, dipakai bareng ERP. Sales User cuma
// punya read + create, ubah data butuh Sales Manager atau System Manager.
const callbacks = {
  afterInsert: () => locations.value?.reload?.(),
  afterUpdate: () => locations.value?.reload?.(),
}

function openCreate() {
  showModal({ doctype: 'Fleet Location', title: 'Location', callbacks })
}

function openEdit(name) {
  showModal({ name, doctype: 'Fleet Location', title: 'Location', callbacks })
}

const rows = computed(() => {
  if (!locations.value?.data?.data) return []
  return parseRows(locations.value.data.data, locations.value.data.columns)
})

const columns = computed(() => {
  let _columns = locations.value?.data?.columns || []
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
    locations.value.data.rows.forEach((row) => {
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
