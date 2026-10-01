<template>
  <div class="sticky top-0 z-10 flex h-12 items-center border-b bg-surface-white px-4">
    <span class="text-base font-semibold text-ink-gray-8">{{ __('More') }}</span>
  </div>

  <div class="flex items-center gap-3 border-b px-4 py-4">
    <Avatar :image="me?.user_image" :label="me?.full_name" size="2xl" />
    <div class="min-w-0">
      <div class="truncate text-base font-medium text-ink-gray-8">
        {{ me?.full_name }}
      </div>
      <div class="truncate text-sm text-ink-gray-5">{{ user }}</div>
    </div>
  </div>

  <div class="divide-y border-b">
    <button
      v-for="link in links"
      :key="link.label"
      class="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-surface-gray-2"
      @click="go(link)"
    >
      <component :is="link.icon" class="size-4 text-ink-gray-6" />
      <span class="flex-1 truncate text-base text-ink-gray-8">
        {{ __(link.label) }}
      </span>
      <FeatherIcon name="chevron-right" class="size-4 text-ink-gray-4" />
    </button>
  </div>

  <!-- Menu di bawah ini belum punya layar mobile sendiri: yang terbuka halaman
       desktop DI DALAM shell apps (header-nya menumpang #app-header). Sengaja
       tetap ditampilkan supaya tidak ada menu yang hilang dari HP. -->
  <div class="px-4 pb-2 pt-4 text-sm font-medium text-ink-gray-5">
    {{ __('Other') }}
  </div>
  <div class="divide-y border-y">
    <button
      v-for="link in desktopLinks"
      :key="link.label"
      class="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-surface-gray-2"
      @click="go(link)"
    >
      <component :is="link.icon" class="size-4 text-ink-gray-6" />
      <span class="flex-1 truncate text-base text-ink-gray-8">
        {{ __(link.label) }}
      </span>
      <FeatherIcon name="chevron-right" class="size-4 text-ink-gray-4" />
    </button>
  </div>

  <div class="flex flex-col gap-2 p-4">
    <Button
      class="w-full"
      :label="__('Switch to desktop CRM')"
      :iconLeft="LucideMonitor"
      @click="leaveMobileApp"
    />
    <Button
      class="w-full"
      :label="__('Log out')"
      theme="red"
      @click="session.logout.submit()"
    />
  </div>
</template>

<script setup>
import LeadsIcon from '@/components/Icons/LeadsIcon.vue'
import NotificationsIcon from '@/components/Icons/NotificationsIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import LucidePackage from '~icons/lucide/package'
import LucideTags from '~icons/lucide/tags'
import LucideReceipt from '~icons/lucide/receipt'
import LucideFileText from '~icons/lucide/file-text'
import ContactsIcon from '@/components/Icons/ContactsIcon.vue'
import OrganizationsIcon from '@/components/Icons/OrganizationsIcon.vue'
import EstimationIcon from '@/components/Icons/EstimationIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import LucideMapPin from '~icons/lucide/map-pin'
import LucideShoppingCart from '~icons/lucide/shopping-cart'
import LucideLayoutDashboard from '~icons/lucide/layout-dashboard'
import LucideBotMessageSquare from '~icons/lucide/bot-message-square'
import LucideBookOpen from '~icons/lucide/book-open'
import LucideMonitor from '~icons/lucide/monitor'
import { sessionStore } from '@/stores/session'
import { usersStore } from '@/stores/users'
import { getSettings } from '@/stores/settings'
import { mobileApp } from '@/composables/settings'
import { Avatar, Button, FeatherIcon } from 'frappe-ui'
import { computed } from 'vue'
import { menuAllowed } from '@/utils/menuAccess'
import { useRouter } from 'vue-router'

const router = useRouter()
const session = sessionStore()
const { user } = session
const { getUser } = usersStore()
const { settings } = getSettings()

const me = computed(() => getUser(user))

// Meeting tidak di sini lagi: sudah jadi tab tengah. Leads yang turun ke sini.
const links = [
  { label: 'Notifications', icon: NotificationsIcon, to: 'Notifications' },
  { label: 'Leads', icon: LeadsIcon, list: 'leads' },
  { label: 'Estimations', icon: EstimationIcon, list: 'estimations' },
  { label: 'Procurement', icon: LucideShoppingCart, list: 'procurement' },
  { label: 'Tenders', icon: LucideFileText, list: 'tenders' },
  { label: 'Accounts', icon: OrganizationsIcon, list: 'accounts' },
  { label: 'Contacts', icon: ContactsIcon, list: 'contacts' },
  { label: 'Tasks', icon: TaskIcon, list: 'tasks' },
  { label: 'Notes', icon: NoteIcon, list: 'notes' },
  { label: 'Absen', icon: LucideMapPin, to: 'MeetingAttendance' },
].filter((link) => menuAllowed(link.list || link.to))

const desktopLinks = computed(() =>
  [
    { label: 'Dashboard', icon: LucideLayoutDashboard, to: 'Dashboard' },
    {
      label: 'Assistant',
      icon: LucideBotMessageSquare,
      to: 'Assistant',
      condition: () => Boolean(settings.value?.enable_crm_assistant),
    },
    { label: 'Products', icon: LucidePackage, to: 'Products' },
    { label: 'Locations', icon: LucideMapPin, to: 'Locations' },
    { label: 'Cost Types', icon: LucideTags, to: 'CostTypes' },
    { label: 'Cost Components', icon: LucideReceipt, to: 'CostComponents' },
    { label: 'Call Logs', icon: PhoneIcon, to: 'Call Logs' },
    { label: 'Manual Book', icon: LucideBookOpen, to: 'ManualBook' },
  ].filter(
    (link) => (link.condition ? link.condition() : true) && menuAllowed(link.to),
  ),
)

function leaveMobileApp() {
  mobileApp.value = false
  router.push({ name: 'Dashboard' })
}

function go(link) {
  if (link.list) {
    return router.push({ name: 'MobileList', params: { list: link.list } })
  }
  router.push({ name: link.to })
}
</script>
