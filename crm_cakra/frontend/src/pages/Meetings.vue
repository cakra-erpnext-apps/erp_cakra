<template>
  <LayoutHeader>
    <template #left-header>
      <ViewBreadcrumbs v-model="viewControls" routeName="Meetings" />
    </template>
    <template #right-header>
      <Button :label="__('Absen')" iconLeft="map-pin" @click="$router.push({ name: 'MeetingAttendance' })" />
      <Button variant="solid" :label="__('Create')" iconLeft="plus" @click="openCreate" />
    </template>
  </LayoutHeader>

  <ViewControls ref="viewControls" v-model="meetings" v-model:loadMore="loadMore" v-model:resizeColumn="triggerResize"
    v-model:updatedPageCount="updatedPageCount" doctype="CRM Meeting" :options="{
      allowedViews: ['list', 'group_by', 'kanban'],
    }" />

  <MeetingsListView v-if="meetings.data && rows.length" v-model="meetings.data.page_length_count"
    v-model:list="meetings" :rows="rows" :columns="columns" :options="{
      showTooltip: false,
      resizeColumn: true,
      rowCount: meetings.data.row_count,
      totalCount: meetings.data.total_count,
    }" @loadMore="() => loadMore++" @columnWidthUpdated="() => triggerResize++"
    @updatePageCount="(count) => (updatedPageCount = count)" @applyFilter="(data) => viewControls.applyFilter(data)"
    @applyLikeFilter="(data) => viewControls.applyLikeFilter(data)" @likeDoc="(data) => viewControls.likeDoc(data)"
    @selectionsChanged="(s) => viewControls.updateSelections(s)" @rowClick="openEdit" />

  <EmptyState v-else-if="meetings.data && !rows.length" name="Meetings" :icon="CalendarIcon" />

  <MeetingModal v-model="showModal" :meetingId="editId" @created="onCreated" @updated="reload" />
</template>

<script setup>
import ViewBreadcrumbs from '@/components/ViewBreadcrumbs.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import CalendarIcon from '@/components/Icons/CalendarIcon.vue'
import MeetingsListView from '@/components/ListViews/MeetingsListView.vue'
import MeetingModal from '@/components/Modals/MeetingModal.vue'
import EmptyState from '@/components/ListViews/EmptyState.vue'
import ViewControls from '@/components/ViewControls.vue'
import { getMeta } from '@/stores/meta'
import { formatDate, timeAgo } from '@/utils'
import { Button } from 'frappe-ui'
import { ref, computed } from 'vue'

const { getFormattedCurrency, getFormattedFloat } = getMeta('CRM Meeting')

const meetings = ref({})
const loadMore = ref(false)
const triggerResize = ref(false)
const updatedPageCount = ref(20)
const viewControls = ref(null)

const showModal = ref(false)
const editId = ref('')

function openCreate() {
  editId.value = ''
  showModal.value = true
}
function openEdit(name) {
  editId.value = name
  showModal.value = true
}
function reload() {
  // `meetings` adalah list resource yang di-v-model ViewControls; punya .reload().
  meetings.value?.reload?.()
}
function onCreated(name) {
  // Flip modal ke edit mode meeting baru -> tombol Absen muncul. Modal tetap terbuka.
  editId.value = name
  reload()
}

const rows = computed(() => {
  if (!meetings.value?.data?.data) return []
  return parseRows(meetings.value.data.data, meetings.value.data.columns)
})

const columns = computed(() => {
  let _columns = meetings.value?.data?.columns || []
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
    meetings.value.data.rows.forEach((row) => {
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
