import './index.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createDialog } from './utils/dialogs'
import { initSocket } from './socket'
import router from './router'
import translationPlugin from './translation'
import { notify, notifyError } from './utils/notify'
import App from './App.vue'

import {
  FrappeUI,
  Button,
  Input,
  TextInput,
  FormControl,
  ErrorMessage,
  Dialog,
  Alert,
  Badge,
  setConfig,
  frappeRequest,
  FeatherIcon,
} from 'frappe-ui'

import { telemetryPlugin } from 'frappe-ui/frappe'

let globalComponents = {
  Button,
  TextInput,
  Input,
  FormControl,
  ErrorMessage,
  Dialog,
  Alert,
  Badge,
  FeatherIcon,
}

// create a pinia instance
let pinia = createPinia()

let app = createApp(App)

// Every failed request pops a toast, so a save that fails on a mandatory field
// is visible even when the page shows the error inline.
setConfig('resourceFetcher', (options) =>
  frappeRequest(options).catch((err) => {
    notifyError(err)
    throw err
  }),
)

// frappe.msgprint() on a successful response would otherwise be dropped
setConfig('serverMessagesHandler', (messages) => {
  for (let m of messages) {
    let msg = m
    if (typeof msg === 'string') {
      try {
        msg = JSON.parse(msg)
      } catch (e) {
        msg = { message: m }
      }
    }
    notify(msg.message || msg.title, msg.indicator === 'red' ? 'error' : 'info')
  }
})
app.use(FrappeUI)
app.use(pinia)
app.use(router)
app.use(translationPlugin)
for (let key in globalComponents) {
  app.component(key, globalComponents[key])
}
app.use(telemetryPlugin, { app_name: 'crm' })

app.config.globalProperties.$dialog = createDialog

// call() from frappe-ui bypasses the resourceFetcher above, and plenty of
// callers never catch it -- pick those up here so nothing fails silently.
window.addEventListener('unhandledrejection', (event) => {
  notifyError(event.reason)
})

app.config.errorHandler = (err) => {
  console.error(err)
  notifyError(err)
}

let socket
if (import.meta.env.DEV) {
  frappeRequest({ url: '/api/method/crm.www.crm.get_context_for_dev' }).then(
    (values) => {
      for (let key in values) {
        window[key] = values[key]
      }
      socket = initSocket()
      app.config.globalProperties.$socket = socket
      app.mount('#app')
    },
  )
} else {
  socket = initSocket()
  app.config.globalProperties.$socket = socket
  app.mount('#app')
}

if (import.meta.env.DEV) {
  window.$dialog = createDialog
}
