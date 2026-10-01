// Konfigurasi daftar apps mobile CRM. Menambah menu = menambah satu entri di
// sini; tidak ada halaman baru yang perlu ditulis (ListPage.vue yang merender).
//
// Semua daftar lewat crm_cakra.api.doc.get_linked_list: search OR lintas field
// dan pembatasan cabang (permission_query_conditions) sudah dikerjakan server,
// jadi apps tidak boleh menegakkan aturan yang sama lagi di sini.
import LeadsIcon from '@/components/Icons/LeadsIcon.vue'
import InquiriesIcon from '@/components/Icons/InquiriesIcon.vue'
import QuotationIcon from '@/components/Icons/QuotationIcon.vue'
import MeetingIcon from '@/components/Icons/MeetingIcon.vue'
import ContactsIcon from '@/components/Icons/ContactsIcon.vue'
import OrganizationsIcon from '@/components/Icons/OrganizationsIcon.vue'
import EstimationIcon from '@/components/Icons/EstimationIcon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import LucideShoppingCart from '~icons/lucide/shopping-cart'
import LucideFileText from '~icons/lucide/file-text'

// Sama persis dengan MobileQuotation.vue -- state quotation bukan doctype
// sendiri jadi warnanya memang ditulis di layar.
const stateColor = (state) =>
  ({
    Inquired: 'text-ink-gray-5',
    Negotiation: 'text-ink-blue-3',
    'Follow Up': 'text-ink-amber-3',
    Win: 'text-ink-green-3',
    Lose: 'text-ink-red-4',
    Converted: 'text-ink-green-3',
  })[state] || 'text-ink-gray-5'

// Peta warna status disalin dari ListView desktop masing-masing supaya satu status
// tidak berganti arti antar layar. Nilai tak dikenal jatuh ke abu-abu, bukan hilang.
const procurementColor = (status) =>
  ({
    Draft: 'text-ink-gray-5',
    Request: 'text-ink-amber-3',
    Reviewing: 'text-ink-blue-3',
    Approve: 'text-ink-green-3',
  })[status] || 'text-ink-gray-5'

const tenderColor = (status) =>
  ({
    Draft: 'text-ink-gray-5',
    Prepared: 'text-ink-blue-3',
    Submitted: 'text-ink-amber-3',
    Inquired: 'text-ink-blue-3',
    Quotation: 'text-ink-amber-3',
    Won: 'text-ink-green-3',
    Lost: 'text-ink-red-4',
    Cancelled: 'text-ink-gray-5',
  })[status] || 'text-ink-gray-5'

const taskColor = (status) =>
  ({
    Backlog: 'text-ink-gray-5',
    Todo: 'text-ink-amber-3',
    'In Progress': 'text-ink-blue-3',
    Done: 'text-ink-green-3',
    Canceled: 'text-ink-red-4',
  })[status] || 'text-ink-gray-5'

const meetingColor = (status) =>
  ({
    Scheduled: 'text-ink-blue-3',
    Visited: 'text-ink-green-3',
    Cancelled: 'text-ink-red-4',
  })[status] || 'text-ink-gray-5'

export const lists = {
  leads: {
    label: 'Leads',
    icon: LeadsIcon,
    doctype: 'CRM Lead',
    fields: ['name', 'lead_name', 'organization', 'status', 'mobile_no', 'modified'],
    filters: { converted: 0 },
    title: (r) => r.lead_name || r.name,
    subtitle: (r) => r.organization || r.mobile_no || r.name,
    badge: (r, s) => ({ label: r.status, class: (r.status && s.getLeadStatus(r.status)?.color) || 'text-ink-gray-5' }),
    route: (r) => ({ name: 'Lead', params: { leadId: r.name } }),
    modal: 'LeadModal',
  },
  inquiries: {
    label: 'Inquiries',
    icon: InquiriesIcon,
    doctype: 'CRM Inquiry',
    fields: ['name', 'organization', 'status', 'job_service', 'inquiry_value', 'modified'],
    title: (r) => r.organization || r.name,
    subtitle: (r) => [r.name, r.job_service].filter(Boolean).join(' - '),
    badge: (r, s) => ({ label: r.status, class: (r.status && s.getInquiryStatus(r.status)?.color) || 'text-ink-gray-5' }),
    route: (r) => ({ name: 'Inquiry', params: { inquiryId: r.name } }),
    newRoute: 'NewInquiry',
  },
  quotations: {
    label: 'Quotations',
    icon: QuotationIcon,
    doctype: 'CRM Quotation',
    fields: ['name', 'account_name', 'state', 'date', 'net_total', 'modified'],
    title: (r) => r.account_name || r.name,
    subtitle: (r) => r.name,
    badge: (r) => ({ label: r.state, class: stateColor(r.state) }),
    route: (r) => ({ name: 'Quotation', params: { quotationId: r.name } }),
    newRoute: 'NewQuotation',
  },
  meetings: {
    label: 'Meetings',
    icon: MeetingIcon,
    doctype: 'CRM Meeting',
    fields: ['name', 'subject', 'organization', 'status', 'meeting_date', 'location'],
    orderBy: 'meeting_date desc',
    dateField: 'meeting_date',
    title: (r) => r.subject || r.name,
    subtitle: (r) => r.organization || r.location || r.name,
    badge: (r) => ({ label: r.status, class: meetingColor(r.status) }),
    modal: 'MeetingModal', // meeting tidak punya halaman detail, cuma modal
  },
  accounts: {
    label: 'Accounts',
    icon: OrganizationsIcon,
    doctype: 'CRM Organization',
    fields: ['name', 'organization_name', 'industry', 'territory', 'modified'],
    title: (r) => r.organization_name || r.name,
    subtitle: (r) => r.industry || r.territory || '',
    route: (r) => ({ name: 'Organization', params: { organizationId: r.name } }),
    modal: 'OrganizationModal',
  },
  estimations: {
    label: 'Estimations',
    icon: EstimationIcon,
    doctype: 'CRM Estimation',
    fields: ['name', 'estimation_no', 'customer_id', 'quo_no', 'validated', 'modified'],
    title: (r) => r.estimation_no || r.name,
    subtitle: (r) => [r.customer_id, r.quo_no].filter(Boolean).join(' - '),
    badge: (r) => ({
      label: r.validated ? 'Validated' : 'Draft',
      class: r.validated ? 'text-ink-green-3' : 'text-ink-gray-5',
    }),
    route: (r) => ({ name: 'Estimation', params: { estimationId: r.name } }),
    newRoute: 'NewEstimation',
  },
  procurement: {
    label: 'Procurement',
    icon: LucideShoppingCart,
    doctype: 'CRM Procurement',
    fields: ['name', 'inquiry', 'account', 'status', 'submitted_on', 'modified'],
    title: (r) => r.inquiry || r.name,
    subtitle: (r) => [r.name, r.account].filter(Boolean).join(' - '),
    badge: (r) => ({ label: r.status, class: procurementColor(r.status) }),
    route: (r) => ({ name: 'ProcurementDoc', params: { procurementId: r.name } }),
  },
  tenders: {
    label: 'Tenders',
    icon: LucideFileText,
    doctype: 'CRM Tender',
    fields: ['name', 'subject', 'organization', 'status', 'closing_date', 'modified'],
    // Tender hidup dari tanggal tutupnya, jadi itu yang ditunjukkan kartunya.
    dateField: 'closing_date',
    dateFormat: 'D MMM YYYY',
    title: (r) => r.subject || r.name,
    subtitle: (r) => r.organization || r.name,
    badge: (r) => ({ label: r.status, class: tenderColor(r.status) }),
    route: (r) => ({ name: 'Tender', params: { tenderId: r.name } }),
  },
  tasks: {
    label: 'Tasks',
    icon: TaskIcon,
    doctype: 'CRM Task',
    fields: ['name', 'title', 'status', 'priority', 'due_date', 'modified'],
    title: (r) => r.title || r.name,
    subtitle: (r) => r.priority || '',
    badge: (r) => ({ label: r.status, class: taskColor(r.status) }),
    // Task dan Note tidak punya halaman sendiri di web -- keduanya dibuka lewat
    // DoctypeModal yang sama, dan modal itu sudah dipasang global di App.vue.
    doctypeModal: { doctype: 'CRM Task', title: 'Task' },
  },
  notes: {
    label: 'Notes',
    icon: NoteIcon,
    doctype: 'FCRM Note',
    fields: ['name', 'title', 'modified'],
    title: (r) => r.title || r.name,
    subtitle: () => '',
    doctypeModal: { doctype: 'FCRM Note', title: 'Note' },
  },
  contacts: {
    label: 'Contacts',
    icon: ContactsIcon,
    doctype: 'Contact',
    fields: ['name', 'first_name', 'last_name', 'company_name', 'mobile_no', 'email_id', 'modified'],
    title: (r) => [r.first_name, r.last_name].filter(Boolean).join(' ') || r.name,
    subtitle: (r) => r.company_name || r.mobile_no || r.email_id || '',
    route: (r) => ({ name: 'Contact', params: { contactId: r.name } }),
    modal: 'ContactModal',
  },
}
