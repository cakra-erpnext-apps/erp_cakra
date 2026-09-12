<template>
  <div class="flex h-full flex-col gap-6 py-8 px-6 text-ink-gray-8">
    <div class="flex flex-col gap-1 px-2">
      <h2 class="flex gap-2 text-xl font-semibold leading-none h-5">
        {{ __('General Settings') }}
      </h2>
      <p class="text-p-base text-ink-gray-6">
        {{ __('Configure general settings for your application') }}
      </p>
    </div>

    <div class="flex-1 flex flex-col overflow-y-auto">
      <div class="flex items-center justify-between py-3 px-2">
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7 truncate">
            {{ __('Update timestamp on new communication') }}
          </div>
          <div class="text-p-sm text-ink-gray-5 truncate">
            {{
              __(
                'Update the modified timestamp on new email communication & comments for leads & inquiries',
              )
            }}
          </div>
        </div>
        <div>
          <Switch
            v-model="settings.doc.update_timestamp_on_new_communication"
            size="sm"
            @click.stop="toggle('update_timestamp_on_new_communication')"
          />
        </div>
      </div>
      <div class="h-px border-t mx-2 border-outline-gray-modals" />
      <div class="flex gap-4 items-center justify-between py-3 px-2">
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7 truncate">
            {{ __('Mark lead/inquiry as replied on response') }}
          </div>
          <div class="text-p-sm text-ink-gray-5">
            {{
              __(
                'Automatically sets Communication Status to “Replied” for the lead or inquiry when a response is received. Applies only when SLA is enabled',
              )
            }}
          </div>
        </div>
        <div>
          <Switch
            v-model="settings.doc.auto_mark_replied_on_response"
            size="sm"
            @click.stop="toggle('auto_mark_replied_on_response')"
          />
        </div>
      </div>
      <div class="h-px border-t mx-2 border-outline-gray-modals" />
      <div class="flex gap-4 items-center justify-between py-3 px-2">
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7 truncate">
            {{ __('Assistant CRM') }}
          </div>
          <div class="text-p-sm text-ink-gray-5">
            {{
              __(
                'Show the Assistant menu (a personal chat assistant per user) at the top of the sidebar',
              )
            }}
          </div>
        </div>
        <div>
          <Switch
            v-model="settings.doc.enable_crm_assistant"
            size="sm"
            @click.stop="toggle('enable_crm_assistant')"
          />
        </div>
      </div>
      <div class="h-px border-t mx-2 border-outline-gray-modals" />
      <div class="flex gap-4 items-center justify-between py-3 px-2">
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7 truncate">
            {{ __('Reopen lead/inquiry on new communication') }}
          </div>
          <div class="text-p-sm text-ink-gray-5">
            {{
              __(
                'Automatically sets Communication Status to “Open” for the lead or inquiry when a new communication is created. Applies only when SLA is enabled',
              )
            }}
          </div>
        </div>
        <div>
          <Switch
            v-model="settings.doc.auto_reopen_on_new_communication"
            size="sm"
            @click.stop="toggle('auto_reopen_on_new_communication')"
          />
        </div>
      </div>
      <div class="h-px border-t mx-2 border-outline-gray-modals" />
      <div class="flex gap-4 items-center justify-between py-3 px-2">
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7 truncate">
            {{ __('Use Items Group') }}
          </div>
          <div class="text-p-sm text-ink-gray-5">
            {{
              __(
                'Item Group for the Items table of Cost Component and the Expense table of Estimation. Set it in ERPNext Custom Setting > Expedition. Empty means every item is allowed',
              )
            }}
          </div>
        </div>
        <div class="w-56 shrink-0">
          <span class="text-p-base text-ink-gray-7">
            {{ expenseItemGroups.join(', ') || __('All items') }}
          </span>
        </div>
      </div>
      <div class="h-px border-t mx-2 border-outline-gray-modals" />
      <div class="flex gap-4 items-center justify-between py-3 px-2">
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7 truncate">
            {{ __('Follow-up reminders') }}
          </div>
          <div class="text-p-sm text-ink-gray-5">
            {{
              __(
                'Send a daily reminder for quotations left untouched and inquiries past their expected closure date. Goes to the assignee, or the owner when nobody is assigned',
              )
            }}
          </div>
        </div>
        <div>
          <Switch
            v-model="settings.doc.enable_reminders"
            size="sm"
            @click.stop="toggle('enable_reminders')"
          />
        </div>
      </div>
      <div
        v-if="settings.doc.enable_reminders"
        class="flex gap-4 items-center justify-between py-3 px-2"
      >
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7 truncate">
            {{ __('Quotation idle days') }}
          </div>
          <div class="text-p-sm text-ink-gray-5">
            {{
              __(
                'A quotation with no decision and no change for this many days counts as idle',
              )
            }}
          </div>
        </div>
        <div class="w-24 shrink-0">
          <FormControl
            v-model="settings.doc.quotation_idle_days"
            type="number"
            size="sm"
            @change="save()"
          />
        </div>
      </div>
      <div
        v-if="settings.doc.enable_reminders"
        class="flex gap-4 items-center justify-between py-3 px-2"
      >
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7 truncate">
            {{ __('Reminder repeat days') }}
          </div>
          <div class="text-p-sm text-ink-gray-5">
            {{ __('Wait this long before nagging about the same document again. 0 means every day') }}
          </div>
        </div>
        <div class="w-24 shrink-0">
          <FormControl
            v-model="settings.doc.reminder_repeat_days"
            type="number"
            size="sm"
            @change="save()"
          />
        </div>
      </div>
      <div class="h-px border-t mx-2 border-outline-gray-modals" />
      <div class="flex gap-4 items-center justify-between py-3 px-2">
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7 truncate">
            {{ __('Margin approval') }}
          </div>
          <div class="text-p-sm text-ink-gray-5">
            {{
              __(
                'A quotation with a thin margin cannot be printed until it is approved. Margin is measured against cost, not Base Price',
              )
            }}
          </div>
        </div>
        <div>
          <Switch
            v-model="settings.doc.enable_margin_approval"
            size="sm"
            @click.stop="toggle('enable_margin_approval')"
          />
        </div>
      </div>
      <div
        v-if="settings.doc.enable_margin_approval"
        class="flex gap-4 items-center justify-between py-3 px-2"
      >
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7 truncate">
            {{ __('Needs Sales Manager below (%)') }}
          </div>
          <div class="text-p-sm text-ink-gray-5">
            {{ __('Below this margin the quotation needs a Sales Manager to approve') }}
          </div>
        </div>
        <div class="w-24 shrink-0">
          <FormControl
            v-model="settings.doc.margin_approval_percent"
            type="number"
            size="sm"
            @change="save()"
          />
        </div>
      </div>
      <div
        v-if="settings.doc.enable_margin_approval"
        class="flex gap-4 items-center justify-between py-3 px-2"
      >
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7 truncate">
            {{ __('Escalates below (%)') }}
          </div>
          <div class="text-p-sm text-ink-gray-5">
            {{ __('Below this margin it takes a Sales Master Manager instead') }}
          </div>
        </div>
        <div class="w-24 shrink-0">
          <FormControl
            v-model="settings.doc.margin_escalation_percent"
            type="number"
            size="sm"
            @change="save()"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { getSettings } from '@/stores/settings'
import { FormControl, Switch, toast } from 'frappe-ui'

const { _settings: settings } = getSettings()

// Cerminan saja: sumbernya ERPNext Custom Setting > Expedition ("Item in Expense always
// use Item Group") -- satu setting untuk tabel Items Cost Component dan grid Expense di
// Estimation. Dulu field sendiri di sini (use_items_group) dan gampang melenceng.
const expenseItemGroups = (window.cmi_item_groups || {}).expense || []

function save() {
  settings.save.submit(null, {
    onSuccess: () => toast.success(__('Setting updated successfully')),
  })
}

function toggle(settingKey) {
  settings.save.submit(null, {
    onSuccess: () => {
      toast.success(
        settings.doc[settingKey]
          ? __('Setting enabled successfully')
          : __('Setting disabled successfully'),
      )
    },
  })
}
</script>
