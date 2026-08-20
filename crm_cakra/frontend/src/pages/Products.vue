<template>
  <LayoutHeader>
    <template #left-header>
      <ViewBreadcrumbs v-model="viewControls" routeName="Products" />
    </template>
    <template #right-header>
      <Button variant="solid" :label="__('Create')" iconLeft="plus" @click="openCreate" />
    </template>
  </LayoutHeader>

  <ViewControls ref="viewControls" v-model="products" v-model:loadMore="loadMore" v-model:resizeColumn="triggerResize"
    v-model:updatedPageCount="updatedPageCount" doctype="CRM Product" :options="{
      allowedViews: ['list', 'group_by'],
    }" />

  <ProductsListView v-if="products.data && rows.length" v-model="products.data.page_length_count"
    v-model:list="products" :rows="rows" :columns="columns" :options="{
      showTooltip: false,
      resizeColumn: true,
      rowCount: products.data.row_count,
      totalCount: products.data.total_count,
    }" @loadMore="() => loadMore++" @columnWidthUpdated="() => triggerResize++"
    @updatePageCount="(count) => (updatedPageCount = count)" @applyFilter="(data) => viewControls.applyFilter(data)"
    @applyLikeFilter="(data) => viewControls.applyLikeFilter(data)" @likeDoc="(data) => viewControls.likeDoc(data)"
    @selectionsChanged="(s) => viewControls.updateSelections(s)" @rowClick="openEdit" />

  <EmptyState v-else-if="products.data && !rows.length" name="Products" :icon="ProductIcon" />
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
import LucidePackage from '~icons/lucide/package'

const { getFormattedCurrency, getFormattedFloat } = getMeta('CRM Product')
const { showModal } = useDoctypeModal()

const ProductIcon = LucidePackage

const products = ref({})
const loadMore = ref(false)
const triggerResize = ref(false)
const updatedPageCount = ref(20)
const viewControls = ref(null)

// Create & edit lewat modal Quick Entry generik (layout "CRM Product-Quick Entry"),
// modal yang sama dipakai tombol + di grid produk quotation. Tidak perlu halaman detail.
const callbacks = {
  afterInsert: () => products.value?.reload?.(),
  afterUpdate: () => products.value?.reload?.(),
}

function openCreate() {
  showModal({ doctype: 'CRM Product', title: 'Product', callbacks })
}

function openEdit(name) {
  showModal({ name, doctype: 'CRM Product', title: 'Product', callbacks })
}

const rows = computed(() => {
  if (!products.value?.data?.data) return []
  return parseRows(products.value.data.data, products.value.data.columns)
})

const columns = computed(() => {
  let _columns = products.value?.data?.columns || []
  if (_columns.length) {
    _columns = _columns.map((col, index) => {
      if (index === _columns.length - 1) return { ...col, align: 'right' }
      return col
    })
  }
  return _columns
})

function parseRows(rowsData, columns = []) {
  return rowsData.map((q) => {
    let _rows = {}
    products.value.data.rows.forEach((row) => {
      _rows[row] = q[row]
      let fieldType = columns?.find((c) => (c.key || c.value) == row)?.type

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
