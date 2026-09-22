<template>
  <div class="flex h-full flex-col overflow-hidden">
    <div
      class="flex h-[45px] shrink-0 items-center gap-2 border-b px-4 text-lg font-medium text-ink-gray-9"
    >
      <CommentIcon class="h-4 text-ink-gray-7" />
      {{ __('Comments') }}
      <span v-if="comments.data?.length" class="text-base font-normal text-ink-gray-5">
        {{ comments.data.length }}
      </span>
    </div>

    <div ref="scroller" class="flex-1 space-y-3 overflow-y-auto px-4 py-4">
      <div
        v-if="!comments.data?.length"
        class="pt-10 text-center text-base text-ink-gray-4"
      >
        {{ __('Belum ada komentar') }}
      </div>

      <div
        v-for="c in comments.data"
        :id="c.name"
        :key="c.name"
        class="flex gap-2 rounded-lg transition-shadow"
      >
        <UserAvatar :user="c.owner" size="md" class="mt-0.5 shrink-0" />
        <div class="min-w-0 flex-1">
          <div
            class="cursor-pointer rounded-xl bg-surface-gray-2 px-3 py-2"
            @click="selected = selected === c.name ? '' : c.name"
          >
            <div class="text-sm font-medium text-ink-gray-8">
              {{ userName(c.owner) }}
            </div>

            <!-- Kutipan komentar yang dibalas, klik untuk melompat ke sana -->
            <div
              v-if="c.quote"
              class="mb-1.5 mt-1 cursor-pointer rounded border-l-2 border-outline-gray-3 bg-surface-gray-1 px-2 py-1"
              @click.stop="goTo(c.quote.name)"
            >
              <div class="text-xs font-medium text-ink-gray-7">
                {{ userName(c.quote.owner) }}
              </div>
              <div class="truncate text-xs text-ink-gray-5">
                {{ c.quote.text }}
              </div>
            </div>

            <CommentComposer
              v-if="editing === c.name"
              class="my-1"
              :doctype="doctype"
              :docname="docname"
              :initialContent="c.content"
              :submitLabel="__('Save')"
              cancellable
              autofocus
              @submit="(p) => saveEdit(c, p)"
              @cancel="editing = ''"
              @click.stop
            />
            <template v-else>
              <!-- eslint-disable-next-line vue/no-v-html -->
              <div
                class="prose-f text-base leading-6"
                v-html="sanitizeHTML(c.content)"
              />
              <div v-if="c.attachments?.length" class="mt-2 flex flex-wrap gap-1">
                <AttachmentItem
                  v-for="a in c.attachments"
                  :key="a.file_url"
                  :label="a.file_name"
                  :url="a.file_url"
                />
              </div>
            </template>
          </div>

          <div class="mt-1 flex items-center gap-3 px-1 text-xs text-ink-gray-5">
            <Tooltip :text="formatDate(c.creation)">
              <span>{{ __(timeAgo(c.creation)) }}</span>
            </Tooltip>
            <span v-if="c.edited">{{ __('diedit') }}</span>
            <template v-if="selected === c.name">
              <button class="hover:text-ink-gray-8" @click="startReply(c)">
                {{ __('Reply') }}
              </button>
              <template v-if="isMine(c)">
                <button
                  class="hover:text-ink-gray-8"
                  @click="((editing = c.name), (replyTo = null))"
                >
                  {{ __('Edit') }}
                </button>
                <button class="hover:text-ink-red-3" @click="remove(c)">
                  {{ __('Remove') }}
                </button>
              </template>
            </template>
          </div>
        </div>
      </div>
    </div>

    <div class="shrink-0 border-t p-3">
      <!-- Strip balasan ala WhatsApp: yang dibalas nempel di atas kotak tulis -->
      <div
        v-if="replyTo"
        class="mb-1.5 flex items-start gap-2 rounded border-l-2 border-outline-gray-3 bg-surface-gray-2 px-2 py-1"
      >
        <div class="min-w-0 flex-1">
          <div class="text-xs font-medium text-ink-gray-7">
            {{ __('Membalas') }} {{ userName(replyTo.owner) }}
          </div>
          <div class="truncate text-xs text-ink-gray-5">
            {{ replyTo.text }}
          </div>
        </div>
        <FeatherIcon
          name="x"
          class="mt-0.5 h-3.5 cursor-pointer text-ink-gray-5"
          @click="replyTo = null"
        />
      </div>

      <CommentComposer
        :doctype="doctype"
        :docname="docname"
        :placeholder="__('Tulis komentar, @ untuk menyebut orang')"
        @submit="send"
      />
    </div>
  </div>
</template>

<script setup>
import UserAvatar from '@/components/UserAvatar.vue'
import AttachmentItem from '@/components/AttachmentItem.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import CommentComposer from '@/components/CommentComposer.vue'
import { usersStore } from '@/stores/users'
import { createResource, Tooltip, FeatherIcon, call, toast } from 'frappe-ui'
import { ref, nextTick } from 'vue'
import { timeAgo, formatDate, sanitizeHTML } from '@/utils'
import { sessionStore } from '@/stores/session'
import { useRoute } from 'vue-router'

const props = defineProps({
  doctype: { type: String, required: true },
  docname: { type: String, required: true },
})

const { getUser } = usersStore()
const { user } = sessionStore()
const route = useRoute()

const selected = ref('')
const editing = ref('')
const replyTo = ref(null)
const scroller = ref(null)

const comments = createResource({
  url: 'crm_cakra.api.comment.get_comments',
  params: { reference_doctype: props.doctype, reference_name: props.docname },
  auto: true,
  onSuccess: () => nextTick(landing),
})

// Notifikasi mention/balasan membawa hash #<nama komentar>; kalau ada, mendarat
// di komentar itu, kalau tidak ya di pesan terbaru seperti ruang obrolan.
function landing() {
  const target = route.hash.slice(1)
  if (target && document.getElementById(target)) goTo(target)
  else scrollToBottom()
}

function userName(email) {
  return getUser(email)?.full_name || email
}

function isMine(comment) {
  return comment.owner === user.value
}

function scrollToBottom() {
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
}

function startReply(comment) {
  editing.value = ''
  selected.value = ''
  replyTo.value = {
    name: comment.name,
    owner: comment.owner,
    text: comment.content.replace(/<[^>]*>/g, ' ').trim().slice(0, 140),
  }
}

function goTo(name) {
  const el = document.getElementById(name)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('ring-2', 'ring-outline-gray-3')
  setTimeout(() => el.classList.remove('ring-2', 'ring-outline-gray-3'), 1200)
}

async function send({ content, attachments, done }) {
  try {
    await call('crm_cakra.api.comment.add_comment', {
      reference_doctype: props.doctype,
      reference_name: props.docname,
      content,
      attachments,
      parent_comment: replyTo.value?.name || null,
    })
    done()
    replyTo.value = null
    comments.reload()
  } catch (e) {
    done(false)
    toast.error(e.messages?.[0] || e.message || __('Error'))
  }
}

async function saveEdit(comment, { content, done }) {
  try {
    await call('crm_cakra.api.comment.edit_comment', {
      name: comment.name,
      content,
    })
    done()
    editing.value = ''
    comments.reload()
  } catch (e) {
    done(false)
    toast.error(e.messages?.[0] || e.message || __('Error'))
  }
}

async function remove(comment) {
  if (!window.confirm(__('Hapus komentar ini?'))) return
  try {
    await call('crm_cakra.api.comment.delete_comment', { name: comment.name })
    comments.reload()
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Error'))
  }
}
</script>
