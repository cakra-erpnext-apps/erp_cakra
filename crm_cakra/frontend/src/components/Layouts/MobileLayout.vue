<template>
  <div class="flex h-screen w-screen">
    <MobileSidebar />
    <div class="flex h-full flex-1 flex-col overflow-auto bg-surface-white">
      <MobileAppHeader />
      <slot />
    </div>
    <GlobalModals />
    <AssistantBubble />
  </div>
</template>
<script setup>
import MobileSidebar from '@/components/Mobile/MobileSidebar.vue'
import MobileAppHeader from '@/components/Mobile/MobileAppHeader.vue'
import GlobalModals from '@/components/Modals/GlobalModals.vue'
import AssistantBubble from '@/components/Assistant/AssistantBubble.vue'
</script>
