<template>
  <div class="flex flex-col gap-4">
    <div
      v-for="p in products"
      :key="p.cost_key || p.name"
      class="rounded-lg border border-outline-gray-2"
    >
      <!-- Kepala kartu: produk + ringkasan hasil hitungan -->
      <div
        class="flex items-center gap-3 px-4 py-3"
        :class="canSeeCosting ? 'cursor-pointer hover:bg-surface-gray-1' : ''"
        @click="canSeeCosting && toggle(p)"
      >
        <LucideChevronRight
          v-if="canSeeCosting"
          class="size-4 shrink-0 text-ink-gray-5 transition-transform"
          :class="isOpen(p) ? 'rotate-90' : ''"
        />
        <div class="min-w-0 flex-1">
          <div class="truncate text-base font-medium text-ink-gray-9">
            {{ productLabel(p) }}
          </div>
          <div class="text-sm text-ink-gray-5">
            {{ __('Qty') }} {{ p.qty || 0 }} {{ p.uom || '' }} &middot;
            {{ __('Duration') }} {{ p.duration || 1 }} {{ __('day') }} &middot;
            {{ __('Margin') }} {{ p.margin_percent || 0 }}% = {{ money(shown(p).margin) }}
          </div>
        </div>
        <div class="shrink-0 text-right">
          <div class="text-sm text-ink-gray-5">{{ __('Base Price') }}</div>
          <div class="text-base font-medium text-ink-gray-9">
            {{ money(shown(p).base) }}
          </div>
        </div>
      </div>

      <div
        v-if="isOpen(p) && canSeeCosting"
        class="border-t border-outline-gray-2 px-4 py-3"
      >
        <!-- Fixed cost: cerminan komponen bertipe Fixed di master produk -->
        <div class="mb-4">
          <div class="mb-1 flex items-baseline justify-between">
            <div class="text-sm font-medium text-ink-gray-7">
              {{ __('Fixed Cost') }}
              <span class="font-normal text-ink-gray-5">
                ({{ money(fixedPerDay(p)) }} / {{ __('day') }} &times;
                {{ p.duration || 1 }})
              </span>
            </div>
            <div class="text-base text-ink-gray-9">
              {{ money(calc(p).fixed) }}
            </div>
          </div>
          <!-- Read-only: angkanya milik master produk. Kolomnya sengaja sama
               dengan tabel Variable Cost supaya kedua blok kebaca sebaris. -->
          <div v-if="fixedItems(p).length" class="overflow-x-auto rounded border border-outline-gray-2">
            <table class="w-full min-w-[780px] table-fixed text-base">
              <thead>
                <tr class="border-b border-outline-gray-2 bg-surface-gray-1 text-sm text-ink-gray-5">
                  <th class="px-2 py-1.5 text-left font-normal">{{ __('Item') }}</th>
                  <th class="w-40 px-2 py-1.5 text-left font-normal">{{ __('Component') }}</th>
                  <th class="w-20 px-2 py-1.5 text-right font-normal">{{ __('Qty') }}</th>
                  <th class="w-24 px-2 py-1.5 text-left font-normal">{{ __('UOM') }}</th>
                  <th class="w-36 px-2 py-1.5 text-right font-normal">{{ __('Rate') }}</th>
                  <th class="w-36 px-2 py-1.5 text-right font-normal">{{ __('Amount') }}</th>
                  <th class="w-10"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(f, i) in fixedItems(p)" :key="i"
                  class="border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1">
                  <td class="truncate px-2 py-1.5">{{ f.item_name }}</td>
                  <td class="truncate px-2 py-1.5 text-sm text-ink-gray-5">
                    {{ f.source_component || '-' }}
                  </td>
                  <td class="px-2 py-1.5 text-right tabular-nums">{{ f.qty }}</td>
                  <td class="truncate px-2 py-1.5">{{ f.uom || '-' }}</td>
                  <td class="px-2 py-1.5 text-right tabular-nums">{{ money(f.rate) }}</td>
                  <td class="px-2 py-1.5 text-right tabular-nums text-ink-gray-9">
                    {{ money(f.amount) }}
                  </td>
                  <td></td>
                </tr>
              </tbody>
              <tfoot>
                <tr class="border-t border-outline-gray-2 bg-surface-gray-1 font-medium text-ink-gray-9">
                  <td colspan="5" class="px-2 py-1.5 text-right text-sm text-ink-gray-7">
                    {{ __('Fixed Cost') }} / {{ __('day') }}
                  </td>
                  <td class="px-2 py-1.5 text-right tabular-nums">{{ money(fixedPerDay(p)) }}</td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>
          <div v-else class="text-sm text-ink-gray-5">
            {{ __('Produk ini belum memanggil komponen Fixed Cost. Atur di master Products.') }}
          </div>
        </div>

        <!-- Variable cost: default produk sudah terisi, Procurement tinggal
             menyesuaikan angkanya atau menambah komponen lain. -->
        <div class="mb-1 flex items-center justify-between">
          <div class="text-sm font-medium text-ink-gray-7">{{ __('Variable Cost') }}</div>
          <div class="flex gap-2">
            <Button
              v-if="variableDefaults(p).length"
              :label="__('Load Defaults')"
              :iconLeft="LucideRotateCcw"
              @click="loadDefaults(p)"
            />
            <Button :label="__('Add Component')" :iconLeft="LucidePlus" @click="addLine(p)" />
          </div>
        </div>
        <!-- table-fixed + min-w: lebar kolom tetap, kolom sempit tidak ikut
             menciut waktu panel dipersempit; sisanya digeser lewat scroll. -->
        <div class="overflow-x-auto rounded border border-outline-gray-2">
        <table class="w-full min-w-[780px] table-fixed text-base">
          <thead>
            <tr class="border-b border-outline-gray-2 bg-surface-gray-1 text-sm text-ink-gray-5">
              <th class="px-2 py-1.5 text-left font-normal">{{ __('Item') }}</th>
              <th class="w-40 px-2 py-1.5 text-left font-normal">{{ __('Component') }}</th>
              <th class="w-20 px-2 py-1.5 text-right font-normal">{{ __('Qty') }}</th>
              <th class="w-24 px-2 py-1.5 text-left font-normal">{{ __('UOM') }}</th>
              <th class="w-36 px-2 py-1.5 text-right font-normal">{{ __('Rate') }}</th>
              <th class="w-36 px-2 py-1.5 text-right font-normal">{{ __('Amount') }}</th>
              <th class="w-10"></th>
            </tr>
          </thead>
          <tbody>
            <!-- Sel yang bisa diketik dikasih border waktu hover/fokus supaya
                 kelihatan mana yang bisa diubah tanpa bikin tabel penuh kotak. -->
            <tr v-for="(c, i) in linesOf(p)" :key="i"
              class="border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1">
              <td class="px-1 py-1">
                <input v-model="c.item_name" :class="cellInput"
                  :placeholder="__('BBM, tol, uang jalan...')" />
              </td>
              <td class="truncate px-2 py-1 text-sm text-ink-gray-5">
                {{ c.source_component || '-' }}
              </td>
              <td class="px-1 py-1">
                <input v-model.number="c.qty" type="number" :class="[cellInput, 'text-right']" />
              </td>
              <td class="px-1 py-1">
                <input v-model="c.uom" :class="cellInput" />
              </td>
              <td class="px-1 py-1">
                <input v-model.number="c.rate" type="number" :class="[cellInput, 'text-right']" />
              </td>
              <td class="px-2 py-1 text-right tabular-nums text-ink-gray-9">
                {{ money((c.qty || 0) * (c.rate || 0)) }}
              </td>
              <td class="px-2 py-1 text-right">
                <button class="text-ink-gray-4 hover:text-ink-red-3" @click="removeLine(c)">
                  <LucideX class="size-4" />
                </button>
              </td>
            </tr>
            <tr v-if="!linesOf(p).length">
              <td colspan="7" class="px-2 py-2 text-sm text-ink-gray-5">
                {{ __('Belum ada komponen biaya variabel.') }}
              </td>
            </tr>
          </tbody>
          <tfoot v-if="linesOf(p).length">
            <tr class="border-t border-outline-gray-2 bg-surface-gray-1 font-medium text-ink-gray-9">
              <td colspan="5" class="px-2 py-1.5 text-right text-sm text-ink-gray-7">
                {{ __('Variable Cost') }} / {{ __('day') }}
              </td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ money(calc(p).variablePerDay) }}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>
        </div>

        <!-- Rekap -->
        <div class="mt-4 flex flex-col gap-1 border-t border-outline-gray-2 pt-3 text-base">
          <div class="flex justify-between text-ink-gray-7">
            <span>{{ __('Fixed Cost') }}</span><span>{{ money(calc(p).fixed) }}</span>
          </div>
          <div class="flex justify-between text-ink-gray-7">
            <span>{{ __('Variable Cost') }}
              <span class="text-ink-gray-5">({{ money(calc(p).variablePerDay) }} / {{ __('day') }} &times;
                {{ p.duration || 1 }})</span>
            </span>
            <span>{{ money(calc(p).variable) }}</span>
          </div>
          <div class="flex items-center justify-between text-ink-gray-7">
            <span class="flex items-center gap-2">
              {{ __('Margin') }}
              <input v-model.number="p.margin_percent" type="number"
                class="w-16 rounded border border-outline-gray-2 px-1 text-right" />%
            </span>
            <span>{{ money(calc(p).margin) }}</span>
          </div>
          <div class="flex justify-between font-medium text-ink-gray-9">
            <span>{{ __('Base Price') }}</span><span>{{ money(calc(p).base) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="!products.length" class="text-base text-ink-gray-5">
      {{ __('Belum ada produk di quotation ini.') }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { createResource, Button } from 'frappe-ui'
import { usersStore } from '@/stores/users'
import LucideChevronRight from '~icons/lucide/chevron-right'
import LucidePlus from '~icons/lucide/plus'
import LucideRotateCcw from '~icons/lucide/rotate-ccw'
import LucideX from '~icons/lucide/x'

const props = defineProps({
  doc: { type: Object, required: true },
  quotationId: { type: String, required: true },
})

const products = computed(() => props.doc.products || [])

// Rincian Fixed/Variable cost dikunci role "Procurement Costing" (System Manager
// ikut lewat). Tanpa role, kartu costing tinggal ringkasannya saja -- tidak bisa
// dibuka, dan get_cost_defaults di server memang tidak mengirim rinciannya.
const { getUser } = usersStore()
const canSeeCosting = computed(() => {
  const roles = getUser().roles || []
  return roles.includes('Procurement Costing') || roles.includes('System Manager')
})
const opened = ref(new Set())

const cellInput =
  'h-7 w-full rounded border border-transparent bg-transparent px-1.5 outline-none ' +
  'hover:border-outline-gray-2 focus:border-outline-gray-3 focus:bg-surface-white'

// Default komponen milik master produk. Yang Fixed cuma ditampilkan, yang
// Variable dimuat ke cost_items -- otomatis oleh watcher di bawah, dan bisa
// dipanggil ulang lewat tombol "Load Defaults" kalau barisnya terlanjur dihapus.
const productCodes = computed(() =>
  products.value.map((p) => p.product_code).filter(Boolean),
)

// Dikirim per produk yang sedang di layar (bukan dibaca server dari tabel):
// produk yang baru dipilih dan belum di-save pun langsung dapat komponennya.
// Tanpa cache key -- isinya berubah tiap kali produk quotation berubah.
const defaults = createResource({
  url: 'crm_cakra.api.procurement.get_cost_defaults',
  makeParams: () => ({
    quotation: props.quotationId,
    codes: JSON.stringify(productCodes.value),
  }),
  auto: true,
})

watch(
  () => productCodes.value.join(','),
  () => defaults.fetch(),
)

// Auto-load: komponen Variable Cost dimuat begitu defaultnya sampai, tanpa harus
// klik "Load Defaults" atau save dulu. Penandanya cost_seeded, sama dengan yang
// dipakai seed_cost_defaults() di server -- jadi jalan sekali per produk: baris
// yang sengaja dihapus Procurement tidak muncul lagi, dan waktu produknya
// diganti, biaya produk lama dibuang dulu. Save nanti tidak menyeed ulang.
watch(
  () => [defaults.data, productCodes.value.join(',')],
  () => {
    if (!defaults.data) return
    products.value.forEach((p) => {
      if (!p.product_code || p.cost_seeded === p.product_code) return
      if (!defaults.data[p.product_code]) return
      if (p.cost_seeded) {
        props.doc.cost_items = (props.doc.cost_items || []).filter(
          (c) => c.cost_key !== key(p),
        )
      }
      p.cost_seeded = p.product_code
      loadDefaults(p)
    })
  },
  { immediate: true },
)

// Base Price (procurement_price) di grid ikut bergerak begitu Duration, Margin,
// atau komponen biaya disentuh. Rumusnya sama dengan calculate_costing() di
// server -- server tetap menghitung ulang saat save; ini cuma supaya kolomnya
// tidak diam sampai orang menekan Save dan menebak-nebak apakah isiannya kena.
//
// Ditulis hanya kalau angkanya benar-benar berubah: menimpa dengan nilai yang
// sama membuat dokumen tampak "Not Saved" cuma karena tab Procurement dibuka.
function setNum(row, field, value) {
  if ((row[field] || 0) !== value) row[field] = value
}

watch(
  () => products.value.map((p) => calc(p)),
  (all) => {
    // Tanpa akses costing, defaults.data kosong -> fixedPerDay 0. Menulis hasil
    // hitungan dari data yang tidak lengkap akan menurunkan Base Price yang sudah
    // benar, jadi baris produknya tidak disentuh sama sekali.
    if (!canSeeCosting.value) return
    products.value.forEach((p, i) => {
      const c = all[i]
      setNum(p, 'fixed_cost', c.fixed)
      setNum(p, 'variable_cost', c.variable)
      // Baris tanpa data biaya sama sekali TIDAK disentuh: harga ribuan quotation
      // lama diketik manual, jangan dinolkan engine ini (sama seperti di server).
      if (!fixedPerDay(p) && !c.variablePerDay) {
        setNum(p, 'margin_amount', 0)
        return
      }
      setNum(p, 'margin_amount', c.margin)
      setNum(p, 'procurement_price', c.base)
    })
  },
  { immediate: true },
)

function isOpen(p) {
  return opened.value.has(key(p))
}
function toggle(p) {
  const k = key(p)
  opened.value.has(k) ? opened.value.delete(k) : opened.value.add(k)
  opened.value = new Set(opened.value)
}

// cost_key normalnya dibuat server saat save. Untuk baris yang belum pernah
// disimpan, dibuat di sini supaya biayanya sudah menempel sebelum save pertama.
function key(p) {
  if (!p.cost_key) p.cost_key = 'ck' + Math.random().toString(36).slice(2, 12)
  return p.cost_key
}

function defaultsOf(p) {
  return defaults.data?.[p.product_code] || {}
}
function fixedPerDay(p) {
  return defaultsOf(p).per_day || 0
}
function fixedItems(p) {
  return defaultsOf(p).fixed || []
}
function variableDefaults(p) {
  return defaultsOf(p).variable || []
}

// "C-00001 - Nama Item". Nama produk datang dari get_cost_defaults; kalau payload
// lama (masih ter-cache) belum membawanya, kodenya saja sudah cukup.
function productLabel(p) {
  if (!p.product_code) return __('(produk belum dipilih)')
  const name = defaultsOf(p).product_name
  return name && name !== p.product_code ? `${p.product_code} - ${name}` : p.product_code
}

function linesOf(p) {
  const k = key(p)
  return (props.doc.cost_items || []).filter((c) => c.cost_key === k)
}

// Rumus yang sama dengan CRMQuotation.calculate_costing() di server; di sini
// hanya untuk pratinjau sebelum disimpan. Server tetap yang menentukan.
// Semua komponen per hari (variable cost = biaya per hari), di-margin,
// baru dikali duration: Base = (Fixed/Day + Variable/Day + Margin/Day) x Duration.
function calc(p) {
  const dur = p.duration || 1
  const variablePerDay = linesOf(p).reduce((s, c) => s + (c.qty || 0) * (c.rate || 0), 0)
  const fixed = fixedPerDay(p) * dur
  const variable = variablePerDay * dur
  const margin = (((fixedPerDay(p) + variablePerDay) * (p.margin_percent || 0)) / 100) * dur
  return { fixed, variablePerDay, variable, margin, base: fixed + variable + margin }
}

// Angka yang tampil di kepala kartu. Dengan akses costing: hasil hitung ulang
// live. Tanpa akses: nilai yang sudah tersimpan -- rinciannya memang tidak
// dikirim server, jadi hitungan lokal akan meleset ke bawah.
function shown(p) {
  if (canSeeCosting.value) return calc(p)
  return { margin: p.margin_amount || 0, base: p.procurement_price || 0 }
}

function newLine(p, values = {}) {
  return {
    cost_key: key(p),
    item_name: '',
    qty: 1,
    uom: '',
    rate: 0,
    ...values,
    doctype: 'CRM Cost Item',
    parentfield: 'cost_items',
    parenttype: 'CRM Quotation',
    __islocal: true,
  }
}

function addLine(p) {
  if (!props.doc.cost_items) props.doc.cost_items = []
  props.doc.cost_items.push(newLine(p))
}

// Muat ulang rincian komponen Variable Cost produk. Baris yang namanya sudah
// ada tidak digandakan -- tarif yang sudah disesuaikan Procurement dipertahankan.
function loadDefaults(p) {
  if (!props.doc.cost_items) props.doc.cost_items = []
  const existing = new Set(linesOf(p).map((c) => c.item_name))
  variableDefaults(p)
    .filter((d) => !existing.has(d.item_name))
    .forEach((d) => props.doc.cost_items.push(newLine(p, { ...d, amount: undefined })))
}

function removeLine(c) {
  props.doc.cost_items = props.doc.cost_items.filter((x) => x !== c)
}

function money(v) {
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    maximumFractionDigits: 0,
  }).format(v || 0)
}
</script>
