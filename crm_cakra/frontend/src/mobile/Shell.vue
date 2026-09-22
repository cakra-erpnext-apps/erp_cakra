<template>
  <div class="flex h-screen w-screen flex-col bg-surface-white">
    <!-- Halaman apps (Home/daftar/More) membawa header sendiri. Halaman detail
         dipakai bersama CRM desktop dan menaruh header-nya lewat Teleport ke
         #app-header, jadi target itu HARUS ada di sini -- tanpa itu tombol Save,
         state, dan breadcrumb-nya hilang tanpa error. -->
    <div
      v-if="!$route.meta.mobileApp"
      class="flex h-12 shrink-0 items-center border-b px-1"
    >
      <div id="app-header" class="min-w-0 flex-1" />
    </div>
    <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain">
      <slot />
    </div>
    <nav
      class="flex shrink-0 border-t bg-surface-white pb-[env(safe-area-inset-bottom)]"
    >
      <RouterLink
        v-for="tab in tabs"
        :key="tab.label"
        :to="tab.to"
        class="flex flex-1 flex-col items-center gap-1 py-2"
        :class="isActive(tab) ? 'text-ink-gray-9' : 'text-ink-gray-4'"
      >
        <component :is="tab.icon" class="size-5" />
        <span class="text-xs leading-none">{{ __(tab.label) }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<script setup>
import InquiriesIcon from '@/components/Icons/InquiriesIcon.vue'
import MeetingIcon from '@/components/Icons/MeetingIcon.vue'
import QuotationIcon from '@/components/Icons/QuotationIcon.vue'
import LucideHouse from '~icons/lucide/house'
import LucideMenu from '~icons/lucide/menu'
import { useRoute } from 'vue-router'

const route = useRoute()

// Meeting sengaja di tengah: itu posisi jempol paling enak, dan absen meeting
// yang paling sering dibuka di lapangan. Leads pindah ke More.
const tabs = [
  { label: 'Home', icon: LucideHouse, to: { name: 'MobileHome' } },
  { label: 'Inquiry', icon: InquiriesIcon, to: { name: 'MobileList', params: { list: 'inquiries' } } },
  { label: 'Meeting', icon: MeetingIcon, to: { name: 'MobileList', params: { list: 'meetings' } } },
  { label: 'Quotation', icon: QuotationIcon, to: { name: 'MobileList', params: { list: 'quotations' } } },
  { label: 'More', icon: LucideMenu, to: { name: 'MobileMore' } },
]

function isActive(tab) {
  if (tab.to.params) return route.params.list === tab.to.params.list
  return route.name === tab.to.name
}
</script>
