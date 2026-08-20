import { createRouter, createWebHistory } from 'vue-router'
import { usersStore } from '@/stores/users'
import { sessionStore } from '@/stores/session'
import { viewsStore } from '@/stores/views'

// Nama dokumen mengandung "/" (LD/4337/CMI/26). Route detail pakai param satu
// segmen supaya garis miringnya ter-encode jadi %2F; link lama yang masih polos
// ditangkap di sini lalu dialihkan ke bentuk ter-encode.
const legacySlashRedirect = (prefix, name, param) => ({
  path: `${prefix}/:legacyName(.*)`,
  redirect: (to) => ({
    name,
    params: { [param]: to.params.legacyName },
    query: to.query,
    hash: to.hash,
  }),
})

const routes = [
  {
    path: '/',
    name: 'Home',
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: () => import('@/pages/MobileNotification.vue'),
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/pages/Dashboard.vue'),
  },
  {
    path: '/assistant',
    name: 'Assistant',
    component: () => import('@/pages/Assistant.vue'),
  },
  {
    path: '/manual',
    name: 'ManualBook',
    component: () => import('@/pages/ManualBook.vue'),
  },
  {
    alias: '/leads',
    path: '/leads/view/:viewType?',
    name: 'Leads',
    component: () => import('@/pages/Leads.vue'),
  },
  {
    path: '/leads/:leadId',
    name: 'Lead',
    component: () => import(`@/pages/${handleMobileView('Lead')}.vue`),
    props: true,
  },
  legacySlashRedirect('/leads', 'Lead', 'leadId'),
  {
    alias: '/inquiries',
    path: '/inquiries/view/:viewType?',
    name: 'Inquiries',
    meta: { label: 'Inquiry' },
    component: () => import('@/pages/Inquiries.vue'),
  },
  {
    path: '/inquiries/new',
    name: 'NewInquiry',
    component: () => import('@/pages/InquiryNew.vue'),
  },
  {
    path: '/inquiries/:inquiryId',
    name: 'Inquiry',
    component: () => import(`@/pages/${handleMobileView('Inquiry')}.vue`),
    props: true,
  },
  legacySlashRedirect('/inquiries', 'Inquiry', 'inquiryId'),
  {
    alias: '/quotations',
    path: '/quotations/view/:viewType?',
    name: 'Quotations',
    component: () => import('@/pages/Quotations.vue'),
  },
  {
    path: '/procurement',
    name: 'Procurement',
    component: () => import('@/pages/Procurement.vue'),
  },
  {
    alias: '/products',
    path: '/products/view/:viewType?',
    name: 'Products',
    component: () => import('@/pages/Products.vue'),
  },
  {
    alias: '/locations',
    path: '/locations/view/:viewType?',
    name: 'Locations',
    component: () => import('@/pages/Locations.vue'),
  },
  {
    alias: '/cost-components',
    path: '/cost-components/view/:viewType?',
    name: 'CostComponents',
    component: () => import('@/pages/CostComponents.vue'),
  },
  {
    alias: '/cost-types',
    path: '/cost-types/view/:viewType?',
    name: 'CostTypes',
    component: () => import('@/pages/CostTypes.vue'),
  },
  {
    path: '/cost-components/new',
    name: 'NewCostComponent',
    component: () => import('@/pages/CostComponentNew.vue'),
  },
  {
    path: '/cost-components/:componentId',
    name: 'CostComponent',
    component: () => import('@/pages/CostComponent.vue'),
    props: true,
  },
  {
    path: '/quotations/new',
    name: 'NewQuotation',
    component: () => import('@/pages/QuotationNew.vue'),
  },
  {
    path: '/quotations/:quotationId',
    name: 'Quotation',
    component: () => import(`@/pages/${handleMobileView('Quotation')}.vue`),
    props: true,
  },
  legacySlashRedirect('/quotations', 'Quotation', 'quotationId'),
  {
    alias: '/meetings',
    path: '/meetings/view/:viewType?',
    name: 'Meetings',
    component: () => import('@/pages/Meetings.vue'),
  },
  {
    path: '/meetings/attendance',
    name: 'MeetingAttendance',
    component: () => import('@/pages/MeetingAttendance.vue'),
  },
  {
    // Halaman Meetings yang langsung terbuka dalam mode kalender (menu sidebar Calendar).
    path: '/meetings/calendar',
    name: 'MeetingsCalendar',
    component: () => import('@/pages/Meetings.vue'),
  },
  {
    alias: '/estimations',
    path: '/estimations/view/:viewType?',
    name: 'Estimations',
    component: () => import('@/pages/Estimations.vue'),
  },
  {
    path: '/estimations/new',
    name: 'NewEstimation',
    component: () => import('@/pages/EstimationNew.vue'),
  },
  {
    path: '/estimations/:estimationId',
    name: 'Estimation',
    component: () => import(`@/pages/${handleMobileView('Estimation')}.vue`),
    props: true,
  },
  legacySlashRedirect('/estimations', 'Estimation', 'estimationId'),
  {
    alias: '/notes',
    path: '/notes/view/:viewType?',
    name: 'Notes',
    component: () => import('@/pages/Notes.vue'),
  },
  {
    alias: '/tasks',
    path: '/tasks/view/:viewType?',
    name: 'Tasks',
    component: () => import('@/pages/Tasks.vue'),
  },
  {
    alias: '/contacts',
    path: '/contacts/view/:viewType?',
    name: 'Contacts',
    component: () => import('@/pages/Contacts.vue'),
  },
  {
    path: '/contacts/:contactId',
    name: 'Contact',
    component: () => import(`@/pages/${handleMobileView('Contact')}.vue`),
    props: true,
  },
  {
    alias: '/organizations',
    path: '/organizations/view/:viewType?',
    name: 'Organizations',
    component: () => import('@/pages/Organizations.vue'),
  },
  {
    path: '/organizations/:organizationId',
    name: 'Organization',
    component: () => import(`@/pages/${handleMobileView('Organization')}.vue`),
    props: true,
  },
  {
    alias: '/call-logs',
    path: '/call-logs/view/:viewType?',
    name: 'Call Logs',
    component: () => import('@/pages/CallLogs.vue'),
  },
  {
    path: '/data-import',
    name: 'DataImportList',
    component: () => import('@/pages/DataImport.vue'),
  },
  {
    path: '/data-import/doctype/:doctype',
    name: 'NewDataImport',
    component: () => import('@/pages/DataImport.vue'),
    props: true,
  },
  {
    path: '/data-import/:importName',
    name: 'DataImport',
    component: () => import('@/pages/DataImport.vue'),
    props: true,
  },
  {
    path: '/welcome',
    name: 'Welcome',
    component: () => import('@/pages/Welcome.vue'),
  },
  {
    path: '/:invalidpath',
    name: 'Invalid Page',
    component: () => import('@/pages/InvalidPage.vue'),
  },
  {
    path: '/not-permitted',
    name: 'Not Permitted',
    component: () => import('@/pages/NotPermitted.vue'),
  },
]

const handleMobileView = (componentName) => {
  return window.innerWidth < 768 ? `Mobile${componentName}` : componentName
}

let router = createRouter({
  history: createWebHistory('/crm'),
  routes,
})

router.beforeEach(async (to, from, next) => {
  router.previousRoute = from

  const { isLoggedIn } = sessionStore()
  const { users, isCrmUser } = usersStore()

  if (isLoggedIn && !users.fetched) {
    try {
      await users.promise
    } catch (error) {
      console.error('Error loading users', error)
    }
  }

  if (isLoggedIn && to.name !== 'Not Permitted' && !isCrmUser()) {
    next({ name: 'Not Permitted' })
  } else if (to.name === 'Home' && isLoggedIn) {
    // Halaman pembuka CRM = Dashboard (dulu: default view dari viewsStore).
    next({ name: 'Dashboard' })
  } else if (!isLoggedIn) {
    window.location.href = '/login?redirect-to=/crm'
  } else if (to.matched.length === 0) {
    next({ name: 'Invalid Page' })
  } else if (['Inquiry', 'Lead'].includes(to.name) && !to.hash) {
    // Buka selalu di tab Data (sama dengan defaultTab di useActiveTabManager).
    next({ ...to, hash: '#data' })
  } else if (
    [
      'Leads',
      'Inquiries',
      'Contacts',
      'Organizations',
      'Quotations',
      'Meetings',
      'Estimations',
      'Notes',
      'Tasks',
      'Call Logs',
    ].includes(to.name) &&
    !to.query?.view
  ) {
    const { views, standardViews, getDefaultView } = viewsStore()
    await views.promise

    const viewType = to.params?.viewType ?? ''
    const standardViewTypes = ['list', 'kanban', 'group_by']

    if (!viewType) {
      const doctypeMap = {
        Leads: 'CRM Lead',
        Inquiries: 'CRM Inquiry',
        Contacts: 'Contact',
        Organizations: 'CRM Organization',
        Quotations: 'CRM Quotation',
        Meetings: 'CRM Meeting',
        Estimations: 'CRM Estimation',
        Notes: 'FCRM Note',
        Tasks: 'CRM Task',
        'Call Logs': 'CRM Call Log',
      }

      const doctype = doctypeMap[to.name]
      let defaultViewType = 'list'

      let globalDefault = getDefaultView()
      if (globalDefault && globalDefault.route_name === to.name) {
        defaultViewType = globalDefault.type || 'list'
        if (globalDefault.name && !globalDefault.is_standard) {
          next({
            name: to.name,
            params: { viewType: defaultViewType },
            query: { ...to.query, view: globalDefault.name },
          })
          return
        }
      }

      for (const viewType of standardViewTypes) {
        const standardView = standardViews.value?.[doctype + ' ' + viewType]
        if (standardView?.is_default) {
          defaultViewType = viewType
          break
        }
      }

      next({
        name: to.name,
        params: { viewType: defaultViewType },
        query: to.query,
      })
    } else if (!standardViewTypes.includes(viewType)) {
      const viewNameOrLabel = viewType

      let view = views.data?.find(
        (v) => v.name == viewNameOrLabel || v.label === viewNameOrLabel,
      )

      if (view) {
        next({
          name: to.name,
          params: { viewType: view.type || 'list' },
          query: { ...to.query, view: view.name },
        })
      } else {
        next({
          name: to.name,
          params: { viewType: 'list' },
          query: to.query,
        })
      }
    } else {
      next()
    }
  } else {
    next()
  }
})

export default router
