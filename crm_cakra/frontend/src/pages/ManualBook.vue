<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="[{ label: __('Manual Book') }]" />
    </template>
  </LayoutHeader>

  <div class="flex-1 overflow-y-auto">
    <div class="mx-auto max-w-4xl px-5 py-8">
      <h1 class="text-2xl font-semibold text-ink-gray-9">
        {{ __('Manual Book') }}
      </h1>
      <p class="mt-1 text-base text-ink-gray-6">
        {{ __('Panduan alur kerja CRM: marketing, procurement, dan data master.') }}
      </p>

      <section v-for="(chapter, i) in chapters" :key="chapter.title" class="mt-10">
        <h2 class="text-lg font-semibold text-ink-gray-9">
          {{ i + 1 }}. {{ chapter.title }}
        </h2>
        <p class="mt-1 text-base text-ink-gray-6">{{ chapter.intro }}</p>

        <!-- bagan alur -->
        <div
          class="mt-4 flex flex-wrap items-stretch gap-2 rounded-lg border bg-surface-gray-1 p-4"
        >
          <template v-for="(step, s) in chapter.flow" :key="step.label">
            <FeatherIcon
              v-if="s"
              name="arrow-right"
              class="h-4 w-4 shrink-0 self-center text-ink-gray-4"
            />
            <component
              :is="step.to ? 'router-link' : 'div'"
              :to="step.to ? { name: step.to } : undefined"
              class="min-w-32 flex-1 rounded-md border bg-surface-white px-3 py-2"
              :class="step.to ? 'hover:border-outline-gray-3' : 'border-dashed'"
            >
              <div class="text-base font-medium text-ink-gray-8">
                {{ step.label }}
              </div>
              <div class="mt-0.5 text-sm text-ink-gray-5">{{ step.hint }}</div>
            </component>
          </template>
        </div>

        <!-- langkah rinci -->
        <ol class="mt-4 flex flex-col gap-2">
          <li
            v-for="(line, n) in chapter.steps"
            :key="line"
            class="flex gap-2 text-base text-ink-gray-7"
          >
            <span class="shrink-0 text-ink-gray-4">{{ n + 1 }}.</span>
            <span>{{ line }}</span>
          </li>
        </ol>

        <p
          v-if="chapter.note"
          class="mt-3 rounded-md border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-6"
        >
          {{ chapter.note }}
        </p>
      </section>
    </div>
  </div>
</template>
<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import { Breadcrumbs, FeatherIcon, usePageMeta } from 'frappe-ui'

usePageMeta(() => ({ title: __('Manual Book') }))

const chapters = [
  {
    title: __('Alur Marketing'),
    intro: __('Dari kontak mentah sampai penawaran resmi ke customer.'),
    flow: [
      { label: __('Lead'), hint: __('Kontak masuk'), to: 'Leads' },
      { label: __('Inquiry'), hint: __('Kebutuhan customer'), to: 'Inquiries' },
      { label: __('Quotation'), hint: __('Penawaran harga'), to: 'Quotations' },
    ],
    steps: [
      __('Menu Leads, klik Create. Isi nama, akun, kontak, dan sumber lead.'),
      __('Kerjakan lead lewat tab Emails, Comments, Tasks, dan Meetings sampai kebutuhannya jelas.'),
      __('Kalau lead sudah serius, buka lead-nya lalu klik Convert to Inquiry. Data kontak dan akun ikut pindah otomatis.'),
      __('Di Inquiry, lengkapi detail muatan: rute, moda, incoterms, tanggal shipment, dan kuantitas.'),
      __('Naikkan status Inquiry sampai won. Hanya inquiry won yang bisa ditarik jadi Quotation.'),
      __('Menu Quotations, klik Create, lalu pilih inquiry-nya di kolom Inquiry. Isi item dan harga, simpan.'),
    ],
    note: __('Quotation yang sudah deal bisa dilanjutkan dengan tombol Convert to Estimation di halaman quotation.'),
  },
  {
    title: __('Alur Procurement'),
    intro: __('Menyiapkan komponen biaya supaya harga di quotation punya dasar.'),
    flow: [
      { label: __('Cost Type'), hint: __('Fixed / variable'), to: 'CostTypes' },
      { label: __('Cost Component'), hint: __('Paket biaya + rate'), to: 'CostComponents' },
      { label: __('Product'), hint: __('Jasa yang dijual'), to: 'Products' },
      { label: __('Quotation'), hint: __('Tab Procurement'), to: 'Quotations' },
    ],
    steps: [
      __('Menu Cost Types, klik Create. Tentukan perilakunya: fixed cost atau variable cost.'),
      __('Menu Cost Components, klik Create. Isi nama komponen, tipe, masa berlaku, lalu daftar item biaya beserta qty, uom, dan rate.'),
      __('Menu Products, klik Create. Pasang cost component yang dipakai produk itu di bagian Cost Default.'),
      __('Di Quotation, tambahkan produk pada tab Data. Fixed cost dan variable cost tersalin dari cost component produk tersebut.'),
      __('Buka tab Procurement di quotation untuk minta harga ke tim procurement. Diskusi lewat kolom komentar, bisa mention peserta.'),
      __('Setelah harga vendor didapat, isi procurement price lalu klik Finish. Harga masuk ke baris produk dan margin terhitung.'),
    ],
    note: __('Menu Procurement di sidebar berisi daftar semua quotation yang sedang dibahas, urut dari komentar terbaru.'),
  },
  {
    title: __('Alur Data Master'),
    intro: __('Data yang dipakai berulang. Isi sekali, dipakai semua transaksi.'),
    flow: [
      { label: __('Accounts'), hint: __('Perusahaan customer'), to: 'Organizations' },
      { label: __('Contacts'), hint: __('Orangnya'), to: 'Contacts' },
      { label: __('Products'), hint: __('Jasa + biaya'), to: 'Products' },
      { label: __('Transaksi'), hint: __('Lead, Inquiry, Quotation') },
    ],
    steps: [
      __('Accounts: menu Accounts, klik Create. Satu akun mewakili satu perusahaan customer, dipakai di lead, inquiry, dan quotation.'),
      __('Contacts: menu Contacts, klik Create. Hubungkan ke akunnya supaya muncul saat memilih kontak di transaksi.'),
      __('Products: menu Products, klik Create. Isi kode, nama, standard rate, dan cost component-nya.'),
      __('Notes: menu Notes atau tab Notes di dokumen. Catatan bebas yang menempel pada satu dokumen.'),
      __('Meetings: menu Meetings, klik Create. Absen kehadiran dipakai lewat halaman Absen dengan lokasi GPS.'),
      __('Tasks: menu Tasks atau tab Tasks di dokumen. Isi due date dan penanggung jawabnya.'),
    ],
    note: __('Notes, Meetings, dan Tasks bisa dibuat langsung dari tab di dalam lead, inquiry, atau quotation supaya otomatis menempel ke dokumen itu.'),
  },
]
</script>
