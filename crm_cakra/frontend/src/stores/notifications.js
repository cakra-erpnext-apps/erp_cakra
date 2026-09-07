import { defineStore } from 'pinia'
import { createResource, dayjsLocal } from 'frappe-ui'
import { computed, ref } from 'vue'

export const visible = ref(false)

export const notifications = createResource({
  url: 'crm_cakra.api.notifications.get_notifications',
  initialData: [],
  auto: true,
})

export const unreadNotificationsCount = computed(
  () => notifications.data?.filter((n) => !n.read).length || 0,
)

// Latar tombol bel makin gelap tiap HEAT_STEP_MIN menit selama notifikasi didiamkan,
// mentok di HEAT_MAX supaya labelnya tetap terbaca. Sama persis dengan rumus di desk
// (erpnext_custom/public/js/notification_badge.js) -- ubah keduanya kalau mau disetel.
const HEAT_STEP_MIN = 1
const HEAT_MAX = 7

// Dihitung dari `creation` notifikasi TERTUA, bukan dari saat tab dibuka: reload
// halaman tidak boleh mereset tekanan warnanya.
const clock = ref(Date.now())
setInterval(() => (clock.value = Date.now()), 30000)

export const notificationHeat = computed(() => {
  const unread = notifications.data?.filter((n) => !n.read) || []
  if (!unread.length) return null
  const oldest = Math.min(...unread.map((n) => dayjsLocal(n.creation).valueOf()))
  if (!isFinite(oldest)) return 'rgba(128, 128, 128, 0.02)'
  const lvl = Math.min(
    Math.floor((clock.value - oldest) / 60000 / HEAT_STEP_MIN),
    HEAT_MAX,
  )
  // rgba, bukan warna solid: satu rumus ikut benar di tema terang maupun gelap.
  return `rgba(128, 128, 128, ${(0.02 + lvl * 0.009).toFixed(3)})`
})

export const notificationsStore = defineStore('crm-notifications', () => {
  const mark_as_read = createResource({
    url: 'crm_cakra.api.notifications.mark_as_read',
    onSuccess: () => {
      mark_as_read.params = {}
      notifications.reload()
    },
  })

  function toggle() {
    visible.value = !visible.value
  }

  function mark_doc_as_read(doc) {
    mark_as_read.params = { doc: doc }
    mark_as_read.reload()
    toggle()
  }

  return {
    unreadNotificationsCount,
    notificationHeat,
    mark_as_read,
    mark_doc_as_read,
    toggle,
  }
})
