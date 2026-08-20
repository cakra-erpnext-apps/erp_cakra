<template>
  <Teleport v-if="showHeader" to="#app-header">
    <slot>
      <header
        class="flex h-10.5 items-center justify-between py-[7px] sm:pl-5 pl-2"
      >
        <div class="flex items-center gap-2">
          <Button
            v-if="canGoBack"
            variant="ghost"
            icon="arrow-left"
            :label="__('Back')"
            @click="router.back()"
          />
          <Button
            v-if="canGoForward"
            variant="ghost"
            icon="arrow-right"
            :label="__('Forward')"
            @click="router.forward()"
          />
          <slot name="left-header" />
        </div>
        <div class="flex items-center gap-2">
          <slot name="right-header" class="flex items-center gap-2" />
        </div>
      </header>
    </slot>
  </Teleport>
</template>
<script setup>
import { ref, computed, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const showHeader = ref(false)
const route = useRoute()
const router = useRouter()

// vue-router keeps back/forward in history.state; null = nothing to go to
const canGoBack = computed(() => route.fullPath && !!window.history.state?.back)
const canGoForward = computed(() => route.fullPath && !!window.history.state?.forward)

nextTick(() => {
  showHeader.value = true
})
</script>
