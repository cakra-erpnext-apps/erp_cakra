import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import { catchAll, pantauKoneksi } from './store'
import './style.css'

const router = createRouter({
  history: createWebHistory('/driver'),
  routes: [
    { path: '/', component: () => import('./pages/Home.vue') },
    { path: '/history', component: () => import('./pages/History.vue') },
    { path: '/jobs', component: () => import('./pages/Jobs.vue') },
    { path: '/jobs/:item', component: () => import('./pages/JobDetail.vue') },
    { path: '/profil', component: () => import('./pages/Profil.vue') },
    { path: '/reward', component: () => import('./pages/Reward.vue') },
    { path: '/slip-gaji', component: () => import('./pages/SlipGaji.vue') },
  ],
})

/**
 * Halaman dimuat sepotong-sepotong (`import()`), dan tiap rilis mengubah nama
 * berkas potongannya. HP yang apps-nya sudah terbuka masih memegang daftar nama
 * lama: begitu sopir pindah halaman, potongan yang dia minta sudah tidak ada di
 * server dan yang muncul adalah "Failed to fetch dynamically imported module".
 * Sekali muat ulang menyelesaikannya, jadi apps mengerjakannya sendiri.
 *
 * Dibatasi sekali per 15 detik: kalau ternyata sebabnya bukan rilis baru
 * (potongannya memang hilang), tanpa batas ini apps akan memuat ulang terus
 * menerus dan sopir tidak pernah bisa membaca error-nya.
 */
const JEDA_MUAT_ULANG = 15000
router.onError((e, to) => {
  if (!/dynamically imported module|module script failed|Failed to fetch/i.test(String(e))) return
  const kunci = 'muat-ulang-terakhir'
  const terakhir = Number(sessionStorage.getItem(kunci) || 0)
  if (Date.now() - terakhir < JEDA_MUAT_ULANG) return
  try {
    sessionStorage.setItem(kunci, String(Date.now()))
  } catch {
    // penyimpanan situs dimatikan: sekali muat ulang tetap lebih baik daripada macet
  }
  location.assign('/driver' + to.fullPath)
})

const app = createApp(App)
catchAll(app)
pantauKoneksi()
app.use(router).mount('#app')
