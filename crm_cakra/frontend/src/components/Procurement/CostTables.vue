<template>
  <div class="flex flex-col gap-6">
    <div v-for="t in tables" :key="t.fieldname">
      <div class="mb-2 text-base font-medium text-ink-gray-9">
        {{ __(t.label) }}
      </div>
      <Grid
        v-model="doc[t.fieldname]"
        :parent="doc"
        doctype="CRM Cost Item"
        parentDoctype="CRM Procurement"
        :parentFieldname="t.fieldname"
        :lockRows="frozen"
      >
        <!-- Baris boleh diketik manual; kontrol ini jalan pintas untuk menarik
             rincian sebuah komponen sekaligus. Satu kontrol saja, tanpa dialog:
             memilih memang satu-satunya langkahnya. Sebelum daftar tipenya sampai,
             filternya kosong -> pencarian pasti nihil, makanya ditunggu dulu. -->
        <template #actions>
          <Link
            v-if="types.data && !frozen"
            class="w-56"
            size="sm"
            :value="null"
            doctype="CRM Cost Component"
            :filters="componentFilters(t.behavior)"
            :placeholder="__('Tarik dari Cost Component...')"
            @change="(c) => importComponent(c, t.fieldname)"
          />
        </template>
      </Grid>
    </div>

    <!-- Summary -->
    <div class="rounded-lg border border-outline-gray-2">
      <div class="border-b border-outline-gray-2 px-4 py-2 text-base font-medium text-ink-gray-9">
        {{ __('Summary') }}
      </div>
      <div class="flex flex-col gap-1 px-4 py-3 text-base">
        <div class="flex justify-between text-ink-gray-7">
          <span>{{ __('Total Fixed Cost') }}</span>
          <span class="tabular-nums">{{ money(totalFixed) }}</span>
        </div>
        <div class="flex justify-between text-ink-gray-7">
          <span>{{ __('Total Variable Cost') }}</span>
          <span class="tabular-nums">{{ money(totalVariable) }}</span>
        </div>
        <div
          class="mt-1 flex justify-between border-t border-outline-gray-2 pt-2 font-medium text-ink-gray-9"
        >
          <span>{{ __('Total') }}</span>
          <span class="tabular-nums">{{ money(totalCost) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import { createResource, call, toast } from 'frappe-ui'
import Grid from '@/components/Controls/Grid.vue'
import Link from '@/components/Controls/Link.vue'
import { money as formatMoney } from '@/utils'

const props = defineProps({
  doc: { type: Object, required: true },
  readonly: { type: Boolean, default: false },
})

const money = (v) => formatMoney(v || 0, 'IDR')

// Sudah Approve = angkanya beku (kolomnya dikunci ProcurementPanel lewat
// fieldPropertyOverrides); di sini yang ikut hilang tombol tambah/hapus baris
// dan jalan pintas tarik komponen.
const frozen = computed(() => props.doc.status === 'Approve')

const tables = [
  { fieldname: 'fixed_cost_items', label: 'Fixed Cost', behavior: 'Fixed Cost' },
  { fieldname: 'variable_cost_items', label: 'Variable Cost', behavior: 'Variable Cost' },
]

// Tipe biaya beserta perannya. Nama tipe bebas ditambah user; yang menentukan
// sebuah komponen masuk tabel Fixed atau Variable adalah field behavior-nya.
const types = createResource({
  url: 'frappe.client.get_list',
  params: {
    doctype: 'CRM Cost Type',
    filters: { disabled: 0 },
    fields: ['name', 'behavior'],
    limit_page_length: 0,
  },
  auto: true,
})

// Hanya komponen yang sudah Validated yang boleh ditarik -- sama dengan gerbang
// di resolve() server.
function componentFilters(behavior) {
  return {
    type: ['in', (types.data || []).filter((t) => t.behavior === behavior).map((t) => t.name)],
    status: 'Validated',
    disabled: 0,
  }
}

async function importComponent(component, fieldname) {
  if (!component || props.readonly || frozen.value) return
  try {
    // Baris anak dibaca lewat parent=: izinnya ikut CRM Cost Component,
    // jadi tidak perlu endpoint sendiri.
    const rows = await call('frappe.client.get_list', {
      doctype: 'CRM Cost Item',
      parent: 'CRM Cost Component',
      filters: { parent: component, parenttype: 'CRM Cost Component' },
      fields: ['item_name', 'qty', 'uom', 'rate', 'remarks'],
      order_by: 'idx asc',
      limit_page_length: 0,
    })
    if (!rows.length) {
      toast.error(__('Komponen {0} belum punya rincian item.', [component]))
      return
    }
    if (!props.doc[fieldname]) props.doc[fieldname] = []
    rows.forEach((r, i) =>
      props.doc[fieldname].push({
        ...r,
        source_component: component,
        doctype: 'CRM Cost Item',
        parentfield: fieldname,
        parenttype: 'CRM Procurement',
        idx: props.doc[fieldname].length + i + 1,
        __islocal: true,
      }),
    )
    toast.success(__('{0} baris diimpor dari {1}', [rows.length, component]))
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal mengimpor komponen'))
  }
}

function sum(rows) {
  return (rows || []).reduce((s, r) => s + (r.qty || 0) * (r.rate || 0), 0)
}

const totalFixed = computed(() => sum(props.doc.fixed_cost_items))
const totalVariable = computed(() => sum(props.doc.variable_cost_items))
const totalCost = computed(() => totalFixed.value + totalVariable.value)
// Total di dokumen ikut bergerak saat sel diketik, bukan diam sampai Save --
// angka yang mengikat tetap hitungan validate() di server.
//
// Ditulis hanya kalau angkanya benar-benar berubah: menimpa dengan nilai yang
// sama membuat dokumen tampak "Not Saved" cuma karena halamannya dibuka.
function setNum(field, value) {
  if ((props.doc[field] || 0) !== value) props.doc[field] = value
}

// amount kolom read_only yang baru diisi validate() di server, jadi tanpa ini
// kolomnya diam sampai dokumen disimpan. Rumusnya disamakan dengan
// crm_cost_item.compute_amount().
function syncAmounts(rows) {
  ;(rows || []).forEach((r) => {
    const amount = (Number(r.qty) || 0) * (Number(r.rate) || 0)
    if (r.amount !== amount) r.amount = amount
  })
}

watch(
  [
    () => props.doc.fixed_cost_items,
    () => props.doc.variable_cost_items,
  ],
  () => {
    syncAmounts(props.doc.fixed_cost_items)
    syncAmounts(props.doc.variable_cost_items)
    setNum('total_fixed_cost', totalFixed.value)
    setNum('total_variable_cost', totalVariable.value)
  },
  { deep: true, immediate: true },
)
</script>
