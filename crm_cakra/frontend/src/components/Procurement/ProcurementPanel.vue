<template>
  <!-- Rincian biaya cuma untuk tim Procurement -- Marketing memasukkan inquiry
       dan menekan Submit, angkanya bukan urusan mereka (roles.py
       PROCUREMENT_ACCESS). Gerbang yang menolak sungguhan tetap di server.
       Pengecualiannya setting "Allow edit in cost in inquiry": pemanggil yang
       memberi canEdit menang atas peran. -->
  <div v-if="canEdit && document.doc" class="flex flex-col">
    <div class="mb-4 flex items-center justify-between">
      <div class="flex h-8 items-center text-xl font-semibold text-ink-gray-8">
        {{ __('Costing') }}
        <Badge
          v-if="document.isDirty"
          class="ml-3"
          :label="__('Not Saved')"
          theme="orange"
        />
      </div>
      <Button
        variant="solid"
        :label="__('Save')"
        :disabled="!document.isDirty"
        :loading="document.save?.loading"
        @click="saveDoc"
      />
    </div>

    <CostTables :doc="document.doc" />
  </div>
</template>

<script setup>
import { computed, provide, watch } from 'vue'
import { Badge, Button, toast } from 'frappe-ui'
import CostTables from '@/components/Procurement/CostTables.vue'
import { useDocument } from '@/data/document'
import { applyItemGroupFilter } from '@/utils/costItemGrid'

const props = defineProps({
  procurementId: { type: String, required: true },
  inquiry: { type: String, default: '' },
  // Siapa yang boleh melihat dan mengubah angka costing. Diputuskan pemanggil:
  // halaman Procurement memakai peran, tab Inquiry menambah setting
  // "Allow edit in cost in inquiry".
  canEdit: { type: Boolean, required: true },
})

const emit = defineEmits(['saved'])

const {
  document,
  triggerOnChange,
  triggerButton,
  triggerOnRowAdd,
  triggerOnRowRemove,
} = useDocument('CRM Procurement', props.procurementId)

// Grid tidak menulis nilai sel sendiri -- dia memanggil trigger yang di-inject
// (di tab Data disediakan rantai Field.vue). Tanpa provide ini, inject jatuh ke
// no-op dan isian sel diam-diam hilang.
provide('triggerOnChange', triggerOnChange)
provide('triggerButton', triggerButton)
provide('triggerOnRowAdd', triggerOnRowAdd)
provide('triggerOnRowRemove', triggerOnRowRemove)
provide(
  'fieldPropertyOverrides',
  computed(() => document.fieldPropertyOverrides || {}),
)

// Kolom Item dua grid costing dibatasi Item Group expense, sama dengan tabel
// Cost Component dan grid Expense di Estimation.
applyItemGroupFilter(document, 'fixed_cost_items.item_name')
applyItemGroupFilter(document, 'variable_cost_items.item_name')

// Costing yang sudah Approve dibekukan: cuma Remarks yang masih boleh diisi,
// supaya catatan kesepakatan tetap bisa ditambah tanpa angkanya bergeser.
// Lewat fieldPropertyOverrides, bukan prop Grid, supaya modal edit baris ikut
// terkunci -- itu jalan masuk kedua ke sel yang sama.
const FROZEN_COLUMNS = ['item_name', 'qty', 'uom', 'rate']

watch(
  () => document.doc?.status,
  (status) => {
    if (!document.fieldPropertyOverrides) document.fieldPropertyOverrides = {}
    for (const table of ['fixed_cost_items', 'variable_cost_items']) {
      for (const column of FROZEN_COLUMNS) {
        const key = `${table}.${column}`
        const rest = { ...(document.fieldPropertyOverrides[key] || {}) }
        // Dihapus, bukan diisi 0: read_only bawaan meta tidak boleh ikut dibuka.
        delete rest.read_only
        document.fieldPropertyOverrides[key] =
          status === 'Approve' ? { ...rest, read_only: 1 } : rest
      }
    }
  },
  { immediate: true },
)

async function saveDoc() {
  try {
    // save.submit() di-override di data/document.js: kalau ada field wajib yang
    // kosong dia cuma menoast lalu balik undefined tanpa pernah memanggil server.
    // Tanpa penjagaan ini tombolnya menghijau "Saved" padahal baris costing tidak
    // pernah sampai ke DB, dan orang menutup tab dengan yakin.
    const saved = await document.save.submit()
    if (!saved) return
    emit('saved')
    toast.success(__('Saved'))
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Failed to save'))
  }
}
</script>
