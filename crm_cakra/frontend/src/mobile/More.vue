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
import ContactsIcon from '@/components/Icons/ContactsIcon.vue'
import OrganizationsIcon from '@/components/Icons/OrganizationsIcon.vue'
import EstimationIcon from '@/components/Icons/EstimationIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import LucideMapPin from '~icons/lucide/map-pin'
import LucideShoppingCart from '~icons/lucide/shopping-cart'
import LucideLayoutDashboard from '~icons/lucide/layout-dashboard'
import LucideBotMessageSquare from '~icons/lucide/bot-message-square'
import LucideFileText from '~icons/lucide/file-text'
import LucideBookOpen from '~icons/lucide/book-open'
import LucideMonitor from '~icons/lucide/monitor'
import { sessionStore } from '@/stores/session'
import { usersStore } from '@/stores/users'
import { getSettings } from '@/stores/settings'
import { mobileApp } from '@/composables/settings'
import { Avatar, Button, FeatherIcon } from 'frappe-ui'
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const session = sessionStore()
const { user } = session
const { getUser } = usersStore()
const { settings } = getSettings()

const me = computed(() => getUser(user))

// Meeting tidak di sini lagi: sudah jadi tab tengah. Leads yang turun ke sini.
const links = [
  { label: 'Leads', icon: LeadsIcon, list: 'leads' },
  { label: 'Accounts', icon: OrganizationsIcon, list: 'accounts' },
  { label: 'Contacts', icon: ContactsIcon, list: 'contacts' },
  { label: 'Absen', icon: LucideMapPin, to: 'MeetingAttendance' },
]

const desktopLinks = computed(() =>
  [
    { label: 'Dashboard', icon: LucideLayoutDashboard, to: 'Dashboard' },
    {
      label: 'Assistant',
      icon: LucideBotMessageSquare,
      to: 'Assistant',
      condition: () => Boolean(settings.value?.enable_crm_assistant),
    },
    { label: 'Estimations', icon: EstimationIcon, to: 'Estimations' },
    { label: 'Procurement', icon: LucideShoppingCart, to: 'Procurement' },
    { label: 'Tenders', icon: LucideFileText, to: 'Tenders' },
    { label: 'Tasks', icon: TaskIcon, to: 'Tasks' },
    { label: 'Notes', icon: NoteIcon, to: 'Notes' },
    { label: 'Manual Book', icon: LucideBookOpen, to: 'ManualBook' },
  ].filter((link) => (link.condition ? link.condition() : true)),
)

// Satu-satunya jalan keluar dari mode apps. Tanpa ini, sekali masuk
// /crm/mobile dari laptop, CRM desktop tidak bisa dibuka lagi sampai reload.
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
