// Notifikasi -> route dokumennya. Satu tempat, dipakai panel desktop maupun
// halaman notifikasi mobile.
//
// Dulu aturan ini ditulis dua kali, dan salinan mobile ketinggalan Quotation +
// Procurement: notifikasinya mendarat di route Quotation dengan param `leadId`,
// jadi tautannya mati diam-diam. Pengingat "penawaran belum tersentuh N hari"
// (api/reminders.py) justru yang paling sering dibuka dari HP.
const PARAM_BY_ROUTE = {
  Inquiry: 'inquiryId',
  Quotation: 'quotationId',
  ProcurementDoc: 'procurementId',
}

export function notificationRoute(notification) {
  // Route yang tidak terdaftar jatuh ke Lead -- sama dengan ROUTE_NAME di
  // api/notifications.py, supaya notifikasi lama tetap bisa dibuka.
  const param = PARAM_BY_ROUTE[notification.route_name] || 'leadId'
  return {
    name: notification.route_name,
    params: { [param]: notification.reference_name },
    hash: notification.hash,
  }
}
