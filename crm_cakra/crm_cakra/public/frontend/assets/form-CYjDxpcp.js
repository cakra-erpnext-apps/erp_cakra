class r{onLoad(){this.setFieldProperty("number","read_only",1)}async onRender(){var i;(i=this.doc)!=null&&i.account&&await this.fillContactFromAccount(),await this.fillInquiryDetails()}async inquiry(){const i=this.value;if(!i){this.doc.number="",this.doc.subject="",this.doc.account="",this.doc.account_name="",this.doc.contact_name="",this.setFieldHtml("inquiry_details","");return}const t=await this.call("frappe.client.get_value",{doctype:"CRM Inquiry",filters:{name:i},fieldname:["organization","organization_name","subject"]});t&&(this.doc.number=i,this.doc.subject=t.subject||"",this.doc.account=t.organization||"",this.doc.account_name=t.organization_name||"",await this.fillContactFromAccount(),await this.fillInquiryDetails())}async account(){await this.fillContactFromAccount()}async fillContactFromAccount(){const i=this.doc.account;if(!i){this.doc.contact_name="";return}const t=await this.call("frappe.client.get_list",{doctype:"Contact",filters:{company_name:i},fields:["name"],order_by:"creation asc",limit_page_length:1}),a=t&&t[0];this.doc.contact_name=a?a.name:""}async fillInquiryDetails(){const i=this.doc.inquiry;if(console.log("[CRMQuotation] fillInquiryDetails, inquiry =",i),!i){this.setFieldHtml("inquiry_details","");return}const t=await this.call("crm_cakra.api.quotation.get_inquiry_detail",{name:i});if(console.log("[CRMQuotation] get_inquiry_detail =",t),!t||!t.name){this.setFieldHtml("inquiry_details","");return}const a=o=>String(o).replace(/[&<>"]/g,e=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[e]),n=(o,e)=>e?`<div style="display:flex;justify-content:space-between;gap:8px;padding:3px 0;font-size:13px">
             <span style="color:var(--text-ink-gray-5,#6b7280);flex-shrink:0">${o}</span>
             <span style="color:var(--text-ink-gray-8,#1f272e);text-align:right;word-break:break-word">${a(e)}</span>
           </div>`:"",c=`
      <div>
        ${n("Inquiry",t.name)}
        ${n("Organization",t.organization)}
        ${n("Subject",t.subject)}
        ${n("Status",t.status)}
        ${n("Contact",t.contact_name)}
        ${n("Email",t.email)}
        ${n("Mobile",t.mobile_no)}
        ${n("Territory",t.territory)}
        ${n("Source",t.source)}
        ${n("Owner",t.inquiry_owner)}
      </div>`;this.setFieldHtml("inquiry_details",c),console.log("[CRMQuotation] setFieldHtml inquiry_details panjang =",c.length)}}export{r as CRMQuotation};
//# sourceMappingURL=form-CYjDxpcp.js.map
