<template>
  <div class="flex flex-col h-full overflow-hidden">
    <LayoutHeader>
      <template #left-header>
        <ViewBreadcrumbs routeName="Dashboard" />
      </template>
      <template #right-header>
        <Button
          v-if="!editing && showAssistantButton"
          :label="__('Assistant')"
          :iconLeft="LucideSparkles"
          :theme="showAssistant ? 'blue' : 'gray'"
          @click="toggleAssistant"
        />
        <Button
          v-if="!editing"
          :label="__('Refresh')"
          :iconLeft="LucideRefreshCcw"
          @click="dashboardItems.reload"
        />
        <Button
          v-if="!editing && isAdmin()"
          :label="__('Edit')"
          :iconLeft="LucidePenLine"
          @click="enableEditing"
        />
        <Button
          v-if="editing"
          :label="__('Chart')"
          iconLeft="plus"
          @click="showAddChartModal = true"
        />
        <Button
          v-if="editing && isAdmin()"
          :label="__('Reset to Default')"
          :iconLeft="LucideUndo2"
          @click="resetToDefault"
        />
        <Button v-if="editing" :label="__('Cancel')" @click="cancel" />
        <Button
          v-if="editing"
          variant="solid"
          :label="__('Save')"
          :disabled="!dirty"
          :loading="saveDashboard.loading"
          @click="save"
        />
      </template>
    </LayoutHeader>

    <!-- Isi halaman: dashboard di kiri, panel assistant (opsional) di kanan. -->
    <div class="flex flex-1 overflow-hidden">
      <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
    <div class="p-5 pb-2 flex items-center gap-4">
      <!-- Scope: Mine / Branch / All. Hanya scope yang boleh dipakai user ini
           yang dirender (server yang menentukan, lihat get_allowed_scopes). -->
      <div
        v-if="allowedScopes.length > 1"
        class="flex rounded bg-surface-gray-2 p-0.5"
      >
        <button
          v-for="s in allowedScopes"
          :key="s"
          class="rounded px-3 py-1 text-sm transition-colors"
          :class="
            scope === s
              ? 'bg-surface-white font-medium text-ink-gray-8 shadow-sm'
              : 'text-ink-gray-5 hover:text-ink-gray-7'
          "
          @click="updateScope(s)"
        >
          {{ __(SCOPE_LABELS[s]) }}
        </button>
      </div>

      <Dropdown
        v-if="!showDatePicker"
        v-model="preset"
        :options="options"
        class="form-control"
        :placeholder="__('Select Range')"
        :button="{
          label: __(preset),
          class:
            '!w-full justify-start [&>span]:mr-auto [&>svg]:text-ink-gray-5',
          variant: 'outline',
          iconRight: 'chevron-down',
          iconLeft: 'calendar',
        }"
      />
      <DateRangePicker
        v-else
        ref="datePickerRef"
        class="!w-48"
        :value="filters.period"
        variant="outline"
        :placeholder="__('Period')"
        :formatter="formatRange"
        @change="
          (v) =>
            updateFilter('period', v, () => {
              showDatePicker = false
              if (!v) {
                filters.period = getLastXDays()
                preset = 'Last 30 Days'
              } else {
                preset = formatter(v)
              }
            })
        "
      >
        <template #prefix>
          <LucideCalendar class="size-4 text-ink-gray-5 mr-2" />
        </template>
      </DateRangePicker>
      <Link
        v-if="isAdmin() || isManager()"
        class="form-control w-40"
        variant="outline"
        :value="filters.branch"
        doctype="CMI Office"
        :placeholder="__('Branch')"
        @change="(v) => updateFilter('branch', v)"
      />
      <Link
        v-if="isAdmin() || isManager()"
        class="form-control w-48"
        variant="outline"
        :value="filters.user && getUser(filters.user).full_name"
        doctype="User"
        :filters="{
          name: ['in', users.data.crmUsers?.map((u) => u.name)],
          ignore_user_type: 1,
        }"
        :placeholder="__('Sales User')"
        :hideMe="true"
        @change="(v) => updateFilter('user', v)"
      >
        <template #prefix>
          <UserAvatar
            v-if="filters.user"
            class="mr-2"
            :user="filters.user"
            size="sm"
          />
        </template>
        <template #item-prefix="{ option }">
          <UserAvatar class="mr-2" :user="option.value" size="sm" />
        </template>
        <template #item-label="{ option }">
          <Tooltip :text="option.value">
            <div class="cursor-pointer">
              {{ getUser(option.value).full_name }}
            </div>
          </Tooltip>
        </template>
      </Link>
    </div>

        <div class="w-full flex-1 overflow-y-scroll">
          <DashboardGrid
            v-if="!dashboardItems.loading && dashboardItems.data"
            v-model="dashboardItems.data"
            class="pt-1"
            :editing="editing"
          />
        </div>
      </div>

      <!-- Panel assistant: agent yang paham dashboard ini — bisa menjelaskan
           angka, memberi masukan, dan (untuk admin) merapikan layout. -->
      <Resizer
        v-if="showAssistant"
        side="right"
        class="flex flex-col border-l"
        :defaultWidth="420"
        :minWidth="320"
        :maxWidth="640"
      >
        <div
          class="flex h-[41px] shrink-0 items-center justify-between border-b px-4"
        >
          <div class="flex items-center gap-2 text-base font-medium text-ink-gray-9">
            <LucideSparkles class="size-4 text-ink-gray-7" />
            {{ __('Assistant') }}
          </div>
          <div class="flex items-center gap-1">
            <Tooltip :text="__('Riwayat sesi')">
              <Button variant="ghost" @click="assistantChatRef?.toggleHistory()">
                <template #icon>
                  <LucideHistory class="size-4" />
                </template>
              </Button>
            </Tooltip>
            <Tooltip :text="__('Chat baru (/clear)')">
              <Button variant="ghost" @click="assistantChatRef?.startNewSession()">
                <template #icon>
                  <LucidePlus class="size-4" />
                </template>
              </Button>
            </Tooltip>
            <Button variant="ghost" @click="showAssistant = false">
              <template #icon>
                <LucideX class="size-4" />
              </template>
            </Button>
          </div>
        </div>
        <AssistantChat
          ref="assistantChatRef"
          class="min-h-0 flex-1"
          compact
          :context="assistantContext"
          :suggestions="assistantSuggestions"
          :title="__('Dashboard Assistant')"
          :placeholder="__('Tanya tentang dashboard ini...')"
          @dashboard-updated="dashboardItems.reload()"
        />
      </Resizer>
    </div>
  </div>
  <AddChartModal
    v-if="showAddChartModal"
    v-model="showAddChartModal"
    v-model:items="dashboardItems.data"
  />
</template>

<script setup lang="ts">
import AddChartModal from '@/components/Dashboard/AddChartModal.vue'
import LucideRefreshCcw from '~icons/lucide/refresh-ccw'
import LucideUndo2 from '~icons/lucide/undo-2'
import LucidePenLine from '~icons/lucide/pen-line'
import LucideSparkles from '~icons/lucide/sparkles'
import LucideX from '~icons/lucide/x'
import LucideHistory from '~icons/lucide/history'
import LucidePlus from '~icons/lucide/plus'
import AssistantChat from '@/components/Assistant/AssistantChat.vue'
import DashboardGrid from '@/components/Dashboard/DashboardGrid.vue'
import Resizer from '@/components/Resizer.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import ViewBreadcrumbs from '@/components/ViewBreadcrumbs.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import Link from '@/components/Controls/Link.vue'
import { usersStore } from '@/stores/users'
import { getSettings } from '@/stores/settings'
import { copy } from '@/utils'
import { getLastXDays, formatter, formatRange } from '@/utils/dashboard'
import {
  usePageMeta,
  createResource,
  DateRangePicker,
  Dropdown,
  Tooltip,
} from 'frappe-ui'
import { ref, reactive, computed, provide } from 'vue'

const { users, getUser, isManager, isAdmin } = usersStore()
const { settings } = getSettings()

const editing = ref(false)

// Panel assistant di samping dashboard. Mengikuti toggle CRM Assistant yang sama
// dengan menu di sidebar; pilihan buka/tutup diingat per browser.
const showAssistant = ref(localStorage.getItem('dashboardAssistantOpen') === '1')
const assistantChatRef = ref(null)
const showAssistantButton = computed(() =>
  Boolean(settings.value?.enable_crm_assistant),
)

function toggleAssistant() {
  showAssistant.value = !showAssistant.value
  localStorage.setItem('dashboardAssistantOpen', showAssistant.value ? '1' : '0')
}

const assistantSuggestions = [
  __('Jelaskan kondisi dashboard saya saat ini.'),
  __('Apa yang paling perlu saya perhatikan?'),
  __('Kenapa angka inquiry saya begini?'),
  __('Rapikan susunan dashboard ini.'),
]

// Konteks layar untuk agent: periode, scope, dan filter yang sedang aktif —
// dikirim tiap pesan supaya jawaban agent memakai angka yang sama dengan yang
// sedang dilihat user (berlaku turn itu saja, tidak disimpan di transcript).
const assistantContext = computed(() => {
  const parts = [
    'User sedang melihat halaman CRM Dashboard (Manager Dashboard).',
    `Periode aktif: ${fromDate.value || '(default bulan ini)'} s/d ${toDate.value || '(default bulan ini)'}.`,
    `Scope aktif: ${scope.value}.`,
  ]
  if (filters.user) parts.push(`Filter sales user: ${filters.user}.`)
  if (filters.branch) parts.push(`Filter branch: ${filters.branch}.`)
  parts.push(
    'Saat memanggil tool dashboard (crm_dashboard_overview / crm_dashboard_get_chart), pakai periode, scope, dan filter di atas.',
  )
  return parts.join('\n')
})

const showDatePicker = ref(false)
const datePickerRef = ref(null)
const preset = ref('Last 30 Days')
const showAddChartModal = ref(false)

const filters = reactive({
  period: getLastXDays(),
  user: null,
  branch: null,
})

// Scope dashboard: mine / branch / all.
// Daftar scope datang dari server, bukan dihitung di sini: Sales User tidak boleh
// melihat 'all', dan 'branch' tidak ada artinya bila user belum punya branch.
// Menyembunyikan tombolnya di frontend saja tidak cukup — server tetap menolak.
const SCOPE_LABELS = {
  mine: 'Mine',
  branch: 'Branch',
  all: 'All Branches',
}

const scope = ref('mine')

const scopeResource = createResource({
  url: 'crm_cakra.api.dashboard.get_allowed_scopes',
  auto: true,
})

const allowedScopes = computed(() => scopeResource.data?.scopes || ['mine'])

function updateScope(value) {
  if (scope.value === value) return
  scope.value = value
  // Pemilih user/branch hanya masuk akal di dalam scope; membiarkannya terisi
  // saat berpindah scope membuat angkanya tidak sesuai tombol yang aktif.
  filters.user = null
  filters.branch = null
  dashboardItems.reload()
}

const fromDate = computed(() => {
  if (!filters.period) return null
  return filters.period.split(',')[0]
})

const toDate = computed(() => {
  if (!filters.period) return null
  return filters.period.split(',')[1]
})

function updateFilter(key: string, value: unknown, callback?: () => void) {
  filters[key] = value
  callback?.()
  dashboardItems.reload()
}

const options = computed(() => [
  {
    group: 'Presets',
    hideLabel: true,
    items: [
      {
        label: __('Last 7 Days'),
        onClick: () => {
          preset.value = 'Last 7 Days'
          filters.period = getLastXDays(7)
          dashboardItems.reload()
        },
      },
      {
        label: __('Last 30 Days'),
        onClick: () => {
          preset.value = 'Last 30 Days'
          filters.period = getLastXDays(30)
          dashboardItems.reload()
        },
      },
      {
        label: __('Last 60 Days'),
        onClick: () => {
          preset.value = 'Last 60 Days'
          filters.period = getLastXDays(60)
          dashboardItems.reload()
        },
      },
      {
        label: __('Last 90 Days'),
        onClick: () => {
          preset.value = 'Last 90 Days'
          filters.period = getLastXDays(90)
          dashboardItems.reload()
        },
      },
    ],
  },
  {
    label: __('Custom Range'),
    onClick: () => {
      showDatePicker.value = true
      setTimeout(() => datePickerRef.value?.open(), 0)
      preset.value = 'Custom Range'
      filters.period = null // Reset period to allow custom date selection
    },
  },
])

const dashboardItems = createResource({
  url: 'crm_cakra.api.dashboard.get_dashboard',
  makeParams() {
    return {
      from_date: fromDate.value,
      to_date: toDate.value,
      user: filters.user,
      scope: scope.value,
      branch: filters.branch,
    }
  },
  auto: true,
})

const dirty = computed(() => {
  if (!editing.value) return false
  return JSON.stringify(dashboardItems.data) !== JSON.stringify(oldItems.value)
})

const oldItems = ref([])

provide('fromDate', fromDate)
provide('toDate', toDate)
provide('filters', filters)
provide('scope', scope)

function enableEditing() {
  editing.value = true
  oldItems.value = copy(dashboardItems.data)
}

function cancel() {
  editing.value = false
  dashboardItems.data = copy(oldItems.value)
}

const saveDashboard = createResource({
  url: 'frappe.client.set_value',
  method: 'POST',
  onSuccess: () => {
    dashboardItems.reload()
    editing.value = false
  },
})

function save() {
  const dashboardItemsCopy = copy(dashboardItems.data)

  dashboardItemsCopy.forEach((item: Record<string, unknown>) => {
    delete item.data
  })

  saveDashboard.submit({
    doctype: 'CRM Dashboard',
    name: 'Manager Dashboard',
    fieldname: 'layout',
    value: JSON.stringify(dashboardItemsCopy),
  })
}

function resetToDefault() {
  createResource({
    url: 'crm_cakra.api.dashboard.reset_to_default',
    auto: true,
    onSuccess: () => {
      dashboardItems.reload()
      editing.value = false
    },
  })
}

usePageMeta(() => {
  return { title: __('CRM Dashboard') }
})
</script>
