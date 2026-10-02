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
      __('Naikkan status Inquiry sesuai tahapnya: Created, Qualified, Submit (dikirim ke Procurement), Approved (costing disetujui), lalu Quotation.'),
      __('Menu Quotations, klik Create, lalu pilih inquiry-nya di kolom Inquiry. Inquiry yang sudah Lost tidak bisa dipilih. Isi item dan harga, simpan.'),
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
      { label: __('Procurement'), hint: __('Costing per inquiry'), to: 'Procurement' },
    ],
    steps: [
      __('Menu Cost Types, klik Create. Tentukan perilakunya: fixed cost atau variable cost.'),
      __('Menu Cost Components, klik Create. Isi nama komponen, tipe, masa berlaku, lalu daftar item biaya beserta qty, uom, dan rate.'),
      __('Menu Products, klik Create. Pasang cost component yang dipakai produk itu di bagian Cost Default.'),
      __('Menu Procurement, klik Add Inquiry lalu pilih inquiry yang butuh harga. Data inquiry-nya ikut tampil di halaman itu.'),
      __('Klik Submit to Procurement untuk mengirim permintaan: isi remark, pilih penerima, dan lampirkan berkas kalau ada.'),
      __('Tim procurement mengisi tabel Fixed Cost dan Variable Cost di bagian bawah, boleh diketik manual atau ditarik dari Cost Component.'),
    ],
    note: __('Total Fixed dan Variable Cost tercermin ke inquiry-nya, dan tersalin ke quotation yang dibuat dari inquiry itu.'),
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
  {
    title: __('Role dan Akses User'),
    intro: __('Untuk admin (System Manager atau Manager). Tiap user punya satu jabatan yang menentukan timnya, ditambah branch, role approval, dan menu yang boleh tampil.'),
    flow: [
      { label: __('Jabatan'), hint: __('Settings, Users') },
      { label: __('Branch'), hint: __('Form User di desk') },
      { label: __('Approval'), hint: __('Role Estimation Approve') },
      { label: __('Menu'), hint: __('CRM Menu Access') },
    ],
    steps: [
      __('Jabatan: klik nama Anda di kiri atas, pilih Settings, lalu Users. Klik user-nya dan pilih jabatan. Role dasarnya ikut terpasang otomatis, tidak perlu dipasang sendiri.'),
      __('Marketing: Marketing Manager mendapat Sales Manager (melihat semua cabang dan boleh mengatur user). Marketing Supervisor dan Marketing Sales mendapat Sales User (melihat data cabangnya sendiri dan miliknya).'),
      __('Procurement: Procurement Manager mendapat Sales Manager, Procurement Operational mendapat Sales User. Hanya tim Procurement yang bisa melihat dan mengisi rincian Fixed Cost dan Variable Cost.'),
      __('Finance: belum ada jabatan Finance di menu Users. Buka form user-nya di desk (/app/user), pasang role Sales User supaya bisa membuka CRM, Accounts User supaya melihat semua cabang, dan Estimation Approve Finance kalau orang itu yang menyetujui Estimation.'),
      __('Branch: di form User desk isi field Branch (cabang utama) dan Additional Branches kalau boleh melihat cabang lain. Dokumen baru otomatis memakai cabang utama pembuatnya.'),
      __('Level lihat per role diatur di /app/cmi-branch-access: See All, Branch + Owner, atau Owner Only. Bawaannya Sales User = Branch + Owner, Sales Manager dan Accounts User = See All.'),
      __('Approval Estimation punya 3 role: Estimation Approve Procurement dan Estimation Approve Finance (urutannya bebas), lalu Estimation Approve Marketing sebagai approval terakhir. Pasang di form User desk, terpisah dari jabatan.'),
      __('Menu: buka /app/crm-menu-access, tambah satu baris per grup (Role), lalu centang menu yang boleh tampil. Contoh: grup Procurement Operational centang Dashboard, Inquiries, Procurement, Cost Types, Cost Components, dan Products. Grup Estimation Approve Finance centang Dashboard dan Estimations.'),
    ],
    note: __('Menu Access hanya menyembunyikan menu, bukan membatasi data. Batas data tetap dari role dasar dan Branch. User yang tidak masuk grup mana pun, System Manager, dan Administrator melihat semua menu.'),
  },
]
</script>
