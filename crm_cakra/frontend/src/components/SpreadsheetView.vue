<template>
  <div class="flex min-h-0 flex-col">
    <!-- Toolbar -->
    <div class="flex h-[45px] shrink-0 items-center gap-3 border-b px-4">
      <div class="min-w-0 flex-1">
        <div class="truncate text-base font-medium text-ink-gray-8">
          {{ data?.file_name || label }}
        </div>
        <div v-if="data" class="truncate text-sm text-ink-gray-5">
          {{ data.rows }} x {{ data.cols }}
          <span v-if="data.truncated"> ({{ __('dipotong') }})</span>
          <span v-if="editCount" class="text-ink-amber-3">
            {{ __('{0} sel belum disimpan', [editCount]) }}
          </span>
        </div>
      </div>

      <slot name="actions" />
      <Button
        :label="__('Riwayat')"
        :variant="showHistory ? 'subtle' : 'ghost'"
        @click="toggleHistory"
      />
      <a v-if="data?.file_url" :href="data.file_url" download>
        <Button :tooltip="__('Download')" icon="download" variant="ghost" />
      </a>
      <Button
        :label="__('Save')"
        variant="solid"
        :disabled="!editCount"
        :loading="saving"
        @click="saveChanges"
      />
    </div>

    <!-- Bilah sel aktif, gaya formula bar Excel -->
    <div
      v-if="data"
      class="flex h-8 shrink-0 items-center gap-2 border-b bg-surface-gray-1 px-2 text-base"
    >
      <span
        class="w-16 shrink-0 rounded border bg-surface-white px-1.5 py-0.5 text-center font-medium text-ink-gray-7"
      >
        {{ activeAddress || '—' }}
      </span>
      <span class="truncate text-ink-gray-6">{{ activeContent }}</span>
    </div>

    <!-- Tab sheet -->
    <div
      v-if="data?.sheets?.length > 1"
      class="flex shrink-0 gap-1 overflow-x-auto border-b px-3 py-1.5"
    >
      <Button
        v-for="s in data.sheets"
        :key="s"
        :label="s"
        size="sm"
        :variant="s === data.sheet ? 'subtle' : 'ghost'"
        @click="switchSheet(s)"
      />
    </div>

    <div class="flex min-h-0 flex-1">
      <div
        class="min-w-0 flex-1 overflow-auto"
        :style="maxHeight === 'none' ? null : { maxHeight }"
      >
        <div v-if="loading" class="p-8 text-center text-ink-gray-5">
          {{ __('Loading') }}...
        </div>
        <table
          v-else-if="data"
          class="border-collapse text-base"
          style="table-layout: fixed"
        >
          <colgroup>
            <col style="width: 46px" />
            <col
              v-for="(w, i) in data.widths"
              :key="i"
              :style="{
                width: (data.hidden_cols.includes(i + 1) ? 0 : w) + 'px',
              }"
            />
          </colgroup>
          <thead>
            <tr>
              <th
                class="sticky left-0 top-0 z-30 border border-outline-gray-2 bg-surface-gray-3"
              />
              <th
                v-for="(w, i) in data.widths"
                :key="i"
                class="sticky top-0 z-20 border border-outline-gray-2 text-sm font-normal"
                :class="
                  active.c === i + 1
                    ? 'bg-surface-gray-4 text-ink-gray-8'
                    : 'bg-surface-gray-2 text-ink-gray-5'
                "
              >
                {{ colLabel(i + 1) }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, ri) in data.cells"
              :key="ri"
              :style="{ height: data.heights[ri] + 'px' }"
            >
              <td
                class="sticky left-0 z-10 select-none border border-outline-gray-2 text-center text-sm"
                :class="
                  active.r === ri + 1
                    ? 'bg-surface-gray-4 text-ink-gray-8'
                    : 'bg-surface-gray-2 text-ink-gray-5'
                "
              >
                {{ ri + 1 }}
              </td>
              <template v-for="(cell, ci) in row" :key="ci">
                <td
                  v-if="cell !== 0"
                  contenteditable="plaintext-only"
                  spellcheck="false"
                  class="border border-outline-gray-2 px-1 outline-none"
                  :class="[
                    edits[key(ri + 1, ci + 1)] !== undefined
                      ? '!bg-surface-amber-2'
                      : '',
                    active.r === ri + 1 && active.c === ci + 1
                      ? 'relative z-10 ring-2 ring-inset ring-outline-gray-4'
                      : '',
                  ]"
                  :style="styleOf(cell)"
                  :title="cell?.f || ''"
                  :rowspan="span(ri + 1, ci + 1)?.rs"
                  :colspan="span(ri + 1, ci + 1)?.cs"
                  @focus="active = { r: ri + 1, c: ci + 1 }"
                  @input="onInput($event, ri + 1, ci + 1)"
                >{{ cell?.v || '' }}</td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Riwayat: siapa mengubah sel apa, dari nilai berapa jadi berapa -->
      <aside
        v-if="showHistory"
        class="flex w-72 shrink-0 flex-col overflow-y-auto border-l"
      >
        <div
          class="sticky top-0 z-10 border-b bg-surface-white px-4 py-2 text-base font-medium text-ink-gray-8"
        >
          {{ __('Riwayat perubahan') }}
        </div>
        <div v-if="historyRes.loading" class="p-4 text-sm text-ink-gray-5">
          {{ __('Loading') }}...
        </div>
        <div
          v-else-if="!historyRes.data?.length"
          class="p-4 text-sm text-ink-gray-5"
        >
          {{ __('Belum ada yang mengubah berkas ini dari sini.') }}
        </div>
        <div
          v-for="b in historyRes.data || []"
          :key="b.batch"
          class="border-b px-4 py-3"
        >
          <div class="flex items-baseline justify-between gap-2">
            <span class="truncate text-base text-ink-gray-8">
              {{ b.owner_name }}
            </span>
            <Tooltip :text="formatDate(b.creation)">
              <span class="shrink-0 text-sm text-ink-gray-5">
                {{ __(timeAgo(b.creation)) }}
              </span>
            </Tooltip>
          </div>
          <div class="mt-0.5 text-sm text-ink-gray-5">
            {{ b.sheet }} · {{ __('{0} sel', [b.cells.length]) }}
          </div>
          <div class="mt-2 space-y-1">
            <div
              v-for="(c, i) in b.cells"
              :key="i"
              class="flex gap-1.5 text-sm"
            >
              <span class="shrink-0 font-medium text-ink-gray-7">
                {{ c.cell }}
              </span>
              <span class="truncate text-ink-gray-5 line-through">
                {{ c.old || __('kosong') }}
              </span>
              <span class="text-ink-gray-4">&rarr;</span>
              <span class="truncate text-ink-gray-8">
                {{ c.new || __('kosong') }}
              </span>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Button, Tooltip, call, createResource, toast } from 'frappe-ui'
import { formatDate, timeAgo } from '@/utils'

const props = defineProps({
  fileName: { type: String, required: true },
  label: { type: String, default: '' },
  maxHeight: { type: String, default: '70vh' },
})

const emit = defineEmits(['saved', 'error'])

const data = ref(null)
const loading = ref(false)
const saving = ref(false)
const showHistory = ref(false)
const active = ref({ r: 0, c: 0 })
const edits = reactive({})

const editCount = computed(() => Object.keys(edits).length)
const key = (r, c) => `${r}:${c}`

const merges = computed(() => {
  const m = {}
  for (const x of data.value?.merges || []) m[key(x.r, x.c)] = x
  return m
})
const span = (r, c) => merges.value[key(r, c)]

const activeAddress = computed(() =>
  active.value.r ? colLabel(active.value.c) + active.value.r : '',
)
const activeContent = computed(() => {
  const { r, c } = active.value
  if (!r) return ''
  const cell = data.value?.cells?.[r - 1]?.[c - 1]
  return edits[key(r, c)] ?? cell?.f ?? cell?.v ?? ''
})

function colLabel(n) {
  let s = ''
  while (n > 0) {
    const rem = (n - 1) % 26
    s = String.fromCharCode(65 + rem) + s
    n = Math.floor((n - rem) / 26)
  }
  return s
}

function styleOf(cell) {
  const s = cell?.s || {}
  const st = {
    fontWeight: s.b ? '600' : null,
    fontStyle: s.i ? 'italic' : null,
    textDecoration: s.u ? 'underline' : null,
    fontSize: s.sz ? s.sz + 'px' : null,
    fontFamily: s.ff || null,
    color: s.c || null,
    backgroundColor: s.bg || null,
    textAlign: s.ha || null,
    verticalAlign: s.va === 'center' ? 'middle' : s.va || 'bottom',
    whiteSpace: s.w ? 'pre-wrap' : 'nowrap',
    overflow: s.w ? null : 'hidden',
  }
  for (const [side, color] of Object.entries(s.bd || {})) {
    st['border' + side[0].toUpperCase() + side.slice(1)] = `1px solid ${color}`
  }
  return st
}

function onInput(e, r, c) {
  edits[key(r, c)] = e.target.innerText.replace(/\n$/, '')
}

function clearEdits() {
  for (const k of Object.keys(edits)) delete edits[k]
}

const historyRes = createResource({
  url: 'crm_cakra.api.spreadsheet.history',
  makeParams: () => ({ file_name: props.fileName }),
})

function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value) historyRes.fetch()
}

async function load(sheet) {
  loading.value = true
  try {
    data.value = await call('crm_cakra.api.spreadsheet.read', {
      file_name: props.fileName,
      sheet,
    })
  } catch (err) {
    toast.error(err.messages?.[0] || err.message || __('Gagal membuka file'))
    emit('error', err)
  }
  loading.value = false
}

async function switchSheet(sheet) {
  if (sheet === data.value?.sheet) return
  if (
    editCount.value &&
    !confirm(__('Perubahan yang belum disimpan akan hilang. Lanjut?'))
  )
    return
  clearEdits()
  active.value = { r: 0, c: 0 }
  await load(sheet)
}

async function saveChanges() {
  saving.value = true
  try {
    const changes = Object.entries(edits).map(([k, v]) => {
      const [r, c] = k.split(':')
      return { r: Number(r), c: Number(c), v }
    })
    data.value = await call('crm_cakra.api.spreadsheet.save', {
      file_name: props.fileName,
      sheet: data.value.sheet,
      changes,
    })
    clearEdits()
    if (showHistory.value) historyRes.reload()
    toast.success(__('Tersimpan ke file lampiran'))
    emit('saved', data.value)
  } catch (err) {
    toast.error(err.messages?.[0] || err.message || __('Gagal menyimpan'))
  }
  saving.value = false
}

watch(
  () => props.fileName,
  (f) => {
    clearEdits()
    active.value = { r: 0, c: 0 }
    data.value = null
    if (f) load()
  },
  { immediate: true },
)

defineExpose({ editCount, reload: () => load(data.value?.sheet) })
</script>
