import { computed, ref } from 'vue'

export const mobileSidebarOpened = ref(false)

export const isMobileView = computed(() => window.innerWidth < 768)

// HP sungguhan: layar sempit DAN penunjuknya kasar (sentuh). Kalau cuma lebar yang
// dilihat, user desktop yang mengecilkan jendela ikut kena; kalau cuma sentuh,
// laptop layar sentuh ikut kena.
export const isHandheld = () =>
  window.matchMedia?.('(pointer: coarse)').matches && window.innerWidth < 768

// Sedang berada di apps mobile (/crm/mobile). Di HP nyala sejak awal; di layar
// lebar baru nyala begitu masuk /crm/mobile, dan dimatikan lewat "Tampilan
// desktop" di menu More. Sengaja TIDAK disimpan ke localStorage: kalau tidak,
// satu kali iseng buka /crm/mobile dari laptop bikin CRM-nya mobile selamanya.
export const mobileApp = ref(isHandheld())

export const showSettings = ref(false)

export const disableSettingModalOutsideClick = ref(false)

export const activeSettingsPage = ref('')
