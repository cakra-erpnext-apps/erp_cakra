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
    // KM juga TIDAK diisi di sini, alasan yang sama dengan Inquiry Details:
    // lihat watcher-nya di pages/Quotation.vue.
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
      this.doc.loading = ''
      this.doc.unloading = ''
      return
    }

    // Ambil organization, subject, & rute dari CRM Inquiry yang dipilih.
    const inquiryDoc = await this.call('frappe.client.get_value', {
      doctype: 'CRM Inquiry',
      filters: { name: inquiry },
      fieldname: [
        'organization',
        'organization_name',
        'subject',
        'origin',
        'destination',
      ],
    })
    if (!inquiryDoc) return

    this.doc.number = inquiry
    this.doc.subject = inquiryDoc.subject || ''
    this.doc.account = inquiryDoc.organization || ''
    this.doc.account_name = inquiryDoc.organization_name || ''

    // Rute inquiry -> rute quotation. Keduanya Link ke Fleet Location, tapi
    // inquiry lama hasil import masih menyimpan teks yang belum tentu terdaftar.
    //
    // Teks yang tidak terdaftar sengaja TIDAK disalin. Dulu disalin apa adanya
    // supaya "terlihat", dan akibatnya quotation lahir dalam keadaan tidak bisa
    // disave sama sekali: validasi link menolak SELURUH dokumen, bukan cuma
    // field itu, jadi field lain pun ikut terkunci. Lebih baik kosong dan
    // dipilih user daripada terisi tapi mati.
    this.doc.loading = await this.locationOrBlank(inquiryDoc.origin)
    this.doc.unloading = await this.locationOrBlank(inquiryDoc.destination)

    // Contact mengikuti organization (account). Panel inquiry di sidebar ikut
    // menyegarkan diri lewat watch di pages/Quotation.vue.
    await this.fillContactFromAccount()
  }

  // Dipanggil otomatis saat field "account" berubah (manual maupun dari inquiry).
  async account() {
    await this.fillContactFromAccount()
  }

  // Helper: kembalikan teks itu hanya kalau benar-benar ada di master Fleet
  // Location, selain itu kosong. Sengaja cocok persis, tidak menebak-nebak:
  // salah tebak lokasi berarti salah jarak dan salah harga.
  async locationOrBlank(text) {
    const name = (text || '').trim()
    if (!name) return ''
    const r = await this.call('frappe.client.get_value', {
      doctype: 'Fleet Location',
      filters: { name },
      fieldname: 'name',
    })
    return r?.name || ''
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
