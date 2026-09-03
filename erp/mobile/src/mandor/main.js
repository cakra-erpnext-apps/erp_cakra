import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { setNs } from '../api'
import { catchAll, pantauKoneksi } from '../store'
import '../style.css'
import App from './App.vue'

// Harus dipasang SEBELUM panggilan pertama: store.refresh() sudah menembak
// `csrf` dan `me` di onMounted App, dan tanpa ini keduanya jatuh ke modul sopir
// yang menolak mandor dengan pesan "tidak tertaut ke data Driver".
setNs('erp.fleet.api.mobile_mandor')

const router = createRouter({
  history: createWebHistory('/mandor'),
  // Urutan menu: Map - Driver - Dispatch. Peta jadi layar pembuka karena ia tab
  // pertama; mandor yang membuka apps biasanya menanyakan "unitnya di mana"
  // sebelum menyentuh assign.
  routes: [
    // Layar pembuka = Dispatch, bukan tab pertama. Urutan menu (Map - Driver -
    // Dispatch) ditentukan daftar TAB di App.vue, jadi tidak perlu redirect
    // sesudah login: cukup Dispatch yang memegang '/'.
    { path: '/', component: () => import('./pages/Orders.vue') },
    { path: '/map', component: () => import('./pages/Peta.vue') },
    { path: '/driver', component: () => import('./pages/Absensi.vue') },
    // `:name(.*)`, BUKAN `:name`: nomor DPO memakai garis miring
    // ("DPO/2026/00006"), dan parameter biasa hanya cocok dengan satu ruas
    // path. Tanpa ini halaman detail tidak pernah cocok dan layarnya kosong
    // tanpa satu pun pesan error.
    { path: '/dpo/:name(.*)', component: () => import('./pages/OrderDetail.vue') },
    // Route yang tidak dikenal dikembalikan ke Dispatch (termasuk tautan lama
    // ke /dispatch). Layar putih tanpa penjelasan adalah kegagalan yang paling
    // lama ketahuannya di HP.
    { path: '/:sisa(.*)', redirect: '/' },
  ],
})

const app = createApp(App)
catchAll(app)
pantauKoneksi()
app.use(router).mount('#app')
