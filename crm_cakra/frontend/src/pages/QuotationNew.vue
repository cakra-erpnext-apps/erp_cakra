<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs" />
    </template>
    <template #right-header>
      <Button :label="__('Cancel')" @click="cancel" />
      <Button
        variant="solid"
        :label="__('Save')"
        :loading="creating"
        @click="createQuotation"
      />
    </template>
  </LayoutHeader>

  <div class="flex-1 overflow-y-auto px-5 py-6">
    <div class="mx-auto max-w-4xl">
      <div
        v-if="tabs.loading"
        class="flex flex-col items-center justify-center gap-3 py-20 text-ink-gray-5"
      >
        <LoadingIndicator class="h-6 w-6" />
        <span>{{ __('Loading...') }}</span>
      </div>

      <FieldLayout
        v-else-if="tabs.data?.length"
        :tabs="tabs.data"
        :data="quotation.doc"
        doctype="CRM Quotation"
      />

      <ErrorMessage v-if="error" class="mt-4" :message="__(error)" />
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import FieldLayout from '@/components/FieldLayout/FieldLayout.vue'
import LoadingIndicator from '@/components/Icons/LoadingIndicator.vue'
import { Breadcrumbs, Button, ErrorMessage, createResource, call } from 'frappe-ui'
import { useDocument } from '@/data/document'
import { openGmapRoute, fetchDistance } from '@/utils/gmap'
import { startNewDoc } from '@/utils/draft'
import { notify } from '@/utils/notify'
import { sessionStore } from '@/stores/session'
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const session = sessionStore()
const error = ref(null)
const creating = ref(false)

// Dokumen baru — sama seperti flow create Inquiry/Lead.
const { document: quotation } = useDocument('CRM Quotation')

// Cache dokumen "new" (key '') di data/document.js persist antar navigasi, jadi
// tanpa reset, form quotation baru membawa data quotation sebelumnya. Reset ke
// dokumen kosong; kalau datang dari Duplicate, pakai data salinannya; kalau ada
// isian yang belum tersimpan (refresh/internet putus), pulihkan itu.
const discardDraft = startNewDoc(quotation, 'CRM Quotation', {
  __newDocument: true,
  doctype: 'CRM Quotation',
})
quotation.fieldPropertyOverrides = {}

const breadcrumbs = computed(() => [
  { label: __('Quotations'), route: { name: 'Quotations' } },
  { label: __('New Quotation') },
])

// Layout yang SAMA dengan halaman detail (Tab Data).
const tabs = createResource({
  url: 'crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout',
  params: { doctype: 'CRM Quotation', type: 'Data Fields' },
  auto: true,
  transform: (_tabs) => {
    // Inisialisasi field Table (products) agar grid bisa dirender.
    _tabs.forEach((tab) =>
      tab.sections.forEach((s) =>
        s.columns.forEach((c) =>
          c.fields.forEach((f) => {
            if (f.fieldtype === 'Table' && !quotation.doc[f.fieldname]) {
              quotation.doc[f.fieldname] = []
            }
          }),
        ),
      ),
    )
    return _tabs
  },
})

// Inquiry yang boleh dipilih: status Won DAN belum dipakai quotation lain.
const availableInquiries = createResource({
  url: 'crm_cakra.api.quotation.get_available_inquiries',
  auto: true,
})

watch(
  [() => tabs.data, () => availableInquiries.data],
  ([tabsData, avail]) => {
    if (!tabsData || !avail) return
    const names = avail.map((d) => d.name)
    tabsData.forEach((tab) =>
      tab.sections.forEach((s) =>
        s.columns.forEach((c) =>
          c.fields.forEach((f) => {
            if (f.fieldname === 'inquiry') {
              // Batasi dropdown ke inquiry yang tersedia (Won + belum dipakai).
              f.link_filters = JSON.stringify({ name: ['in', names] })
            }
          }),
        ),
      ),
    )
  },
  { immediate: true },
)

// Saat inquiry dipilih → isi account & subject langsung dari inquiry
// (live, supaya account read-only langsung muncul tanpa menunggu save).
watch(
  () => quotation.doc.inquiry,
  async (inq) => {
    if (!inq) return
    const inquiry = await call('frappe.client.get_value', {
      doctype: 'CRM Inquiry',
      filters: { name: inq },
      // annual_revenue = "Estimation Cost" di CRM Inquiry (field warisan, label
      // saja yang diganti). Jadi pembanding margin quotation ini.
      fieldname: ['organization', 'subject', 'origin', 'destination', 'annual_revenue'],
    })
    if (!inquiry) return
    quotation.doc.account = inquiry.organization || ''
    if (!quotation.doc.subject) quotation.doc.subject = inquiry.subject || ''
    // Rute inquiry -> Loading/Unloading (Link Fleet Location). Nilai yang tidak
    // cocok dengan lokasi terdaftar tetap terisi, tapi ditolak waktu save.
    quotation.doc.loading = inquiry.origin || ''
    quotation.doc.unloading = inquiry.destination || ''
    quotation.doc.estimation_costing = inquiry.annual_revenue || 0
    quotation.doc.margin =
      (Number(quotation.doc.net_total) || 0) - (Number(inquiry.annual_revenue) || 0)
  },
)

// Kalkulasi live: amount = qty * price per baris + net_total.
// Base Price dihitung sejak di halaman New, tidak menunggu simpan pertama.
// Angka ini adalah lantai harga (lihat validate_price_floor di crm_quotation.py);
// membiarkannya 0 selama orang mengetik harga berarti aturannya baru terlihat
// setelah harga terlanjur salah.
watch(
  () =>
    (quotation.doc.products || [])
      .map((p) => `${p.product_code || ''}|${p.duration || ''}|${p.margin_percent || ''}`)
      .join(';'),
  async () => {
    const rows = quotation.doc.products || []
    if (!rows.length) return
    try {
      const bases = await call('crm_cakra.api.procurement.preview_base_prices', {
        rows: rows.map((p) => ({
          product_code: p.product_code,
          duration: p.duration,
          margin_percent: p.margin_percent,
        })),
      })
      rows.forEach((p, i) => {
        const base = Number(bases?.[i]) || 0
        if ((p.procurement_price || 0) !== base) p.procurement_price = base
      })
    } catch (e) {
      // Angka lama dibiarkan: pratinjau yang gagal bukan alasan menampilkan 0,
      // dan server tetap menghitung ulang saat simpan.
      console.error('[Quotation] gagal menghitung Base Price:', e)
    }
  },
)

watch(
  () => (quotation.doc.products || []).map((p) => `${p.qty}|${p.price}|${p.rate}`).join(';'),
  () => {
    let total = 0
    ;(quotation.doc.products || []).forEach((p) => {
      p.amount = (Number(p.qty) || 0) * (Number(p.price) || 0) * (Number(p.rate) || 1)
      total += p.amount
    })
    quotation.doc.net_total = total
    quotation.doc.margin = total - (Number(quotation.doc.estimation_costing) || 0)
  },
)

onMounted(() => {
  // Paksa Account selalu tampil (read-only) walau belum terisi —
  // Frappe biasanya menyembunyikan field read-only yang kosong.
  if (!quotation.fieldPropertyOverrides) quotation.fieldPropertyOverrides = {}
  quotation.fieldPropertyOverrides.account = { hidden: false }
  quotation.fieldPropertyOverrides.check_gmap = { click: openGmapRoute }
  quotation.fieldPropertyOverrides.get_km = {
    error: '',
    click: (doc) => fetchDistance(doc, quotation.fieldPropertyOverrides),
  }

  // Default yang nyaman (server tetap menerapkan default doctype saat insert).
  if (!quotation.doc.date) {
    quotation.doc.date = new Date().toISOString().slice(0, 10)
  }
  if (!quotation.doc.currency) quotation.doc.currency = 'IDR'
  if (!quotation.doc.rate) quotation.doc.rate = 1
  // Printed By default = user yang sedang login (yang membuat).
  if (!quotation.doc.printed_by) quotation.doc.printed_by = session.user
  // Judul additional default (server juga menerapkan default doctype saat insert,
  // ini supaya langsung tampil di form baru sebelum save).
  if (!quotation.doc.additional1_title) quotation.doc.additional1_title = 'Rate Include'
  if (!quotation.doc.additional2_title) quotation.doc.additional2_title = 'Rate Exclude'
  if (!quotation.doc.tac) quotation.doc.tac = 'Terms and Conditions'
})

function createQuotation() {
  error.value = null
  const doc = { ...quotation.doc, doctype: 'CRM Quotation' }
  delete doc.__newDocument

  creating.value = true
  createResource({
    url: 'frappe.client.insert',
    params: { doc },
    auto: true,
    onSuccess(d) {
      creating.value = false
      discardDraft()
      router.push({ name: 'Quotation', params: { quotationId: d.name } })
    },
    onError(err) {
      creating.value = false
      error.value =
        err.messages?.join('\n') || err.message || __('Failed to create quotation')
      // Lewat notify(), bukan toast langsung: pesan yang sama juga dilempar
      // handler global (resourceFetcher dan serverMessagesHandler), dan hanya
      // notify() yang menyaring pengulangan -- toast langsung menumpuk jadi
      // beberapa kotak identik di layar.
      notify(error.value)
    },
  })
}

function cancel() {
  discardDraft()
  router.push({ name: 'Quotations' })
}
</script>
