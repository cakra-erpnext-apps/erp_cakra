<template>
  <LayoutHeader>
    <template #left-header>
      <div class="flex items-center gap-2">
        <div class="text-lg font-medium text-ink-gray-9">
          {{ __('Assistant') }}
        </div>
        <Badge v-if="agentName" :label="agentName" variant="subtle" />
      </div>
    </template>
    <template #right-header>
      <Button
        :label="__('Riwayat')"
        :iconLeft="LucideHistory"
        @click="chatRef?.toggleHistory()"
      />
      <Button
        :label="__('Chat Baru')"
        :iconLeft="LucidePlus"
        @click="chatRef?.startNewSession()"
      />
    </template>
  </LayoutHeader>

  <!-- Chat-nya sendiri ada di komponen reusable (juga dipakai panel Dashboard). -->
  <AssistantChat
    ref="chatRef"
    class="flex-1"
    @loaded="(s) => (agentName = s.agentName)"
  />
</template>

<script setup>
import AssistantChat from '@/components/Assistant/AssistantChat.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import LucideHistory from '~icons/lucide/history'
import LucidePlus from '~icons/lucide/plus'
import { Badge, Button } from 'frappe-ui'
import { ref } from 'vue'

const agentName = ref('')
const chatRef = ref(null)
</script>
