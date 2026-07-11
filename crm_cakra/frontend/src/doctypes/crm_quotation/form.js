export class CRMQuotation {
  // Dipanggil saat form pertama kali dimuat.
  onLoad() {
    // Number diisi otomatis → read-only. (Subject dibiarkan editable;
    //  Account read-only di-set di doctype.)
    this.setFieldProperty('number', 'read_only', 1)
  }

  // Dipanggil setelah dokumen ter-render — pastikan contact ikut terisi
  // walau untuk quotation lama.
  //
  // Panel "Inquiry Details" TIDAK diisi di sini. setupFormScript() memanggil
  // triggerOnRender() tanpa await, sehingga kegagalan apa pun di sini lenyap
  // sebagai unhandled rejection dan field-nya diam-diam tetap kosong.
  // Pengisiannya ada di pages/Quotation.vue, yang menulis ke objek useDocument
  // yang sama dengan yang dibaca SidePanelLayout.
  async onRender() {
    if (this.doc?.account) {
      await this.fillContactFromAccount()
    }
  }

  // Dipanggil otomatis saat field "inquiry" (Link ke CRM Inquiry) berubah.
  async inquiry() {
    const inquiry = this.value

    // Inquiry dikosongkan → bersihkan field turunan.
    if (!inquiry) {
      this.doc.number = ''
      this.doc.subject = ''
      this.doc.account = ''
      this.doc.account_name = ''
      this.doc.contact_name = ''
      return
    }

    // Ambil organization & subject dari CRM Inquiry yang dipilih.
    const inquiryDoc = await this.call('frappe.client.get_value', {
      doctype: 'CRM Inquiry',
      filters: { name: inquiry },
      fieldname: ['organization', 'organization_name', 'subject'],
    })
    if (!inquiryDoc) return

    this.doc.number = inquiry
    this.doc.subject = inquiryDoc.subject || ''
    this.doc.account = inquiryDoc.organization || ''
    this.doc.account_name = inquiryDoc.organization_name || ''

    // Contact mengikuti organization (account). Panel inquiry di sidebar ikut
    // menyegarkan diri lewat watch di pages/Quotation.vue.
    await this.fillContactFromAccount()
  }

  // Dipanggil otomatis saat field "account" berubah (manual maupun dari inquiry).
  async account() {
    await this.fillContactFromAccount()
  }

  // Helper: isi contact_name dari contact milik account/organization.
  async fillContactFromAccount() {
    const account = this.doc.account
    if (!account) {
      this.doc.contact_name = ''
      return
    }

    const contacts = await this.call('frappe.client.get_list', {
      doctype: 'Contact',
      filters: { company_name: account },
      fields: ['name'],
      order_by: 'creation asc',
      limit_page_length: 1,
    })

    const c = contacts && contacts[0]
    this.doc.contact_name = c ? c.name : ''
  }
}
