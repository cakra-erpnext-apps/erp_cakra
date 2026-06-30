# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as assign
from frappe.model.document import Document

from crm_cakra.api.exchange_rate import get_exchange_rate
from crm_cakra.fcrm.doctype.crm_service_level_agreement.utils import get_sla
from crm_cakra.fcrm.doctype.crm_status_change_log.crm_status_change_log import (
    add_status_change_log,
)
from crm_cakra.fcrm.doctype.utils import add_or_remove_lost_reason_section_in_sidepanel


class CRMInquiry(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from crm_cakra.fcrm.doctype.crm_contacts.crm_contacts import CRMContacts
        from crm_cakra.fcrm.doctype.crm_inquiry_transportation_mode.crm_inquiry_transportation_mode import CRMInquiryTransportationMode
        from crm_cakra.fcrm.doctype.crm_inquiry_type_inquiry.crm_inquiry_type_inquiry import CRMInquiryTypeInquiry
        from crm_cakra.fcrm.doctype.crm_products.crm_products import CRMProducts
        from crm_cakra.fcrm.doctype.crm_rolling_response_time.crm_rolling_response_time import CRMRollingResponseTime
        from crm_cakra.fcrm.doctype.crm_status_change_log.crm_status_change_log import CRMStatusChangeLog
        from frappe.types import DF

        annual_revenue: DF.Currency
        business_unit: DF.Literal["", "EMKL (TRUCKING DOMESTIK NON ISOTANK)", "FF (EXPORT/IMPORT CONTAINER DRY)", "ISO (LOCAL/ DOMESTIK ISOTANK)", "LOG (CONTRACT LOGISTICS)", "PCP (EXPORT ISOTANK)", "PKGOLEO (PRODUCT)"]
        cargo_commodity: DF.SmallText | None
        cargo_packaging: DF.Data | None
        cargo_weight: DF.Data | None
        closed_date: DF.Date | None
        communication_status: DF.Link | None
        contact: DF.Link | None
        contacts: DF.Table[CRMContacts]
        costing_procurement: DF.Currency
        currency: DF.Link | None
        date_shipment: DF.Date | None
        destination: DF.SmallText | None
        email: DF.Data | None
        estimasi_tarif: DF.Currency
        exchange_rate: DF.Float
        expected_closure_date: DF.Date | None
        expected_inquiry_value: DF.Currency
        first_name: DF.Data | None
        first_responded_on: DF.Datetime | None
        first_response_time: DF.Duration | None
        gender: DF.Link | None
        incoterms: DF.Literal["", "EXW (EX WOKRS)", "FCA (FREE CARRIER)", "FAS (FREE ALONGSIDE SHIP)", "FOB (FREE ON BOARD)", "CFR (COST & FREIGHT)", "CIF (COST, INSURANCE & FREIGHT)", "CPT (COST PAID TO)", "CIP (CARRIER, INSURANCE PAID TO)", "DPU (DELIVERED AT PLACE UNLOADED)", "DAP (DELIVERED AT PLACE)", "DDP (DELIVERED DUTY PAID)"]
        industry: DF.Link | None
        inquiry_date: DF.Date | None
        inquiry_owner: DF.Link | None
        inquiry_value: DF.Currency
        is_void: DF.Check
        job_service: DF.Literal["", "Trukcing Container 40ft", "Trucking Isotank 25kl", "Door To Port Flexitank 18kl", "Trucking Container 20ft", "Export Service Container 20 Dry", "Export Service Container 40 Dry", "Export Service Container 20 Reefer", "Export Service Container 40 Reefer", "Door To Door Isotank", "Door To Door Container 20 Dry", "Door To Door Container 40 Dry", "Door To Door Container 20 Reefer", "Doot To Door Container 40 Reefer", "Freight LCL", "Freight", "Container Storage", "Isotank", "Container - Container 20 Dry", "Container - Container 40 Dry", "Container - Container 20 & 40 Dry", "Container - Container 20 & 40 Reefer", "Container - Container 20 Reefer", "Container - Container 40 Reefer", "EMKL & Trucking - Container 20 Dry", "EMKL & Trucking - Container 40 Dry", "EMKL & Trucking - Container 20 & 40 Dry", "EMKL & Trucking", "EMKL & Trucking - Container 20 Reefer", "EMKL & Trucking - Container 40 Reefer", "Import Door To Door", "EMKL & Trucking - Isotank", "Door To Port Isotank", "Local Service", "EMKL & Trucking - Isotank T75", "Impor Trucking Container", "Export Service Isotank", "Impor Service Isotank", "Impor Service Container", "Door to Door Flexitank", "Port To Port", "Port To Door Isotank", "Other Product", "Product Packaging", "Product Oleochemical", "Repair Container", "Toeslagh", "Export Service Flexitank", "Trucking + Rental Isotank", "Door To Port", "Cleaning Isotank", "Export Isotank & Flexibag"]
        job_title: DF.Data | None
        last_name: DF.Data | None
        last_responded_on: DF.Datetime | None
        last_response_time: DF.Duration | None
        lead: DF.Link | None
        lead_name: DF.Data | None
        lost_notes: DF.Text | None
        lost_reason: DF.Link | None
        mobile_no: DF.Data | None
        naming_series: DF.Literal["INQ/.####./CMI/.YY."]
        net_total: DF.Currency
        next_step: DF.Data | None
        no_of_employees: DF.Literal["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"]
        organization: DF.Link | None
        organization_name: DF.Data
        origin: DF.SmallText | None
        phone: DF.Data | None
        port_pol_destination_detail_address: DF.SmallText | None
        probability: DF.Percent
        products: DF.Table[CRMProducts]
        qty: DF.Float
        qty_volume: DF.Data | None
        rate: DF.Currency
        remarks: DF.Text | None
        response_by: DF.Datetime | None
        rolling_responses: DF.Table[CRMRollingResponseTime]
        salutation: DF.Link | None
        service_type: DF.Literal["", "New Customer", "New Job Service", "New Product", "Existing Job Service", "Existing Product"]
        shipper_consignee: DF.Data | None
        sla: DF.Link | None
        sla_creation: DF.Datetime | None
        sla_status: DF.Literal["", "First Response Due", "Rolling Response Due", "Failed", "Fulfilled"]
        source: DF.Link | None
        status: DF.Link
        status_cargo: DF.Data | None
        status_change_log: DF.Table[CRMStatusChangeLog]
        subject: DF.Data | None
        territory: DF.Link | None
        total: DF.Currency
        transportation_mode: DF.TableMultiSelect[CRMInquiryTransportationMode]
        type_inquiry: DF.TableMultiSelect[CRMInquiryTypeInquiry]
        void_at: DF.Datetime | None
        void_by: DF.Link | None
        void_reason: DF.SmallText | None
        website: DF.Data | None
    # end: auto-generated types

    def autoname(self):
        from frappe.model.naming import make_autoname

        # Format: INQ/0001/CMI/26 — counter di-key per tahun ("INQ-YY-")
        # sehingga otomatis reset tiap pergantian tahun.
        yy = frappe.utils.now_datetime().strftime("%y")
        counter = make_autoname(f"INQ-{yy}-.####.").split("-")[-1]
        self.name = f"INQ/{counter}/CMI/{yy}"

    def before_validate(self):
        self.set_sla()

    def validate(self):
        self.validate_status()
        self.set_primary_contact()
        self.set_primary_email_mobile_no()
        if (
            not self.is_new()
            and self.has_value_changed("inquiry_owner")
            and self.inquiry_owner
        ):
            self.share_with_agent(self.inquiry_owner)
            self.assign_agent(self.inquiry_owner)
        if self.has_value_changed("status"):
            add_status_change_log(self)
            if frappe.db.get_value("CRM Inquiry Status", self.status, "type") == "Won":
                self.closed_date = frappe.utils.nowdate()
        self.validate_forecasting_fields()
        self.validate_lost_reason()
        self.update_exchange_rate()

    def after_insert(self):
        if self.inquiry_owner:
            if self.inquiry_owner != frappe.session.user:
                self.share_with_agent(self.inquiry_owner)
            self.assign_agent(self.inquiry_owner)

    def before_save(self):
        self.apply_sla()

    def validate_status(self):
        if self.is_new() and not self.status:
            if frappe.db.exists("CRM Inquiry Status", "Qualification"):
                self.status = "Qualification"
            else:
                self.status = frappe.get_all(
                    "CRM Inquiry Status", {"type": "Open"}, pluck="name"
                )[0]

    def set_primary_contact(self, contact=None):
        if not self.contacts:
            return

        if not contact and len(self.contacts) == 1:
            self.contacts[0].is_primary = 1
        elif contact:
            for d in self.contacts:
                if d.contact == contact:
                    d.is_primary = 1
                else:
                    d.is_primary = 0

    def set_primary_email_mobile_no(self):
        if not self.contacts:
            self.email = ""
            self.mobile_no = ""
            self.phone = ""
            return

        if len([contact for contact in self.contacts if contact.is_primary]) > 1:
            frappe.throw(
                _("Only one {0} can be set as primary.").format(frappe.bold("Contact"))
            )

        primary_contact_exists = False
        for d in self.contacts:
            if d.is_primary == 1:
                primary_contact_exists = True
                self.email = d.email.strip() if d.email else ""
                self.mobile_no = d.mobile_no.strip() if d.mobile_no else ""
                self.phone = d.phone.strip() if d.phone else ""
                break

        if not primary_contact_exists:
            self.email = ""
            self.mobile_no = ""
            self.phone = ""

    def assign_agent(self, agent):
        if not agent:
            return

        assignees = self.get_assigned_users()
        if assignees:
            for assignee in assignees:
                if agent == assignee:
                    # the agent is already set as an assignee
                    return

        assign(
            {"assign_to": [agent], "doctype": "CRM Inquiry", "name": self.name},
            ignore_permissions=True,
        )

    def share_with_agent(self, agent):
        if not agent:
            return

        docshares = frappe.get_all(
            "DocShare",
            filters={"share_name": self.name, "share_doctype": self.doctype},
            fields=["name", "user"],
        )

        shared_with = [d.user for d in docshares] + [agent]

        for user in shared_with:
            if user == agent and not frappe.db.exists(
                "DocShare",
                {"user": agent, "share_name": self.name, "share_doctype": self.doctype},
            ):
                frappe.share.add_docshare(
                    self.doctype,
                    self.name,
                    agent,
                    write=1,
                    flags={"ignore_share_permission": True},
                )
            elif user != agent:
                frappe.share.remove(
                    self.doctype,
                    self.name,
                    user,
                    flags={"ignore_share_permission": True, "ignore_permissions": True},
                )

    def set_sla(self):
        """
        Find an SLA to apply to the inquiry.
        """
        if self.sla:
            return

        sla = get_sla(self)
        if not sla:
            self.first_responded_on = None
            self.first_response_time = None
            return
        self.sla = sla.name

    def apply_sla(self):
        """
        Apply SLA if set.
        """
        if not self.sla:
            return
        sla = frappe.get_last_doc("CRM Service Level Agreement", {"name": self.sla})
        if sla:
            sla.apply(self)

    def update_closed_date(self):
        """
        Update the closed date based on the "Won" status.
        """
        if self.status == "Won" and not self.closed_date:
            self.closed_date = frappe.utils.nowdate()

    def update_default_probability(self):
        """
        Update the default probability based on the status.
        """
        if not self.probability or self.probability == 0:
            self.probability = (
                frappe.db.get_value("CRM Inquiry Status", self.status, "probability") or 0
            )

    def update_expected_inquiry_value(self):
        """
        Update the expected inquiry value based on the net total or total.
        """
        if (
            frappe.db.get_single_value(
                "FCRM Settings", "auto_update_expected_inquiry_value"
            )
            and (self.net_total or self.total)
            and self.expected_inquiry_value
        ):
            self.expected_inquiry_value = self.net_total or self.total

    def validate_forecasting_fields(self):
        self.update_closed_date()
        self.update_default_probability()
        self.update_expected_inquiry_value()
        if frappe.db.get_single_value("FCRM Settings", "enable_forecasting"):
            if not self.expected_inquiry_value or self.expected_inquiry_value == 0:
                frappe.throw(
                    _("Expected inquiry value is required."), frappe.MandatoryError
                )
            if not self.expected_closure_date:
                frappe.throw(
                    _("Expected closure date is required."), frappe.MandatoryError
                )

    def validate_lost_reason(self):
        """
        Validate the lost reason if the status is set to "Lost".
        """
        if (
            self.status
            and frappe.get_cached_value("CRM Inquiry Status", self.status, "type")
            == "Lost"
        ):
            if not self.lost_reason:
                frappe.throw(
                    _("Please specify a reason for losing the inquiry."),
                    frappe.ValidationError,
                )
            elif self.lost_reason == "Other" and not self.lost_notes:
                frappe.throw(
                    _("Please specify the reason for losing the inquiry."),
                    frappe.ValidationError,
                )
        if self.has_value_changed("status"):
            add_or_remove_lost_reason_section_in_sidepanel(self)

    def update_exchange_rate(self):
        if self.has_value_changed("currency") or not self.exchange_rate:
            system_currency = (
                frappe.db.get_single_value("FCRM Settings", "currency") or "USD"
            )
            exchange_rate = 1
            if self.currency and self.currency != system_currency:
                exchange_rate = get_exchange_rate(self.currency, system_currency)

            self.db_set("exchange_rate", exchange_rate)

    @staticmethod
    def default_list_data():
        columns = [
            {
                "label": "Subject",
                "type": "Data",
                "key": "subject",
                "width": "11rem",
            },
            {
                "label": "Communication",
                "type": "Link",
                "key": "communication_status",
                "options": "CRM Communication Status",
                "width": "7rem",
            },
            {
                "label": "Organization",
                "type": "Link",
                "key": "organization",
                "options": "CRM Organization",
                "width": "12rem",
            },
            {
                "label": "Annual Revenue",
                "type": "Currency",
                "key": "annual_revenue",
                "align": "right",
                "width": "11rem",
            },
            {
                "label": "Status",
                "type": "Link",
                "options": "CRM Inquiry Status",
                "key": "status",
                "width": "10rem",
            },
            {
                "label": "Email",
                "type": "Data",
                "key": "email",
                "width": "12rem",
            },
            {
                "label": "Mobile No.",
                "type": "Data",
                "key": "mobile_no",
                "width": "11rem",
            },
            {
                "label": "Assigned To",
                "type": "Text",
                "key": "_assign",
                "width": "10rem",
            },
            {
                "label": "Last Modified",
                "type": "Datetime",
                "key": "modified",
                "width": "8rem",
            },
        ]
        rows = [
            "name",
            "organization",
            "annual_revenue",
            "status",
            "email",
            "currency",
            "mobile_no",
            "inquiry_owner",
            "sla_status",
            "response_by",
            "first_response_time",
            "first_responded_on",
            "modified",
            "_assign",
            "subject",
            "communication_status",
        ]
        return {"columns": columns, "rows": rows}

    @staticmethod
    def default_kanban_settings():
        return {
            "column_field": "status",
            "title_field": "organization",
            "kanban_fields": '["annual_revenue", "email", "mobile_no", "_assign", "modified"]',
        }


@frappe.whitelist()
def add_contact(inquiry: str, contact: str):
    if not frappe.has_permission("CRM Inquiry", "write", inquiry):
        frappe.throw(_("Not allowed to add contact to Inquiry"), frappe.PermissionError)

    inquiry = frappe.get_cached_doc("CRM Inquiry", inquiry)
    inquiry.append("contacts", {"contact": contact})
    inquiry.save()
    return True


@frappe.whitelist()
def remove_contact(inquiry: str, contact: str):
    if not frappe.has_permission("CRM Inquiry", "write", inquiry):
        frappe.throw(
            _("Not allowed to remove contact from Inquiry"), frappe.PermissionError
        )

    inquiry = frappe.get_cached_doc("CRM Inquiry", inquiry)
    inquiry.contacts = [d for d in inquiry.contacts if d.contact != contact]
    inquiry.save()
    return True


@frappe.whitelist()
def set_primary_contact(inquiry: str, contact: str):
    if not frappe.has_permission("CRM Inquiry", "write", inquiry):
        frappe.throw(
            _("Not allowed to set primary contact for Inquiry"), frappe.PermissionError
        )

    inquiry = frappe.get_cached_doc("CRM Inquiry", inquiry)
    inquiry.set_primary_contact(contact)
    inquiry.save()
    return True


def create_organization(doc):
    if not doc.get("organization_name"):
        return

    existing_organization = frappe.db.exists(
        "CRM Organization", {"organization_name": doc.get("organization_name")}
    )
    if existing_organization:
        return existing_organization

    organization = frappe.new_doc("CRM Organization")
    organization.update(
        {
            "organization_name": doc.get("organization_name"),
            "website": doc.get("website"),
            "territory": doc.get("territory"),
            "industry": doc.get("industry"),
            "annual_revenue": doc.get("annual_revenue"),
        }
    )
    organization.insert(ignore_permissions=True)
    return organization.name


def contact_exists(doc):
    email_exist = frappe.db.exists("Contact Email", {"email_id": doc.get("email")})
    mobile_exist = frappe.db.exists("Contact Phone", {"phone": doc.get("mobile_no")})

    doctype = "Contact Email" if email_exist else "Contact Phone"
    name = email_exist or mobile_exist

    if name:
        return frappe.db.get_value(doctype, name, "parent")

    return False


def create_contact(doc):
    existing_contact = contact_exists(doc)
    if existing_contact:
        return existing_contact

    contact = frappe.new_doc("Contact")
    contact.update(
        {
            "first_name": doc.get("first_name"),
            "last_name": doc.get("last_name"),
            "salutation": doc.get("salutation"),
            "company_name": doc.get("organization") or doc.get("organization_name"),
            "gender": doc.get("gender"),
        }
    )

    if doc.get("email"):
        contact.append("email_ids", {"email_id": doc.get("email"), "is_primary": 1})

    if doc.get("mobile_no"):
        contact.append(
            "phone_nos", {"phone": doc.get("mobile_no"), "is_primary_mobile_no": 1}
        )

    contact.insert(ignore_permissions=True)
    contact.reload()  # load changes by hooks on contact

    return contact.name


@frappe.whitelist()
def create_inquiry(doc: dict):
    inquiry = frappe.new_doc("CRM Inquiry")

    contact = doc.get("contact")
    if not contact and (
        doc.get("first_name")
        or doc.get("last_name")
        or doc.get("email")
        or doc.get("mobile_no")
    ):
        contact = create_contact(doc)

    inquiry.update(
        {
            "organization": doc.get("organization") or create_organization(doc),
            "contacts": [{"contact": contact, "is_primary": 1}] if contact else [],
        }
    )

    doc.pop("organization", None)

    inquiry.update(doc)

    inquiry.insert(ignore_permissions=True)
    return inquiry.name
