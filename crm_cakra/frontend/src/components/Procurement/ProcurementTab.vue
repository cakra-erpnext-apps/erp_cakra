<template>
  <div class="flex-1 overflow-y-auto px-5 pb-8">
    <!-- "Postingan": item product quotation, grid yang sama dengan tab Data -->
    <div class="pt-4">
      <div class="mb-2 flex items-center justify-between">
        <div class="text-base font-medium text-ink-gray-9">
          {{ __('Products') }}
        </div>
        <div class="flex gap-2">
          <!-- Costing yang sudah selesai (Approved) tinggal punya satu jalan:
               dibuka lagi lewat Edit. Save disembunyikan di situ supaya tidak
               ada yang mengubah angka tanpa memindahkan statusnya dulu. -->
          <Button
            v-if="!isApproved"
            :label="__('Save')"
            :disabled="!document.isDirty"
            :loading="document.save?.loading"
            @click="saveDoc"
          />
          <Button
            v-if="isApproved"
            :label="__('Edit')"
            :loading="finishing"
            @click="reopen"
          />
          <!-- Finish hanya untuk costing yang memang sedang diminta (Waiting).
               Di status lain quotation bukan pekerjaan Procurement, jadi tombolnya
               tidak ada -- server pun menolak transisinya. -->
          <Button
            v-else-if="isWaiting"
            variant="solid"
            theme="blue"
            :label="__('Finish')"
            :loading="finishing"
            @click="confirmFinish"
          />
        </div>
      </div>
      <Grid
        v-if="document.doc"
        v-model="document.doc.products"
        v-model:parent="document.doc"
        doctype="CRM Products"
        parentDoctype="CRM Quotation"
        parentFieldname="products"
      />
    </div>

    <!-- Costing: variable cost per item dihitung di sini, fixed cost ditarik dari
         master produk. Hasilnya jadi Base Price, yang menjadi lantai harga:
         Price boleh di atasnya, tidak boleh di bawah (dijaga server saat save). -->
    <div class="mt-6">
      <div class="mb-2 text-base font-medium text-ink-gray-9">
        {{ __('Costing') }}
      </div>
      <CostingPanel
        v-if="document.doc"
        :doc="document.doc"
        :quotationId="props.quotationId"
        :readonly="isApproved"
      />
    </div>

    <!-- Thread komentar procurement, ala komentar di bawah postingan.
         Dibatasi max-w supaya nyaman dibaca, tidak selebar grid. -->
    <div class="mt-6 max-w-2xl">
      <div class="mb-3 text-base font-medium text-ink-gray-9">
        {{ __('Comments') }}
        <span v-if="comments.data?.length" class="text-ink-gray-5">
          ({{ comments.data.length }})
        </span>
      </div>

      <div v-if="comments.data?.length" class="flex flex-col gap-3">
        <div
          v-for="c in comments.data"
          :key="c.name"
          :id="'pcomment-' + c.name"
          class="group flex gap-2 rounded-lg transition-colors duration-500"
          :class="highlighted === c.name ? 'bg-surface-gray-2' : ''"
        >
          <UserAvatar :user="c.owner" size="md" class="mt-0.5 shrink-0" />
          <div class="min-w-0 flex-1">
            <div class="rounded-lg bg-surface-gray-1 px-3 py-2">
              <div class="flex items-baseline justify-between gap-2">
                <span class="text-sm font-medium text-ink-gray-9">
                  {{ c.owner_name }}
                </span>
                <span class="shrink-0 text-xs text-ink-gray-5">
                  {{ __(timeAgo(c.creation)) }}
                </span>
              </div>
              <!-- Kutipan pesan yang dibalas, ala WhatsApp -->
              <div
                v-if="c.reply_to"
                class="mt-1 cursor-pointer rounded border-l-2 border-outline-gray-3 bg-surface-white px-2 py-1"
                @click="scrollToComment(c.reply_to)"
              >
                <div class="text-xs font-medium text-ink-gray-8">
                  {{ repliedOf(c)?.owner_name || __('Komentar dihapus') }}
                </div>
                <div class="truncate text-sm text-ink-gray-6">
                  {{ excerpt(repliedOf(c)?.content) }}
                </div>
              </div>
              <!-- eslint-disable-next-line vue/no-v-html -->
              <div
                class="prose-f mt-0.5 break-words text-base leading-6"
                v-html="sanitizeHTML(c.content)"
              />
            </div>
            <div class="mt-0.5 flex gap-3 px-3 text-xs">
              <button
                class="hidden text-ink-gray-5 hover:underline group-hover:inline"
                @click="startReply(c)"
              >
                {{ __('Reply') }}
              </button>
              <button
                v-if="c.owner === user"
                class="hidden text-ink-red-3 hover:underline group-hover:inline"
                @click="removeComment(c)"
              >
                {{ __('Delete') }}
              </button>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="text-base text-ink-gray-5">
        {{ __('Belum ada komentar. Mulai diskusi procurement di sini.') }}
      </div>

      <!-- Tulis komentar: rich editor dengan @mention -->
      <div class="mt-4 flex items-start gap-2">
        <UserAvatar :user="user" size="md" class="mt-1 shrink-0" />
        <div
          class="flex-1 overflow-hidden rounded-lg border border-outline-gray-2 focus-within:border-outline-gray-3"
        >
          <!-- Bar "membalas X" ala WhatsApp -->
          <div
            v-if="replyTo"
            class="flex items-start justify-between gap-2 border-b border-outline-gray-1 bg-surface-gray-1 px-3 py-1.5"
          >
            <div class="min-w-0 border-l-2 border-outline-gray-3 pl-2">
              <div class="text-xs font-medium text-ink-gray-8">
                {{ replyTo.owner_name }}
              </div>
              <div class="truncate text-sm text-ink-gray-6">
                {{ excerpt(replyTo.content) }}
              </div>
            </div>
            <button class="shrink-0 text-ink-gray-5 hover:text-ink-gray-8" @click="replyTo = null">
              <LucideX class="size-4" />
            </button>
          </div>
          <TextEditor
            ref="textEditor"
            :editor-class="['prose-sm max-w-none min-h-14 px-3 py-2']"
            :content="newComment"
            :placeholder="__('Tulis komentar... ketik @ untuk mention')"
            :mentions="mentionUsers"
            @change="newComment = $event"
          />
          <div class="flex justify-end border-t border-outline-gray-1 px-2 py-1.5">
            <Button
              variant="solid"
              :label="__('Post')"
              :loading="posting"
              @click="postComment"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, provide, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { createResource, Button, call, toast, TextEditor } from 'frappe-ui'
import Grid from '@/components/Controls/Grid.vue'
import CostingPanel from '@/components/Procurement/CostingPanel.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { timeAgo, sanitizeHTML } from '@/utils'
import { useDocument } from '@/data/document'
import { getMeta } from '@/stores/meta'
import { globalStore } from '@/stores/global'
import { sessionStore } from '@/stores/session'
import { usersStore } from '@/stores/users'
import LucideX from '~icons/lucide/x'

const props = defineProps({
  quotationId: { type: String, required: true },
})

const { user } = sessionStore()
const { $socket } = globalStore()

// Dokumen yang sama dengan tab Data (useDocument di-cache per doctype+name),
// jadi edit grid di sini = edit quotation, disimpan lewat tombol Save di header.
const { document, triggerOnChange, triggerButton, triggerOnRowAdd, triggerOnRowRemove } =
  useDocument('CRM Quotation', props.quotationId)

// Grid tidak menulis nilai sel sendiri — dia memanggil trigger yang di-inject
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

const comments = createResource({
  url: 'crm_cakra.api.procurement.get_comments',
  params: { quotation: props.quotationId },
  cache: ['procurement_comments', props.quotationId],
  auto: true,
})

const newComment = ref('')
const posting = ref(false)
const finishing = ref(false)

// Approved = costing dinyatakan selesai. Tombolnya berganti jadi Edit, dan Edit
// mengembalikan statusnya ke Waiting supaya revisinya terlihat sebagai
// pekerjaan yang masih berjalan, bukan hasil yang sudah disetujui.
const isApproved = computed(() => document.doc?.state === 'Approved')
const isWaiting = computed(() => document.doc?.state === 'Waiting')

// Approved = costing final. Grid Products ikut dikunci sampai kolom-kolomnya,
// termasuk tombol tambah/hapus baris (Grid membaca read_only field induknya).
// Dikunci di tampilan DAN dijaga server: validate() menolak perubahan apa pun
// pada quotation yang sudah Approved.
const productFields = computed(() => {
  const meta = getMeta('CRM Products')
  return meta?.getFields ? meta.getFields({ restrictNoValueFields: false }) : []
})

watch(
  [isApproved, productFields],
  ([approved, fields]) => {
    if (!document.fieldPropertyOverrides) document.fieldPropertyOverrides = {}
    const ov = document.fieldPropertyOverrides
    const keys = ['products', ...fields.map((f) => `products.${f.fieldname}`)]
    keys.forEach((k) => {
      ov[k] = { ...(ov[k] || {}), read_only: approved ? 1 : 0 }
    })
  },
  { immediate: true },
)

// Komentar orang lain masuk tanpa perlu refresh.
//
// Tidak ada event khusus yang perlu dibuat: setiap insert/update dokumen sudah
// menyiarkan `list_update` ke room doctype-nya (frappe.model.document.notify_update),
// jadi cukup ikut room itu. Isinya cuma {doctype, name, user} -- tanpa quotation --
// makanya threadnya ditarik ulang dulu, lalu toast baru muncul kalau memang ADA
// baris baru di thread ini (siaran itu kena semua quotation).
async function onCommentEvent(data) {
  if (data?.doctype !== 'CRM Procurement Comment') return
  // Komentar sendiri: daftarnya sudah diperbarui postComment().
  if (data?.user === user.value) return

  const sebelum = new Set((comments.data || []).map((c) => c.name))
  await comments.reload()
  const baru = (comments.data || []).filter((c) => !sebelum.has(c.name))
  if (!baru.length) return

  const penulis = baru[baru.length - 1].owner_name
  toast.info(
    baru.length > 1
      ? __('{0} komentar baru di Procurement', [baru.length])
      : __('{0} menambahkan komentar', [penulis]),
  )
}

onMounted(() => {
  $socket.emit('doctype_subscribe', 'CRM Procurement Comment')
  $socket.on('list_update', onCommentEvent)
})

onBeforeUnmount(() => {
  $socket.off('list_update', onCommentEvent)
  $socket.emit('doctype_unsubscribe', 'CRM Procurement Comment')
})

async function setState(state) {
  finishing.value = true
  try {
    const r = await call('crm_cakra.api.procurement.set_costing_state', {
      quotation: props.quotationId,
      state,
    })
    document.doc.state = r.state
    if (document.originalDoc) document.originalDoc.state = r.state
    return r.state
  } finally {
    finishing.value = false
  }
}

async function reopen() {
  try {
    const state = await setState('Waiting')
    toast.success(__('Costing dibuka lagi, status {0}', [__(state)]))
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal mengubah status'))
  }
}
const textEditor = ref(null)
const replyTo = ref(null)
const highlighted = ref(null)

function repliedOf(c) {
  return comments.data?.find((x) => x.name === c.reply_to)
}

function excerpt(html) {
  const t = (html || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
  return t.length > 120 ? t.slice(0, 120) + '...' : t
}

function startReply(c) {
  replyTo.value = c
  textEditor.value?.editor?.commands?.focus()
}

function scrollToComment(name) {
  const el = window.document.getElementById('pcomment-' + name)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  highlighted.value = name
  setTimeout(() => (highlighted.value = null), 1500)
}

// Daftar user untuk @mention di editor (format yang dipahami TextEditor).
const { users: usersList } = usersStore()
const mentionUsers = computed(
  () =>
    usersList.data?.crmUsers
      ?.filter((u) => u.enabled)
      .map((u) => ({ label: u.full_name.trimEnd(), value: u.name })) || [],
)

async function saveDoc() {
  try {
    await document.save.submit()
    toast.success(__('Saved'))
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Failed to save'))
  }
}

async function confirmFinish() {
  // Price TIDAK lagi ditimpa dari Base Price. Base Price sekarang berperan
  // sebagai lantai harga -- angka jualnya tetap keputusan orang. Simpan biasa
  // tidak ditolak (menawar harga itu pekerjaan setengah jadi yang wajar); yang
  // dijaga adalah Finish di sini dan cetak di server (before_print).
  const rows = (document.doc?.products || []).filter(
    (p) => Number(p.procurement_price) > 0,
  )
  if (!rows.length) {
    toast.error(__('Belum ada Base Price. Isi costing tiap item dulu.'))
    return
  }

  const below = rows.filter(
    (p) => Number(p.price || 0) < Number(p.procurement_price),
  )
  if (below.length) {
    toast.error(
      __('{0} item harganya masih di bawah Base Price. Perbaiki dulu.', [
        below.length,
      ]),
    )
    return
  }

  finishing.value = true
  try {
    await document.save.submit()
    // Status dipindah server, bukan lewat doc.state di sini: save berikutnya
    // dari tab lain bisa membawa state lama dan diam-diam memutarnya balik.
    const state = await setState('Approved')
    toast.success(__('Costing selesai, status jadi {0}', [__(state)]))
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Failed to save'))
  } finally {
    finishing.value = false
  }
}

async function postComment() {
  const content = newComment.value
  // Konten HTML dari editor: anggap kosong bila tanpa teks nyata.
  const plain = content.replace(/<[^>]*>/g, '').trim()
  if (!plain || posting.value) return
  posting.value = true
  try {
    const row = await call('crm_cakra.api.procurement.add_comment', {
      quotation: props.quotationId,
      content,
      reply_to: replyTo.value?.name || null,
    })
    comments.data = [...(comments.data || []), row]
    newComment.value = ''
    replyTo.value = null
    textEditor.value?.editor?.commands?.clearContent(true)
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal mengirim komentar'))
  } finally {
    posting.value = false
  }
}

async function removeComment(c) {
  if (!confirm(__('Hapus komentar ini?'))) return
  try {
    await call('crm_cakra.api.procurement.delete_comment', { name: c.name })
    comments.data = comments.data.filter((x) => x.name !== c.name)
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Gagal menghapus komentar'))
  }
}
</script>
