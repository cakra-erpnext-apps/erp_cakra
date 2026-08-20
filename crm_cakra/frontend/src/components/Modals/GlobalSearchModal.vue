<template>
  <Dialog v-model="show" :options="{ size: 'xl' }">
    <template #body>
      <div class="flex items-center gap-2 border-b px-4 py-3">
        <FeatherIcon name="search" class="h-4 w-4 text-ink-gray-5" />
        <input
          ref="input"
          v-model="text"
          type="text"
          class="w-full border-none bg-transparent p-0 text-base text-ink-gray-8 placeholder-ink-gray-4 focus:ring-0"
          :placeholder="__('Search everything...')"
        />
        <span class="shrink-0 text-xs text-ink-gray-4">esc</span>
      </div>
      <div class="max-h-[60vh] overflow-y-auto px-2 py-2">
        <div
          v-if="search.loading"
          class="px-2 py-3 text-base text-ink-gray-5"
        >
          {{ __('Searching...') }}
        </div>
        <div
          v-else-if="text.length < 2"
          class="px-2 py-3 text-base text-ink-gray-5"
        >
          {{ __('Type at least 2 characters') }}
        </div>
        <div
          v-else-if="!search.data?.length"
          class="px-2 py-3 text-base text-ink-gray-5"
        >
          {{ __('No results found') }}
        </div>
        <div v-for="group in search.data" :key="group.doctype" class="mb-2">
          <div class="px-2 py-1 text-xs uppercase text-ink-gray-4">
            {{ group.label }}
          </div>
          <div
            v-for="item in group.items"
            :key="item.name"
            class="flex cursor-pointer items-center justify-between gap-2 rounded px-2 py-1.5 hover:bg-surface-gray-2"
            @click="open(group, item)"
          >
            <span class="truncate text-base text-ink-gray-8">
              {{ item.title }}
            </span>
            <span class="shrink-0 text-sm text-ink-gray-4">{{ item.name }}</span>
          </div>
        </div>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
import { ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Dialog, FeatherIcon, createResource } from 'frappe-ui'
import { useDebounceFn, useEventListener } from '@vueuse/core'

const show = defineModel()
const router = useRouter()
const text = ref('')
const input = ref(null)

const search = createResource({
  url: 'crm_cakra.api.doc.global_search',
  makeParams: () => ({ txt: text.value }),
})

const fetch = useDebounceFn(() => {
  if (text.value.length < 2) {
    search.data = null
    return
  }
  search.fetch()
}, 300)

watch(text, fetch)

watch(show, (value) => {
  if (!value) return
  text.value = ''
  search.data = null
  nextTick(() => input.value?.focus())
})

useEventListener(window, 'keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key?.toLowerCase() === 'k') {
    e.preventDefault()
    show.value = true
  }
})

function open(group, item) {
  show.value = false
  router.push({ name: group.route, params: { [group.param]: item.name } })
}
</script>
