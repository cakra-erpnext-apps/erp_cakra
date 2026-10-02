<template>
  <!-- Pop-up kanan bawah semua halaman CRM. Saat CRM dibuka ia muncul sendiri
       berisi pekerjaan yang masih pending (tanpa agent -- langsung dari data, jadi
       instan dan tidak makan kuota). Agent baru dipakai kalau user menekan
       "Tanya Assistant"; tiap pesannya membawa konteks halaman yang sedang dibuka. -->
  <div v-if="visible" class="fixed bottom-20 right-5 z-40 flex flex-col items-end gap-3">
    <div
      v-show="open"
      class="flex h-[560px] max-h-[calc(100vh-11rem)] w-[380px] max-w-[calc(100vw-2.5rem)] flex-col overflow-hidden rounded-xl border bg-surface-white shadow-2xl"
    >
      <div class="flex h-11 shrink-0 items-center justify-between border-b px-3">
        <div class="flex min-w-0 items-center gap-2 text-base font-medium text-ink-gray-9">
          <Button v-if="mode === 'chat'" variant="ghost" @click="mode = 'todo'">
            <template #icon><LucideArrowLeft class="size-4" /></template>
          </Button>
          <LucideSparkles v-else class="size-4 shrink-0 text-ink-gray-7" />
          <span class="truncate">
            {{ mode === 'chat' ? __('Assistant') : __('Pekerjaan Pending') }}
          </span>
        </div>
        <div class="flex items-center gap-1">
          <Tooltip v-if="mode === 'chat'" :text="__('Chat baru (/clear)')">
            <Button variant="ghost" @click="chat?.startNewSession()">
              <template #icon><LucidePlus class="size-4" /></template>
            </Button>
          </Tooltip>
          <Tooltip v-else :text="__('Muat ulang')">
            <Button variant="ghost" :loading="pending.loading" @click="pending.reload()">
              <template #icon><LucideRefreshCw class="size-4" /></template>
            </Button>
          </Tooltip>
          <Button variant="ghost" @click="open = false">
            <template #icon><LucideX class="size-4" /></template>
          </Button>
        </div>
      </div>

      <!-- Daftar pending, gaya pesan chat dari bot -->
      <div v-show="mode === 'todo'" class="flex min-h-0 flex-1 flex-col">
        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          <div class="mb-3 rounded-lg bg-surface-gray-2 px-3 py-2 text-base text-ink-gray-8">
            <template v-if="!pending.data">{{ __('Memuat pekerjaan Anda...') }}</template>
            <template v-else-if="rows.length">
              {{ __('Halo {0}, ada {1} pekerjaan yang masih pending. Yang paling mendesak di atas.', [firstName, rows.length]) }}
            </template>
            <template v-else>
              {{ __('Halo {0}, tidak ada pekerjaan yang menggantung. Semua beres.', [firstName]) }}
            </template>
          </div>

          <div
            v-for="r in rows"
            :key="r.name"
            class="mb-2 cursor-pointer rounded-lg border px-3 py-2 hover:bg-surface-gray-1"
            @click="go(r)"
          >
            <div class="flex items-center gap-2">
              <span class="size-2 shrink-0 rounded-full" :class="PRIORITY_DOT[r.priority]" />
              <span class="shrink-0 text-base font-medium text-ink-gray-9">{{ r.name }}</span>
              <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-6">{{ r.account }}</span>
              <Badge :label="__(r.status)" size="sm" />
            </div>
            <div class="mt-1 text-base text-ink-gray-8">{{ r.action }}</div>
            <div v-if="timing(r)" class="mt-0.5 text-sm" :class="r.priority === 'High' ? 'text-ink-red-4' : 'text-ink-gray-5'">
              {{ timing(r) }}
            </div>
          </div>
        </div>

        <div v-if="assistantEnabled" class="shrink-0 border-t p-3">
          <Button class="w-full" :label="__('Tanya Assistant')" @click="openChat">
            <template #prefix><LucideSparkles class="size-4" /></template>
          </Button>
        </div>
      </div>

      <!-- Chat agent, dirender sekali lalu disimpan supaya percakapan tidak hilang -->
      <AssistantChat
        v-if="chatOpened"
        v-show="mode === 'chat'"
        ref="chat"
        class="min-h-0 flex-1"
        compact
        :context="context"
        :suggestions="suggestions"
        :placeholder="__('Tanya tentang halaman ini...')"
      />
    </div>

    <button
      class="relative flex size-12 items-center justify-center rounded-full bg-surface-gray-7 text-ink-white shadow-lg hover:bg-surface-gray-6"
      :aria-label="__('Pekerjaan Pending')"
      @click="toggle"
    >
      <LucideX v-if="open" class="size-5" />
      <LucideSparkles v-else class="size-5" />
      <span
        v-if="!open && rows.length"
        class="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-surface-red-5 px-1 text-xs font-medium text-ink-white"
      >
        {{ rows.length }}
      </span>
    </button>
  </div>
</template>

<script setup>
import AssistantChat from '@/components/Assistant/AssistantChat.vue'
import { getSettings } from '@/stores/settings'
import { usersStore } from '@/stores/users'
import { Badge, Button, Tooltip, createResource } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LucideArrowLeft from '~icons/lucide/arrow-left'
import LucidePlus from '~icons/lucide/plus'
import LucideRefreshCw from '~icons/lucide/refresh-cw'
import LucideSparkles from '~icons/lucide/sparkles'
import LucideX from '~icons/lucide/x'

const route = useRoute()
const router = useRouter()
const { settings } = getSettings()
const { getUser } = usersStore()

const open = ref(false)
const mode = ref('todo')
const chatOpened = ref(false)
const chat = ref(null)

const visible = computed(() => route.name !== 'Assistant')
const assistantEnabled = computed(() => Boolean(settings.value?.enable_crm_assistant))
const firstName = computed(() => {
  const u = getUser()
  return u?.first_name || u?.full_name || ''
})

const PRIORITY_DOT = {
  High: 'bg-surface-red-5',
  Medium: 'bg-surface-amber-2',
  Low: 'bg-surface-gray-4',
}

// Muncul sendiri paling sering sekali tiap FCRM Settings.pending_popup_hours jam
// (default 24, 0 = tidak pernah), dan hanya kalau memang ada yang pending.
// Waktu terakhir tampil disimpan per user di browser ini.
const pending = createResource({
  url: 'crm_cakra.api.dashboard.get_my_pending',
  auto: true,
})

const shownKey = () => `crm_pending_popup_at:${getUser()?.name || ''}`

watch(
  () => [pending.data, settings.value?.name],
  ([res, settingsLoaded]) => {
    if (!res?.data?.length || !settingsLoaded) return
    const raw = settings.value.pending_popup_hours
    const hours = raw == null || raw === '' ? 24 : Number(raw)
    if (!hours) return
    try {
      const last = Number(localStorage.getItem(shownKey())) || 0
      if (Date.now() - last < hours * 3600 * 1000) return
      localStorage.setItem(shownKey(), String(Date.now()))
    } catch {
      // Penyimpanan diblokir: tetap tampilkan, paling buruk muncul tiap buka CRM.
    }
    open.value = true
  },
  { immediate: true },
)

const rows = computed(() => pending.data?.data || [])

function timing(r) {
  const parts = []
  if (r.due_days != null) {
    if (r.due_days < 0) parts.push(__('Lewat tenggat {0} hari', [-r.due_days]))
    else if (r.due_days === 0) parts.push(__('Tenggat hari ini'))
    else parts.push(__('Tenggat {0} hari lagi', [r.due_days]))
  }
  if (r.idle_days > 0) parts.push(__('diam {0} hari', [r.idle_days]))
  return parts.join(', ')
}

function go(r) {
  router.push({ name: r._route, params: { [r._routeParam]: r.name } })
}

function toggle() {
  open.value = !open.value
  if (open.value && mode.value === 'todo') pending.reload()
}

function openChat() {
  chatOpened.value = true
  mode.value = 'chat'
}

// Parameter route -> doctype dokumen yang sedang dibuka.
const PARAM_DOCTYPE = {
  leadId: 'CRM Lead',
  inquiryId: 'CRM Inquiry',
  quotationId: 'CRM Quotation',
  tenderId: 'CRM Tender',
  estimationId: 'CRM Estimation',
  procurementId: 'CRM Procurement',
  contactId: 'Contact',
  organizationId: 'CRM Organization',
  componentId: 'CRM Cost Component',
}

const currentDoc = computed(() => {
  for (const [param, doctype] of Object.entries(PARAM_DOCTYPE)) {
    if (route.params[param]) return { doctype, name: String(route.params[param]) }
  }
  return null
})

const context = computed(() => {
  const parts = [`User sedang membuka halaman CRM "${String(route.name)}" (${route.fullPath}).`]
  if (currentDoc.value) {
    const { doctype, name } = currentDoc.value
    parts.push(
      `Dokumen yang sedang dibuka: ${doctype} ${name}. Kalau pertanyaan menyangkut ` +
        `"ini"/"dokumen ini"/"halaman ini", baca dulu dengan crm_get_record ` +
        `(doctype "${doctype}", name "${name}") sebelum menjawab.`,
    )
  }
  if (rows.value.length) {
    // Daftar pending yang sedang dilihat user, supaya "bagaimana menyelesaikan
    // yang pertama?" langsung nyambung tanpa agent mencari ulang.
    parts.push(
      'Pekerjaan pending user (urut prioritas): ' +
        rows.value
          .slice(0, 15)
          .map((r) => `${r.name} (${r.kind}, ${r.status}, ${r.account}): ${r.action}`)
          .join('; '),
    )
  }
  return parts.join('\n')
})

const suggestions = computed(() =>
  currentDoc.value
    ? [
        __('Ringkas dokumen ini.'),
        __('Apa langkah berikutnya untuk dokumen ini?'),
        __('Ada data yang kurang di sini?'),
      ]
    : [
        __('Bagaimana cara menyelesaikan pekerjaan paling mendesak saya?'),
        __('Quotation mana yang belum dijawab customer?'),
        __('Inquiry apa yang belum dibuatkan quotation?'),
      ],
)
</script>
