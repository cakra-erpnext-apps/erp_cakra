<template>
  <div>
    <MiniMap :points="points" :dashed-points="endPoints" height="60vh" />
    <div
      v-if="!points.length && !endPoints.length"
      class="mt-2 text-sm text-ink-gray-5"
    >
      {{ __('Pilih titik rute untuk melihatnya di peta.') }}
    </div>
  </div>
</template>

<script setup>
import MiniMap from '@/components/MiniMap.vue'
import { call } from 'frappe-ui'
import { ref, watch } from 'vue'

const props = defineProps({
  // Dokumen estimasi (reaktif) -- peta ikut berubah begitu titiknya dipilih.
  data: { type: Object, required: true },
})

const ROUTE_FIELDS = ['route1', 'route2', 'route3', 'route4', 'route5', 'route6', 'route7', 'route8']
const MAP_FIELDS = [...ROUTE_FIELDS, 'loading', 'unloading']

// Koordinat titik untuk peta. Lokasi tanpa koordinat dilewati diam-diam:
// masternya boleh saja belum di-pin, dan itu bukan alasan mengosongkan peta.
//
// Loading/Unloading dipisah ke deret putus-putus: keduanya bukan bagian dari
// urutan 1..8, jadi kalau digabung nomornya jadi bohong.
const points = ref([])
const endPoints = ref([])

watch(
  () => MAP_FIELDS.map((f) => props.data?.[f] || '').join('|'),
  async (key) => {
    // Nomor pin diikat ke posisi field, bukan urutan hasil filter: Route 4 tetap
    // pin "4" walau Route 3 dikosongkan.
    const values = key.split('|')
    const entries = MAP_FIELDS.map((f, i) => ({
      name: values[i],
      end: i >= ROUTE_FIELDS.length,
      text: i < ROUTE_FIELDS.length ? String(i + 1) : f === 'loading' ? 'L' : 'U',
    })).filter((e) => e.name)
    if (!entries.length) {
      points.value = []
      endPoints.value = []
      return
    }
    const rows = await call('frappe.client.get_list', {
      doctype: 'Fleet Location',
      filters: { name: ['in', [...new Set(entries.map((e) => e.name))]] },
      fields: ['name', 'latitude', 'longitude'],
      limit_page_length: 0,
    })
    const byName = Object.fromEntries(rows.map((r) => [r.name, r]))
    const resolve = (list) =>
      list
        .map((e) => ({ row: byName[e.name], text: e.text }))
        .filter((p) => p.row?.latitude && p.row?.longitude)
        .map((p) => ({
          lat: p.row.latitude,
          lng: p.row.longitude,
          label: p.row.name,
          text: p.text,
        }))

    points.value = resolve(entries.filter((e) => !e.end))
    endPoints.value = resolve(entries.filter((e) => e.end))
  },
  { immediate: true },
)
</script>
