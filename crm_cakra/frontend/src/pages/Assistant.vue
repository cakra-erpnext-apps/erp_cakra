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
  </LayoutHeader>

  <div class="flex flex-1 flex-col overflow-hidden">
    <!-- Riwayat chat -->
    <div ref="scrollArea" class="flex-1 overflow-y-auto px-4 py-6 sm:px-10">
      <div class="mx-auto flex w-full max-w-3xl flex-col gap-4">
        <div
          v-if="!messages.length && !loadingSession"
          class="mt-16 text-center text-ink-gray-5"
        >
          <div class="text-lg font-medium text-ink-gray-7">
            {{ __('CRM Assistant') }}
          </div>
          <div class="mt-1 text-p-base">
            {{ greeting || __('Tulis pesan untuk mulai.') }}
          </div>
        </div>

        <template v-for="(m, i) in messages" :key="i">
          <div
            class="flex"
            :class="m.role === 'user' ? 'justify-end' : 'justify-start'"
          >
            <div
              class="max-w-[85%] whitespace-pre-wrap rounded-lg px-3.5 py-2.5 text-p-base leading-relaxed"
              :class="
                m.role === 'user'
                  ? 'bg-surface-gray-6 text-ink-white'
                  : 'bg-surface-gray-2 text-ink-gray-8'
              "
            >{{ m.text }}</div>
          </div>
        </template>

        <div v-if="sending" class="flex justify-start">
          <div
            class="rounded-lg bg-surface-gray-2 px-3.5 py-2.5 text-p-base text-ink-gray-5"
          >
            {{ __('Assistant sedang mengetik...') }}
          </div>
        </div>
      </div>
    </div>

    <!-- Input -->
    <div class="border-t px-4 py-3 sm:px-10">
      <div class="mx-auto flex w-full max-w-3xl items-end gap-2">
        <Textarea
          ref="inputBox"
          v-model="draft"
          :rows="2"
          class="flex-1"
          :placeholder="__('Tulis pesan... (Enter untuk kirim, Shift+Enter baris baru)')"
          :disabled="sending || loadingSession"
          @keydown.enter.exact.prevent="send"
        />
        <Button
          variant="solid"
          :label="__('Kirim')"
          :loading="sending"
          :disabled="!draft.trim() || loadingSession"
          @click="send"
        />
      </div>
      <div
        v-if="!configured && !loadingSession"
        class="mx-auto mt-1.5 w-full max-w-3xl text-p-sm text-ink-red-3"
      >
        {{ __('Akun AI belum dikonfigurasi. Hubungi administrator.') }}
      </div>
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import { Badge, Button, Textarea, call, toast } from 'frappe-ui'
import { ref, nextTick, onMounted } from 'vue'

const messages = ref([])
const draft = ref('')
const sending = ref(false)
const loadingSession = ref(true)
const agentName = ref('')
const greeting = ref('')
const configured = ref(true)
const scrollArea = ref(null)

function scrollToBottom() {
  nextTick(() => {
    const el = scrollArea.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

onMounted(async () => {
  try {
    const r = await call('assistant.assistant.crm.session')
    agentName.value = r.agent_name || ''
    greeting.value = r.greeting || ''
    configured.value = !!r.configured
    messages.value = r.messages || []
    scrollToBottom()
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal memuat assistant.'))
  } finally {
    loadingSession.value = false
  }
})

async function send() {
  const text = draft.value.trim()
  if (!text || sending.value) return
  draft.value = ''
  messages.value.push({ role: 'user', text })
  sending.value = true
  scrollToBottom()
  try {
    const r = await call('assistant.assistant.crm.chat', { message: text })
    messages.value.push({ role: 'assistant', text: r.reply || '' })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      text: e.messages?.[0] || e.message || __('Gagal menghubungi assistant.'),
    })
  } finally {
    sending.value = false
    scrollToBottom()
  }
}
</script>
