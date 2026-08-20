<template>
  <div class="flex h-full flex-col gap-6 p-8 text-ink-gray-8">
    <div class="flex flex-col gap-1">
      <h2 class="flex gap-2 text-xl font-semibold leading-none h-5">
        {{ __('List Views') }}
      </h2>
      <p class="text-p-base text-ink-gray-6">
        {{
          __(
            'Every list remembers the columns you last used. Reset it to go back to the default columns of each menu.',
          )
        }}
      </p>
    </div>

    <div class="flex flex-col items-start gap-3">
      <Button
        :label="__('Reset my list views')"
        :loading="resetViews.loading && !allUsers"
        @click="reset(false)"
      />
      <Button
        v-if="isManager()"
        :label="__('Reset list views of all users')"
        theme="red"
        :loading="resetViews.loading && allUsers"
        @click="reset(true)"
      />
      <div v-if="message" class="text-p-base text-ink-gray-6">
        {{ message }}
      </div>
      <ErrorMessage v-if="error" :message="error" />
    </div>
  </div>
</template>

<script setup>
import { ErrorMessage, createResource } from 'frappe-ui'
import { usersStore } from '@/stores/users'
import { ref } from 'vue'

const { isManager } = usersStore()

const message = ref('')
const error = ref('')
const allUsers = ref(false)

const resetViews = createResource({
  url: 'crm_cakra.api.views.reset_standard_views',
})

function reset(forAllUsers) {
  message.value = ''
  error.value = ''
  allUsers.value = forAllUsers
  resetViews.submit(
    { all_users: forAllUsers },
    {
      onSuccess(count) {
        message.value = __('{0} list views reset. Reload to see them.', [count])
      },
      onError(err) {
        error.value = err.messages?.join('\n') || err.message
      },
    },
  )
}
</script>
