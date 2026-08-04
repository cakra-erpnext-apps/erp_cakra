<template>
  <LayoutHeader>
    <template #left-header>
      <ViewBreadcrumbs v-model="viewControls" routeName="Meetings" />
    </template>
    <template #right-header>
      <Button :label="__('Absen')" iconLeft="map-pin" @click="$router.push({ name: 'MeetingAttendance' })" />
      <Button :label="showCalendar ? __('List') : __('Calendar')" iconLeft="calendar"
        @click="showCalendar = !showCalendar" />
      <Button variant="solid" :label="__('Create')" iconLeft="plus" @click="openCreate" />
    </template>
  </LayoutHeader>

  <!-- Mode kalender: meeting diplot sesuai meeting_date; klik = edit -->
  <div v-if="showCalendar" id="meetings-calendar" class="flex-1 overflow-auto p-4">
    <Calendar :key="calendarEvents.length" :events="calendarEvents"
      :config="{ defaultMode: 'Month', isEditMode: false }"
      :onClick="(e) => openEdit(e.calendarEvent?.id || e.id)" />
  </div>

  <template v-else>
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
  </template>

  <MeetingModal v-model="showModal" :meetingId="editId" @created="onCreated" @updated="onModalSaved" />
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
import { Button, Calendar, createResource } from 'frappe-ui'
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'

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
function onModalSaved() {
  reload()
  if (showCalendar.value) calendarList.reload()
}

// ---- mode kalender --------------------------------------------------------
// Sumber datanya terpisah dari list ViewControls: kalender butuh SEMUA meeting
// ber-tanggal (list-nya berhalaman 20-an baris, kalender bakal bolong).
// Route MeetingsCalendar (menu sidebar Calendar) langsung membuka mode ini.
const showCalendar = ref(useRoute().name === 'MeetingsCalendar')
const calendarList = createResource({
  url: 'frappe.client.get_list',
  makeParams: () => ({
    doctype: 'CRM Meeting',
    filters: { meeting_date: ['is', 'set'] },
    fields: ['name', 'subject', 'status', 'meeting_date', 'venue'],
    order_by: 'meeting_date asc',
    limit_page_length: 0,
  }),
})
watch(showCalendar, (on) => on && calendarList.fetch(), { immediate: true })

const STATUS_COLOR = { Scheduled: 'blue', Visited: 'green', Cancelled: 'red' }
// Komponen Calendar frappe-ui butuh tanggal & jam TERPISAH (fromDate='YYYY-MM-DD',
// fromTime='HH:mm') — datetime utuh membuat event tak pernah cocok ke sel grid.
const calendarEvents = computed(() =>
  (calendarList.data || []).map((m) => {
    const s = String(m.meeting_date)
    const end = addHour(m.meeting_date)
    return {
      id: m.name,
      title: m.subject,
      venue: m.venue || '',
      // Kalender = JADWAL (meeting_date), bukan waktu absen. Blok 1 jam.
      fromDate: s.slice(0, 10),
      fromTime: s.slice(11, 16) || '00:00',
      toDate: end.slice(0, 10),
      toTime: end.slice(11, 16),
      color: STATUS_COLOR[m.status] || 'green',
    }
  }),
)
function addHour(dt) {
  const d = new Date(String(dt).replace(' ', 'T'))
  d.setHours(d.getHours() + 1)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:00`
}
function onCreated(name) {
  // Flip modal ke edit mode meeting baru -> tombol Absen muncul. Modal tetap terbuka.
  editId.value = name
  reload()
  // Meeting baru langsung tampil di kalender tanpa harus pindah-pindah mode.
  if (showCalendar.value) calendarList.reload()
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

<style>
/* Judul event kalender frappe-ui memakai --text per warna yang terlalu pucat.
   Dipertegas hanya di halaman ini (unscoped karena CalendarEvent bukan child scoped).
   Selector `p` (bukan .event-title): template Month CalendarEvent.vue tidak memberi
   class pada judulnya, jadi warnanya ikut sel tanggal (text-ink-gray-4 = nyaris putih
   untuk tanggal di luar bulan tampil). */
#meetings-calendar .event p {
  color: #1f2937 !important;
  font-weight: 600;
}
#meetings-calendar .event .event-subtitle {
  color: #4b5563 !important;
  font-weight: 400;
}
html[data-theme='dark'] #meetings-calendar .event p {
  color: #f3f4f6 !important;
}
html[data-theme='dark'] #meetings-calendar .event .event-subtitle {
  color: #d1d5db !important;
}
</style>
