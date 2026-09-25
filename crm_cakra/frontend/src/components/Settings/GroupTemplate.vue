<template>
  <div class="flex h-full flex-col gap-6 px-6 py-8 text-ink-gray-8">
    <div class="flex flex-col gap-1 px-2">
      <h2 class="flex h-5 gap-2 text-xl font-semibold leading-none">
        {{ __('Group Template') }}
      </h2>
      <p class="text-p-base text-ink-gray-6">
        {{
          __(
            'Pick which email template each flow uses. Leave it empty to use the built-in wording',
          )
        }}
      </p>
    </div>

    <div class="flex flex-1 flex-col overflow-y-auto">
      <div
        v-for="(group, i) in groups"
        :key="group.field"
        class="flex flex-col gap-3 px-2 py-3"
        :class="i ? 'border-t border-outline-gray-modals' : ''"
      >
        <div class="flex items-center justify-between gap-4">
          <div class="flex flex-col">
            <div class="truncate text-p-base font-medium text-ink-gray-7">
              {{ __(group.label) }}
            </div>
            <div class="text-p-sm text-ink-gray-5">
              {{ __(group.description) }}
            </div>
          </div>
          <div class="w-72 shrink-0">
            <Link
              :value="settings.doc[group.field]"
              doctype="Email Template"
              :placeholder="__('Built-in wording')"
              @change="(v) => pilih(group.field, v)"
            />
          </div>
        </div>

        <!-- Nama field yang bisa dipakai di templatenya. Tanpa daftar ini orang
             harus menebak, dan Jinja yang salah tulis berakhir jadi email
             bawaan tanpa penjelasan. -->
        <div class="text-p-sm text-ink-gray-5">
          {{ __('Available fields') }}:
          <span class="font-mono">{{ group.fields.join(', ') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import Link from '@/components/Controls/Link.vue'
import { getSettings } from '@/stores/settings'
import { toast } from 'frappe-ui'

const { _settings: settings } = getSettings()

// Satu baris per alur yang mengirim email. Menambah alur baru nanti cukup
// menambah field Link di FCRM Settings dan satu baris di sini.
const groups = [
  {
    field: 'procurement_email_template',
    label: 'Procurement',
    description:
      'Sent when Submit to Procurement is sent. The Check button in the template opens the procurement document in CRM',
    fields: [
      'procurement',
      'inquiry',
      'account',
      'route',
      'inquiry_date',
      'requester',
      'remark',
      'link',
    ],
  },
]

function pilih(field, value) {
  settings.doc[field] = value || ''
  settings.save.submit(null, {
    onSuccess: () => toast.success(__('Setting updated successfully')),
  })
}
</script>
