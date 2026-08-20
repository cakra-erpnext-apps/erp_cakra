<template>
  <div :id="mapId" class="w-full rounded border border-outline-gray-2" :style="{ height: height }" />
</template>

<script setup>
// Peta kecil berbasis Leaflet (dependency yang sudah ada, dipakai Geolocation field).
// editable=true: klik peta / drag marker untuk set titik -> emit('update', {lat,lng}).
// editable=false: cuma tampilkan marker (read-only).
// Tiles OpenStreetMap butuh internet di device; offline -> peta abu-abu.
import leafletIconUrl from 'leaflet/dist/images/marker-icon.png?url'
import leafletIconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png?url'
import leafletShadowUrl from 'leaflet/dist/images/marker-shadow.png?url'
import { watch, onMounted, onBeforeUnmount, nextTick } from 'vue'

const props = defineProps({
  lat: { type: Number, default: null },
  lng: { type: Number, default: null },
  editable: { type: Boolean, default: false },
  zoom: { type: Number, default: 16 },
  height: { type: String, default: '260px' },
  // Deret titik rute: [{lat, lng, label}]. Kalau diisi, lat/lng/editable
  // diabaikan -- peta menggambar garis bernomor dan menyesuaikan zoom.
  points: { type: Array, default: () => [] },
  // Deret kedua, digambar putus-putus dan pudar supaya tidak bersaing dengan
  // rute utama: dipakai untuk titik Loading/Unloading. Tiap titik boleh punya
  // `text` sendiri sebagai isi pin (default: nomor urut).
  dashedPoints: { type: Array, default: () => [] },
})
const emit = defineEmits(['update'])

// id acak: beberapa MiniMap bisa mount di ms yang sama (satu per kartu absen).
const mapId = `minimap-${Math.random().toString(36).slice(2)}`

let L, map, marker, routeLayer

function pin(text, faded) {
  return L.divIcon({
    className: '',
    html:
      '<div style="background:#2563eb;color:#fff;border:2px solid #fff;border-radius:9999px;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600' +
      (faded ? ';opacity:.55' : '') +
      '">' +
      text +
      '</div>',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  })
}

function series(pts, faded) {
  const latlngs = pts.map((p) => [p.lat, p.lng])
  return [
    L.polyline(latlngs, {
      color: '#2563eb',
      weight: 3,
      opacity: faded ? 0.45 : 1,
      dashArray: faded ? '6 8' : null,
    }),
    ...pts.map((p, i) =>
      L.marker(latlngs[i], {
        icon: pin(p.text || String(i + 1), faded),
        opacity: faded ? 0.7 : 1,
      }).bindTooltip(p.label || String(i + 1)),
    ),
  ]
}

function drawRoute() {
  if (!map) return
  if (routeLayer) routeLayer.remove()
  routeLayer = null
  const ok = (p) => p.lat != null && p.lng != null
  const main = props.points.filter(ok)
  const dashed = props.dashedPoints.filter(ok)
  if (!main.length && !dashed.length) return
  routeLayer = L.layerGroup([
    ...(main.length ? series(main, false) : []),
    ...(dashed.length ? series(dashed, true) : []),
  ]).addTo(map)
  // Satu titik menghasilkan bounds tanpa luas -- tanpa maxZoom leaflet melompat
  // ke zoom maksimum dan pengguna kehilangan konteks sekitarnya.
  const all = [...main, ...dashed].map((p) => [p.lat, p.lng])
  map.fitBounds(L.latLngBounds(all).pad(0.2), { maxZoom: props.zoom })
}

function hasPoint() {
  return props.lat != null && props.lng != null && !Number.isNaN(props.lat)
}

function placeMarker(lat, lng) {
  if (marker) {
    marker.setLatLng([lat, lng])
  } else {
    marker = L.marker([lat, lng], { draggable: props.editable }).addTo(map)
    if (props.editable) marker.on('dragend', emitUpdate)
  }
}

function emitUpdate() {
  // wrap(): peta boleh digeser terus melewati batas dunia, dan titik di salinan
  // peta sebelah mengembalikan bujur seperti -261 -- letaknya sama persis tapi
  // mesin rute dan Google Maps menolaknya sebagai angka di luar batas.
  const p = marker.getLatLng().wrap()
  emit('update', { lat: p.lat, lng: p.lng })
}

async function init() {
  await import('leaflet/dist/leaflet.css')
  const mod = await import('leaflet')
  L = mod.default || mod
  // Perbaiki path gambar marker untuk Vite (sama seperti GeolocationControl).
  delete L.Icon.Default.prototype._getIconUrl
  L.Icon.Default.mergeOptions({
    iconRetinaUrl: leafletIconRetinaUrl,
    iconUrl: leafletIconUrl,
    shadowUrl: leafletShadowUrl,
  })

  const center = hasPoint() ? [props.lat, props.lng] : [-6.2, 106.816] // default Jakarta
  map = L.map(mapId, { attributionControl: false }).setView(center, hasPoint() ? props.zoom : 11)
  // CARTO Voyager: tampilan mirip Google Maps dan gratis. Tile OSM langsung sering
  // ditolak (peta blank). Sama dengan basemap di desk (erp/public/js/geo_point_form.js).
  const street = L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    {
      attribution: '&copy; OpenStreetMap, &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 20,
    },
  ).addTo(map)

  // Toggle Map/Satellite ala Google Maps. Citra Esri gratis tanpa API key, tapi
  // tidak punya nama jalan -- label Voyager ditumpuk di atasnya biar terbaca.
  const satellite = L.layerGroup([
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { attribution: '&copy; Esri', maxZoom: 19 },
    ),
    L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png',
      { subdomains: 'abcd', maxZoom: 20 },
    ),
  ])
  L.control
    .layers(
      { [__('Map')]: street, [__('Satellite')]: satellite },
      null,
      { position: 'topright' },
    )
    .addTo(map)

  const hasSeries = props.points.length || props.dashedPoints.length
  if (hasSeries) drawRoute()
  else if (hasPoint()) placeMarker(props.lat, props.lng)
  if (props.editable && !hasSeries) {
    map.on('click', (e) => {
      const p = e.latlng.wrap()
      placeMarker(p.lat, p.lng)
      emitUpdate()
    })
  }
  // Dialog/parent kadang belum punya ukuran saat init -> hitung ulang.
  nextTick(() => map.invalidateSize())
  setTimeout(() => map && map.invalidateSize(), 200)
}

// Dipakai pencarian alamat: pindahkan pin ke satu titik tanpa lewat props,
// supaya watcher lat/lng tidak ikut aktif tiap kali user nge-pin manual.
function focus(lat, lng) {
  if (!map) return
  placeMarker(lat, lng)
  map.setView([lat, lng], props.zoom)
}
defineExpose({ focus })

onMounted(() => nextTick(init))
onBeforeUnmount(() => {
  if (map) map.remove()
})

watch(() => [props.points, props.dashedPoints], drawRoute, { deep: true })

watch(
  () => [props.lat, props.lng],
  () => {
    if (map && hasPoint()) {
      placeMarker(props.lat, props.lng)
      map.setView([props.lat, props.lng], props.zoom)
    }
  },
)
</script>
