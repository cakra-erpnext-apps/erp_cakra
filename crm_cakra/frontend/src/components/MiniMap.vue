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
})
const emit = defineEmits(['update'])

// id acak: beberapa MiniMap bisa mount di ms yang sama (satu per kartu absen).
const mapId = `minimap-${Math.random().toString(36).slice(2)}`

let L, map, marker

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
  const p = marker.getLatLng()
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
  map = L.map(mapId).setView(center, hasPoint() ? props.zoom : 11)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap',
    maxZoom: 19,
  }).addTo(map)

  if (hasPoint()) placeMarker(props.lat, props.lng)
  if (props.editable) {
    map.on('click', (e) => {
      placeMarker(e.latlng.lat, e.latlng.lng)
      emitUpdate()
    })
  }
  // Dialog/parent kadang belum punya ukuran saat init -> hitung ulang.
  nextTick(() => map.invalidateSize())
  setTimeout(() => map && map.invalidateSize(), 200)
}

onMounted(() => nextTick(init))
onBeforeUnmount(() => {
  if (map) map.remove()
})

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
