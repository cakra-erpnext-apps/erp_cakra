<template>
  <div class="flex h-full min-h-0 flex-col overflow-hidden bg-surface-white">
    <!-- Daftar riwayat sesi (dibuka lewat tombol Riwayat / setelah /clear) -->
    <div
      v-if="historyMode"
      class="flex-1 overflow-y-auto"
      :class="compact ? 'px-3 py-4' : 'px-4 py-6 sm:px-10'"
    >
      <div
        class="flex w-full flex-col gap-2"
        :class="compact ? '' : 'mx-auto max-w-3xl'"
      >
        <div class="mb-1 text-base font-medium text-ink-gray-8">
          {{ __('Riwayat sesi') }}
        </div>
        <div
          v-if="!historySessions.length"
          class="rounded-lg border border-outline-gray-2 px-3 py-4 text-center text-p-sm text-ink-gray-5"
        >
          {{ __('Belum ada sesi sebelumnya. Ketik /clear untuk menutup sesi dan memulai yang baru.') }}
        </div>
        <button
          v-for="s in historySessions"
          :key="s.name"
          class="rounded-lg border border-outline-gray-2 px-3 py-2.5 text-left transition-colors hover:border-outline-gray-3 hover:bg-surface-gray-1"
          @click="openSession(s.name)"
        >
          <div class="truncate text-p-base text-ink-gray-8">
            {{ s.summary || __('(tanpa ringkasan)') }}
          </div>
          <div class="mt-0.5 text-p-sm text-ink-gray-5">
            {{ s.agent_name }} - {{ (s.creation || '').slice(0, 16) }}
          </div>
        </button>
      </div>
    </div>

    <!-- Riwayat chat (sesi aktif, atau sesi arsip yang sedang dibuka) -->
    <div
      v-else
      ref="scrollArea"
      class="flex-1 overflow-y-auto"
      :class="compact ? 'px-3 py-4' : 'px-4 py-6 sm:px-10'"
    >
      <div
        class="flex w-full flex-col gap-6"
        :class="compact ? '' : 'mx-auto max-w-3xl'"
      >
        <!-- Penanda sedang membaca sesi arsip -->
        <div
          v-if="viewing"
          class="flex items-center justify-between rounded-lg bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-6"
        >
          <span>
            {{ __('Riwayat') }}: {{ viewing.agent_name }} -
            {{ (viewing.creation || '').slice(0, 16) }}
          </span>
          <Button variant="ghost" :label="__('Kembali')" @click="closeViewing" />
        </div>

        <!-- Sambutan + saran pembuka -->
        <div
          v-if="!viewing && !messages.length && !loadingSession"
          :class="compact ? 'mt-4' : 'mt-12'"
        >
          <div class="flex flex-col items-center text-center">
            <div
              class="flex size-11 items-center justify-center rounded-full bg-surface-gray-2"
            >
              <LucideSparkles class="size-5 text-ink-gray-7" />
            </div>
            <div class="mt-3 text-lg font-medium text-ink-gray-8">
              {{ title || __('CRM Assistant') }}
            </div>
            <div class="mt-1 max-w-lg text-p-base text-ink-gray-6">
              {{ greeting || __('Tulis pesan untuk mulai.') }}
            </div>
          </div>

          <div
            class="mx-auto mt-6 grid gap-2"
            :class="compact ? 'grid-cols-1' : 'max-w-xl sm:grid-cols-2'"
          >
            <button
              v-for="s in suggestions"
              :key="s"
              class="rounded-lg border border-outline-gray-2 px-3 py-2.5 text-left text-p-sm text-ink-gray-7 transition-colors hover:border-outline-gray-3 hover:bg-surface-gray-1"
              @click="sendText(s)"
            >
              {{ s }}
            </button>
          </div>
        </div>

        <div v-for="(m, i) in shownMessages" :key="i" class="flex gap-3">
          <!-- Avatar hanya di sisi assistant; pesan user rata kanan tanpa avatar. -->
          <div
            v-if="m.role !== 'user'"
            class="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-surface-gray-2"
          >
            <LucideSparkles class="size-3.5 text-ink-gray-7" />
          </div>

          <div
            class="flex min-w-0 flex-1"
            :class="m.role === 'user' ? 'justify-end' : 'justify-start'"
          >
            <!-- Balasan assistant dirender sebagai markdown: model membalas dengan
                 **tebal**, daftar bernomor, dsb. Tanpa ini, tanda bintang terlihat mentah. -->
            <div
              v-if="m.role !== 'user'"
              class="assistant-md min-w-0 text-p-base leading-relaxed text-ink-gray-8"
              v-html="render(m.text)"
            />
            <div
              v-else
              class="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-surface-gray-2 px-3.5 py-2 text-p-base leading-relaxed text-ink-gray-8"
            >
              {{ m.text }}
            </div>
          </div>
        </div>

        <!-- Indikator mengetik: tiga titik beranimasi. -->
        <div v-if="sending" class="flex gap-3">
          <div
            class="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-surface-gray-2"
          >
            <LucideSparkles class="size-3.5 text-ink-gray-7" />
          </div>
          <div class="flex items-center gap-1 py-2">
            <span class="typing-dot" />
            <span class="typing-dot" style="animation-delay: 0.15s" />
            <span class="typing-dot" style="animation-delay: 0.3s" />
          </div>
        </div>
      </div>
    </div>

    <!-- Input (disembunyikan saat membaca riwayat) -->
    <div
      v-if="!historyMode && !viewing"
      :class="compact ? 'px-3 pb-3' : 'px-4 pb-4 sm:px-10'"
    >
      <div class="w-full" :class="compact ? '' : 'mx-auto max-w-3xl'">
        <div
          class="flex items-end gap-2 rounded-xl border border-outline-gray-2 bg-surface-white p-2 shadow-sm transition-colors focus-within:border-outline-gray-3"
        >
          <!-- textarea polos (bukan komponen), supaya nilainya benar-benar dikuasai
               di sini: pesan wajib hilang dari kolom begitu terkirim. -->
          <textarea
            ref="inputBox"
            v-model="draft"
            rows="1"
            :placeholder="placeholder || __('Tanya apa saja tentang lead, inquiry, atau quotation...')"
            :disabled="loadingSession"
            class="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-p-base text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none disabled:cursor-not-allowed"
            @input="autoGrow"
            @keydown.enter.exact.prevent="send"
          />
          <Button
            variant="solid"
            :loading="sending"
            :disabled="!draft.trim() || sending || loadingSession"
            @click="send"
          >
            <template #icon>
              <LucideArrowUp class="size-4" />
            </template>
          </Button>
        </div>

        <div
          v-if="!configured && !loadingSession"
          class="mt-1.5 text-p-sm text-ink-red-3"
        >
          {{ __('Akun AI belum dikonfigurasi. Hubungi administrator.') }}
        </div>
        <div v-else-if="!compact" class="mt-1.5 text-center text-p-sm text-ink-gray-4">
          {{ __('Enter untuk kirim, Shift+Enter baris baru, /clear untuk sesi baru') }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import LucideSparkles from '~icons/lucide/sparkles'
import LucideArrowUp from '~icons/lucide/arrow-up'
import { sanitizeHTML } from '@/utils'
import { Button, call, toast } from 'frappe-ui'
import { marked } from 'marked'
import { ref, computed, nextTick, onMounted } from 'vue'

// Chat CRM Assistant yang bisa ditempel di mana saja: halaman penuh (/assistant)
// maupun panel samping (mis. Dashboard). Satu user = satu agent — komponen ini
// selalu bicara ke agent yang sama, di mana pun ia ditempel.
const props = defineProps({
  // Mode panel samping: padding rapat, tanpa max-width tengah, saran 1 kolom.
  compact: { type: Boolean, default: false },
  // Konteks layar yang dikirim ke agent tiap pesan (turn ini saja, tidak
  // disimpan di transcript) — mis. periode & scope dashboard yang sedang dilihat.
  context: { type: String, default: '' },
  // Saran pembuka; default seperti halaman /assistant.
  suggestions: {
    type: Array,
    default: () => [
      __('Quotation mana yang belum dijawab customer?'),
      __('Inquiry apa yang perlu saya tindak lanjuti?'),
      __('Ringkas pipeline saya bulan ini.'),
      __('Berapa win rate saya belakangan ini?'),
    ],
  },
  title: { type: String, default: '' },
  placeholder: { type: String, default: '' },
})

const emit = defineEmits(['loaded', 'dashboard-updated'])

const messages = ref([])
const draft = ref('')
const sending = ref(false)
const loadingSession = ref(true)
const greeting = ref('')
const configured = ref(true)
const scrollArea = ref(null)
const inputBox = ref(null)

// Riwayat sesi: /clear menutup sesi aktif (server menyimpannya sebagai arsip)
// dan memulai sesi baru; sesi lama bisa dibuka lagi lewat daftar riwayat.
const historyMode = ref(false)
const historySessions = ref([])
const viewing = ref(null) // sesi arsip yang sedang dibaca (read-only)

const shownMessages = computed(() =>
  viewing.value ? viewing.value.messages || [] : messages.value,
)

async function startNewSession() {
  if (sending.value) return
  try {
    const r = await call('assistant.assistant.crm.clear_session')
    messages.value = r.messages || []
    greeting.value = r.greeting || greeting.value
    configured.value = !!r.configured
    historyMode.value = false
    viewing.value = null
    emit('loaded', { agentName: r.agent_name || '', configured: configured.value })
    toast.success(__('Sesi baru dimulai. Chat sebelumnya tersimpan di riwayat.'))
    nextTick(() => inputBox.value?.focus())
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal memulai sesi baru.'))
  }
}

async function toggleHistory() {
  // Sedang di riwayat (daftar ataupun membaca sesi) -> kembali ke chat aktif.
  if (historyMode.value || viewing.value) {
    historyMode.value = false
    viewing.value = null
    scrollToBottom()
    return
  }
  try {
    historySessions.value = (await call('assistant.assistant.crm.sessions')) || []
    historyMode.value = true
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal memuat riwayat.'))
  }
}

async function openSession(name) {
  try {
    viewing.value = await call('assistant.assistant.crm.session_messages', { name })
    historyMode.value = false
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal membuka sesi.'))
  }
}

function closeViewing() {
  viewing.value = null
  historyMode.value = true
}

// Parent (halaman /assistant, panel Dashboard) menaruh tombolnya sendiri.
defineExpose({ startNewSession, toggleHistory })

// Balasan model memakai markdown. Di-sanitasi supaya v-html tetap aman.
function render(text) {
  if (!text) return ''
  return sanitizeHTML(marked.parse(text, { gfm: true, breaks: true, async: false }))
}

function scrollToBottom() {
  nextTick(() => {
    const el = scrollArea.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// Textarea tumbuh mengikuti isi, lalu kembali satu baris setelah dikosongkan.
function autoGrow() {
  const el = inputBox.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

function resetInput() {
  draft.value = ''
  nextTick(() => {
    const el = inputBox.value
    if (!el) return
    el.style.height = 'auto'
    el.focus()
  })
}

onMounted(async () => {
  try {
    const r = await call('assistant.assistant.crm.session')
    greeting.value = r.greeting || ''
    configured.value = !!r.configured
    messages.value = r.messages || []
    emit('loaded', { agentName: r.agent_name || '', configured: configured.value })
    scrollToBottom()
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal memuat assistant.'))
  } finally {
    loadingSession.value = false
  }
})

function send() {
  sendText(draft.value)
}

async function sendText(text) {
  text = (text || '').trim()
  if (!text || sending.value || loadingSession.value) return

  // Perintah chat: /clear = tutup sesi ini (tersimpan di riwayat), mulai baru.
  if (text.toLowerCase() === '/clear') {
    resetInput()
    await startNewSession()
    return
  }

  // Kosongkan kolom SEBELUM menunggu balasan: kalau tidak, pesan yang sudah terkirim
  // masih tertinggal di kolom selama AI berpikir, dan bisa terkirim dua kali.
  resetInput()
  messages.value.push({ role: 'user', text })
  sending.value = true
  scrollToBottom()

  try {
    const r = await call('assistant.assistant.crm.chat', {
      message: text,
      context: props.context || undefined,
    })
    messages.value.push({ role: 'assistant', text: r.reply || '' })
    // Agent mengubah layout dashboard di turn ini -> induk (halaman Dashboard)
    // bisa langsung reload grid-nya.
    if (r.dashboard_updated) emit('dashboard-updated')
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

<style scoped>
.typing-dot {
  height: 6px;
  width: 6px;
  border-radius: 9999px;
  background-color: var(--ink-gray-4, #9ca3af);
  animation: typing 1.2s ease-in-out infinite;
}

@keyframes typing {
  0%,
  60%,
  100% {
    opacity: 0.25;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

/* Markdown balasan assistant: rapikan jarak & beri gaya pada elemen yang
   benar-benar dipakai model (tebal, daftar, kode, tabel). */
.assistant-md :deep(p) {
  margin: 0 0 0.6rem;
}
.assistant-md :deep(p:last-child) {
  margin-bottom: 0;
}
.assistant-md :deep(strong) {
  font-weight: 600;
  color: var(--ink-gray-9, #171717);
}
.assistant-md :deep(ul),
.assistant-md :deep(ol) {
  margin: 0 0 0.6rem;
  padding-left: 1.25rem;
}
.assistant-md :deep(ul) {
  list-style: disc;
}
.assistant-md :deep(ol) {
  list-style: decimal;
}
.assistant-md :deep(li) {
  margin: 0.15rem 0;
}
.assistant-md :deep(code) {
  border-radius: 4px;
  background-color: var(--surface-gray-2, #f3f4f6);
  padding: 0.1rem 0.3rem;
  font-size: 0.85em;
}
.assistant-md :deep(pre) {
  overflow-x: auto;
  border-radius: 8px;
  background-color: var(--surface-gray-2, #f3f4f6);
  padding: 0.75rem;
}
.assistant-md :deep(pre code) {
  background: none;
  padding: 0;
}
.assistant-md :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 0.6rem;
}
.assistant-md :deep(th),
.assistant-md :deep(td) {
  border: 1px solid var(--outline-gray-2, #e5e7eb);
  padding: 0.3rem 0.5rem;
  text-align: left;
}
.assistant-md :deep(a) {
  color: var(--ink-blue-3, #2563eb);
  text-decoration: underline;
}
</style>
