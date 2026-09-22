<template>
  <LayoutHeader>
    <template #left-header>
      <ViewBreadcrumbs v-model="viewControls" routeName="Tenders" />
    </template>
    <template #right-header>
      <Button
        variant="solid"
        :label="__('Create')"
        iconLeft="plus"
        @click="showModal = true"
      />
    </template>
  </LayoutHeader>

  <ViewControls
    ref="viewControls"
    v-model="tenders"
    v-model:loadMore="loadMore"
    v-model:resizeColumn="triggerResize"
    v-model:updatedPageCount="updatedPageCount"
    doctype="CRM Tender"
    :options="{ allowedViews: ['list'] }"
  />

  <TendersListView
    v-if="tenders.data && rows.length"
    v-model="tenders.data.page_length_count"
    v-model:list="tenders"
    :rows="rows"
    :columns="columns"
    :options="{
      showTooltip: false,
      resizeColumn: true,
      rowCount: tenders.data.row_count,
      totalCount: tenders.data.total_count,
    }"
    @loadMore="() => loadMore++"
    @columnWidthUpdated="() => triggerResize++"
    @updatePageCount="(count) => (updatedPageCount = count)"
    @applyFilter="(data) => viewControls.applyFilter(data)"
    @applyLikeFilter="(data) => viewControls.applyLikeFilter(data)"
    @likeDoc="(data) => viewControls.likeDoc(data)"
    @selectionsChanged="(s) => viewControls.updateSelections(s)"
    @rowClick="openTender"
  />

  <EmptyState v-else-if="tenders.data && !rows.length" name="Tenders" :icon="TenderIcon" />

  <TenderModal v-if="showModal" v-model="showModal" />
</template>

<script setup>
import ViewBreadcrumbs from '@/components/ViewBreadcrumbs.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import TenderIcon from '~icons/lucide/gavel'
import TendersListView from '@/components/ListViews/TendersListView.vue'
import TenderModal from '@/components/Modals/TenderModal.vue'
import EmptyState from '@/components/ListViews/EmptyState.vue'
import ViewControls from '@/components/ViewControls.vue'
import { getMeta } from '@/stores/meta'
import { formatDate, timeAgo } from '@/utils'
import { Button } from 'frappe-ui'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

const { getFormattedCurrency, getFormattedFloat } = getMeta('CRM Tender')

const router = useRouter()
const tenders = ref({})
const loadMore = ref(false)
const triggerResize = ref(false)
const updatedPageCount = ref(20)
const viewControls = ref(null)
const showModal = ref(false)

function openTender(name) {
  router.push({ name: 'Tender', params: { tenderId: name } })
}

const rows = computed(() => {
  if (!tenders.value?.data?.data) return []
  return parseRows(tenders.value.data.data, tenders.value.data.columns)
})

const columns = computed(() => {
  let _columns = tenders.value?.data?.columns || []
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
    tenders.value.data.rows.forEach((row) => {
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
