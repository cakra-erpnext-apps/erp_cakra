<script setup>
import { useRouter } from 'vue-router'
import Ikon from '../Ikon.vue'
import { keluar, state } from '../store'

const router = useRouter()
const d = state.me.driver

async function logout() {
  await keluar()
  router.replace('/')
}
</script>

<template>
  <div class="grid gap-4">
    <div class="card grid gap-4">
      <div class="flex items-center gap-3">
        <img v-if="d.image" :src="d.image" class="h-16 w-16 rounded-2xl object-cover" />
        <div
          v-else
          class="grid h-16 w-16 place-items-center rounded-2xl bg-brand-50 text-2xl font-bold text-brand-600"
        >
          {{ (d.title || '?').charAt(0) }}
        </div>
        <div class="min-w-0">
          <div class="truncate text-lg font-semibold">{{ d.title }}</div>
          <div class="text-sm text-slate-400">{{ d.code }}</div>
          <span class="chip mt-1.5 bg-slate-100 text-slate-600">{{ state.me.status }}</span>
        </div>
      </div>

      <dl class="grid gap-2 border-t border-slate-100 pt-3 text-sm">
        <div class="flex items-center justify-between gap-3">
          <dt class="text-slate-400">Cabang</dt>
          <dd class="font-medium">{{ d.branch || '-' }}</dd>
        </div>
        <div class="flex items-center justify-between gap-3">
          <dt class="text-slate-400">No. HP</dt>
          <dd class="font-medium">{{ d.phone_number || '-' }}</dd>
        </div>
      </dl>
    </div>

    <div class="grid gap-2">
      <RouterLink
        v-for="m in [
          { ikon: 'hadiah', teks: 'Reward', ke: '/reward' },
          { ikon: 'slip', teks: 'Slip Gaji', ke: '/slip-gaji' },
        ]"
        :key="m.ke"
        :to="m.ke"
        class="card flex items-center gap-3"
      >
        <span class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600">
          <Ikon :n="m.ikon" />
        </span>
        <span class="flex-1 font-medium">{{ m.teks }}</span>
        <Ikon n="lanjut" class="h-4 w-4 text-slate-300" />
      </RouterLink>
    </div>

    <button class="btn-ghost !text-red-600" @click="logout">
      <Ikon n="keluar" class="h-4 w-4" />
      Keluar
    </button>
  </div>
</template>
