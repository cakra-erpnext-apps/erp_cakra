<script setup>
/**
 * Peta satu Dispatch Order: titik rute bernomor + posisi truk yang mengerjakannya.
 *
 * Bentuknya sengaja meniru section Map di desk (pin bernomor, start hijau, Depo
 * ungu, Langsir biru terang, garis putus-putus berpanah antar titik) supaya
 * mandor dan orang kantor melihat gambar yang sama saat saling menelepon.
 *
 * Tile dari `/tiles/` -- proxy milik server sendiri, sama dengan monitor GPS
 * desk. Bukan CDN pihak ketiga: peta yang gagal muat di lapangan tidak pernah
 * bisa dibedakan dari sinyal yang jelek.
 */
import { onBeforeUnmount, onMounted, shallowRef, ref, watch } from 'vue'

const props = defineProps({
  route: { type: Array, default: () => [] },
  armada: { type: Array, default: () => [] },
})

const wadah = ref(null)
const pesan = ref('')
const peta = shallowRef(null)
const lapis = shallowRef([])
let ro

const WARNA = (t, i) =>
  i === 0 ? '#16a34a' : t.langsir ? '#0ea5e9' : t.jenis === 'Depo' ? '#7c3aed' : '#1d4ed8'

function bulat(teks, bg) {
  return window.L.divIcon({
    className: '',
    html: `<div style="width:24px;height:24px;border-radius:50%;background:${bg};color:#fff;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;">${teks}</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  })
}

function truk(label) {
  const tag = label
    ? `<div style="position:absolute;bottom:40px;left:50%;transform:translateX(-50%);white-space:nowrap;font-size:10px;font-weight:600;color:#111;background:rgba(255,255,255,.92);border:1px solid rgba(0,0,0,.18);border-radius:4px;padding:1px 5px;">${label}</div>`
    : ''
  return window.L.divIcon({
    className: '',
    html: `${tag}<img src="/assets/erp/images/truck.png" style="width:42px;height:42px;filter:drop-shadow(0 1px 3px rgba(0,0,0,.4));">`,
    iconSize: [42, 42],
    iconAnchor: [21, 21],
  })
}

function gambar() {
  if (!peta.value) return
  for (const m of lapis.value) m.remove()
  lapis.value = []

  const L = window.L
  const titik = props.route.filter((t) => t.latitude || t.longitude)

  titik.forEach((t, i) => {
    lapis.value.push(
      L.marker([t.latitude, t.longitude], { icon: bulat(i + 1, WARNA(t, i)) }).bindTooltip(
        `${i + 1}. ${t.titik}${t.langsir ? ' [Langsir]' : ''}`,
      ),
    )
  })

  if (titik.length > 1) {
    const garis = titik.map((t) => [t.latitude, t.longitude])
    lapis.value.push(
      L.polyline(garis, { color: '#1d4ed8', weight: 3, opacity: 0.7, dashArray: '6 8' }),
    )
    // Panah di tengah tiap ruas: tanpa arah, rute bolak-balik terlihat sama saja
    // dengan rute searah.
    for (let i = 0; i < garis.length - 1; i++) {
      const [a, b] = [garis[i], garis[i + 1]]
      const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
      const dx = (b[1] - a[1]) * Math.cos((mid[0] * Math.PI) / 180)
      const deg = (Math.atan2(dx, b[0] - a[0]) * 180) / Math.PI - 90
      lapis.value.push(
        L.marker(mid, {
          interactive: false,
          icon: L.divIcon({
            className: '',
            html: `<div style="transform:rotate(${deg.toFixed(0)}deg);color:#1d4ed8;font-size:15px;line-height:15px;">&#10148;</div>`,
            iconSize: [15, 15],
            iconAnchor: [7, 7],
          }),
        }),
      )
    }
  }

  for (const a of props.armada) {
    const label = a.vehicle + (a.driver_nama ? ` - ${a.driver_nama}` : '')
    lapis.value.push(
      L.marker([a.latitude, a.longitude], { zIndexOffset: 1000, icon: truk(label) }).bindTooltip(
        label,
      ),
    )
  }

  lapis.value.forEach((m) => m.addTo(peta.value))
  if (lapis.value.length) {
    peta.value.fitBounds(window.L.featureGroup(lapis.value).getBounds().pad(0.3))
  }
  pesan.value = titik.length || props.armada.length ? '' : 'Titik rute belum punya koordinat.'
}

onMounted(() => {
  if (!window.L) {
    pesan.value = 'Peta tidak bisa dimuat.'
    return
  }
  peta.value = window.L.map(wadah.value, { attributionControl: false }).setView([-2.5, 118], 5)
  window.L.tileLayer('/tiles/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(peta.value)
  gambar()
  // Kartu peta bisa masih 0 px saat halaman baru dirender di dalam area yang
  // digulir -- tanpa hitung ulang, tile-nya tinggal abu-abu selamanya.
  ro = new ResizeObserver(() => peta.value && peta.value.invalidateSize())
  ro.observe(wadah.value)
})

watch(() => [props.route, props.armada], gambar, { deep: true })

onBeforeUnmount(() => {
  if (ro) ro.disconnect()
  if (peta.value) peta.value.remove()
})
</script>

<template>
  <div class="grid gap-2">
    <!-- z-0: pane Leaflet punya z-index sendiri yang bisa menimpa nav bawah. -->
    <div
      ref="wadah"
      class="relative z-0 h-[45vh] w-full overflow-hidden rounded-2xl bg-slate-200 ring-1 ring-slate-900/5"
    ></div>
    <p v-if="pesan" class="text-center text-xs text-slate-400">{{ pesan }}</p>
  </div>
</template>
