<template>
  <LayoutHeader>
    <template #left-header>
      <ViewBreadcrumbs v-model="viewControls" routeName="CostComponents" />
    </template>
    <template #right-header>
      <Button variant="solid" :label="__('Create')" iconLeft="plus" @click="openCreate" />
    </template>
  </LayoutHeader>

  <ViewControls ref="viewControls" v-model="components" v-model:loadMore="loadMore"
    v-model:resizeColumn="triggerResize" v-model:updatedPageCount="updatedPageCount"
    doctype="CRM Cost Component" :options="{ allowedViews: ['list', 'group_by'] }" />

  <ProductsListView v-if="components.data && rows.length" v-model="components.data.page_length_count"
    v-model:list="components" :rows="rows" :columns="columns" doctype="CRM Cost Component" :options="{
      showTooltip: false,
      resizeColumn: true,
      rowCount: components.data.row_count,
      totalCount: components.data.total_count,
    }" @loadMore="() => loadMore++" @columnWidthUpdated="() => triggerResize++"
    @updatePageCount="(count) => (updatedPageCount = count)" @applyFilter="(data) => viewControls.applyFilter(data)"
    @applyLikeFilter="(data) => viewControls.applyLikeFilter(data)" @likeDoc="(data) => viewControls.likeDoc(data)"
    @selectionsChanged="(s) => viewControls.updateSelections(s)" @rowClick="openEdit" />

  <EmptyState v-else-if="components.data && !rows.length" name="Cost Components" :icon="CostIcon" />
</template>

<script setup>
import ViewBreadcrumbs from '@/components/ViewBreadcrumbs.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import ProductsListView from '@/components/ListViews/ProductsListView.vue'
import EmptyState from '@/components/ListViews/EmptyState.vue'
import ViewControls from '@/components/ViewControls.vue'
import { getMeta } from '@/stores/meta'
import { formatDate, timeAgo } from '@/utils'
import { Button } from 'frappe-ui'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import LucideReceipt from '~icons/lucide/receipt'

const { getFormattedCurrency, getFormattedFloat } = getMeta('CRM Cost Component')
const router = useRouter()

const CostIcon = LucideReceipt

const components = ref({})
const loadMore = ref(false)
const triggerResize = ref(false)
const updatedPageCount = ref(20)
const viewControls = ref(null)

// Halaman penuh, bukan modal: satu komponen memuat tabel rincian sendiri, jadi
// polanya mengikuti Quotation, bukan Quick Entry.
function openCreate() {
  router.push({ name: 'NewCostComponent' })
}

function openEdit(name) {
  router.push({ name: 'CostComponent', params: { componentId: name } })
}

const rows = computed(() => {
  if (!components.value?.data?.data) return []
  return parseRows(components.value.data.data, components.value.data.columns)
})

const columns = computed(() => {
  let _columns = components.value?.data?.columns || []
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
    components.value.data.rows.forEach((row) => {
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
