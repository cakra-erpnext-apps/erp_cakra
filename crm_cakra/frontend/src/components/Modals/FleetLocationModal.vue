<template>
  <Dialog v-model="show" :options="{ title: __('New Location'), size: '2xl' }">
    <template #body-content>
      <div class="flex flex-col gap-4">
        <div class="grid grid-cols-2 gap-3">
          <FormControl
            ref="nameInput"
            v-model="doc.code"
            :label="__('Name')"
            :placeholder="__('Nama lokasi, mis. PORT BELAWAN')"
          />
          <FormControl
            v-model.number="doc.radius_km"
            type="number"
            :label="__('Radius (KM)')"
          />
        </div>

        <!-- Cari alamat: lebih cepat dan lebih akurat daripada menggeser peta
             manual dari zoom seluruh Indonesia. -->
        <div class="relative">
          <FormControl
            v-model="query"
            :label="__('Cari Alamat')"
            :placeholder="__('mis. Pelabuhan Belawan, Medan')"
            autocomplete="off"
            @focus="open = true"
            @keydown.esc="open = false"
          />
          <div
            v-if="open && query.trim().length >= 3"
            class="absolute z-10 mt-1 w-full overflow-hidden rounded border border-outline-gray-2 bg-surface-white shadow-lg"
          >
            <div v-if="searching" class="px-3 py-2 text-sm text-ink-gray-5">
              {{ __('Mencari...') }}
            </div>
            <div
              v-else-if="!results.length"
              class="px-3 py-2 text-sm text-ink-gray-5"
            >
              {{ __('Alamat tidak ditemukan') }}
            </div>
            <button
              v-for="(r, i) in results"
              v-else
              :key="i"
              type="button"
              class="block w-full px-3 py-2 text-left hover:bg-surface-gray-2"
              @click="pick(r)"
            >
              <div class="text-sm text-ink-gray-8">{{ r.label }}</div>
              <div v-if="r.detail" class="truncate text-xs text-ink-gray-5">
                {{ r.detail }}
              </div>
            </button>
          </div>
        </div>

        <FormControl
          v-model="doc.alamat"
          type="textarea"
          :rows="2"
          :label="__('Alamat')"
        />

        <div>
          <div class="mb-1.5 flex items-baseline justify-between">
            <span class="text-xs text-ink-gray-5">
              {{ __('Klik peta untuk menaruh pin') }}
            </span>
            <span class="text-xs text-ink-gray-5">
              {{ __('Route') }}: {{ __('otomatis') }}
            </span>
          </div>
          <!-- lat/lng sengaja tidak di-bind balik: MiniMap sudah memindahkan
               markernya sendiri saat diklik, dan watcher-nya akan zoom ke 16
               tiap koordinat berubah -- petanya jadi melompat tiap nge-pin. -->
          <MiniMap ref="map" editable height="320px" @update="onPin" />
        </div>

        <!-- Read-only: koordinat hanya datang dari pin di peta. -->
        <div class="grid grid-cols-2 gap-3">
          <FormControl
            :modelValue="doc.latitude ?? ''"
            :label="__('Latitude')"
            disabled
            :placeholder="__('belum di-pin')"
          />
          <FormControl
            :modelValue="doc.longitude ?? ''"
            :label="__('Longitude')"
            disabled
            :placeholder="__('belum di-pin')"
          />
        </div>

        <ErrorMessage :message="error" />
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="show = false" />
        <Button
          variant="solid"
          :label="__('Create')"
          :loading="loading"
          @click="create"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
// Fleet Location yang dibuat dari CRM: selalu untuk rute (is_route dikunci 1),
// dan koordinatnya diambil dari pin di peta -- bukan diketik. Modal generik
// CreateDocumentModal tidak dipakai karena cuma merender field, tanpa peta.
import MiniMap from '@/components/MiniMap.vue'
import { Dialog, FormControl, Button, ErrorMessage, call } from 'frappe-ui'
import { watchDebounced } from '@vueuse/core'
import { ref, watch } from 'vue'

const props = defineProps({
  prefill: { type: String, default: '' },
  callback: { type: Function, default: null },
})

const show = defineModel({ type: Boolean })

const loading = ref(false)
const error = ref('')
const doc = ref(blank())

const map = ref(null)
const query = ref('')
const results = ref([])
const searching = ref(false)
const open = ref(false)
let skipSearch = false

function blank() {
  return {
    code: props.prefill || '',
    alamat: '',
    radius_km: 1,
    latitude: null,
    longitude: null,
  }
}

watch(show, (isOpen) => {
  if (isOpen) {
    doc.value = blank()
    error.value = ''
    query.value = ''
    results.value = []
    open.value = false
  }
})

// 600ms: Nominatim minta jangan dihujani, dan satu permintaan per jeda mengetik
// sudah cukup terasa instan. Hasil per kata kunci di-cache di server.
watchDebounced(
  query,
  async (q) => {
    // Memilih saran ikut menulis ulang kotak carinya; jangan cari lagi untuk
    // alamat yang barusan dipilih -- itu permintaan terbuang ke Nominatim.
    if (skipSearch) {
      skipSearch = false
      return
    }
    if ((q || '').trim().length < 3) {
      results.value = []
      return
    }
    searching.value = true
    try {
      results.value = await call('erp.fleet.geocode.search_address', { q })
    } catch (e) {
      results.value = []
      console.error('[Fleet Location] pencarian alamat gagal:', e)
    } finally {
      searching.value = false
    }
  },
  { debounce: 600 },
)

function pick(r) {
  doc.value.alamat = r.address
  doc.value.latitude = r.lat
  doc.value.longitude = r.lon
  // Nama lokasi tetap milik user -- alamat OSM cuma jadi usulan awal kalau kosong.
  if (!doc.value.code?.trim()) doc.value.code = r.label
  map.value?.focus(r.lat, r.lon)
  skipSearch = true
  query.value = r.label
  open.value = false
}

function onPin({ lat, lng }) {
  doc.value.latitude = Number(lat.toFixed(6))
  doc.value.longitude = Number(lng.toFixed(6))
}

async function create() {
  if (!doc.value.code?.trim()) {
    error.value = __('Nama lokasi wajib diisi.')
    return
  }
  loading.value = true
  error.value = ''
  try {
    const d = await call('frappe.client.insert', {
      doc: {
        doctype: 'Fleet Location',
        ...doc.value,
        code: doc.value.code.trim(),
        // Lokasi dari CRM dipakai sebagai titik rute quotation.
        is_route: 1,
      },
    })
    show.value = false
    props.callback?.(d)
  } catch (e) {
    error.value = e.messages?.[0] || e.message || __('Gagal membuat lokasi')
  } finally {
    loading.value = false
  }
}
</script>
