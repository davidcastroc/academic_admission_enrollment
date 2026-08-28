from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class AcademicApplication(models.Model):
    _name = "academic.application"
    _description = "Academic Application"
    _inherit = ["mail.thread", "mail.activity.mixin", "portal.mixin"]
    _order = "create_date desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True, index=True)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict", tracking=True, index=True)
    offering_id = fields.Many2one("academic.offering", required=True, ondelete="restrict", tracking=True, index=True)
    company_id = fields.Many2one(related="offering_id.company_id", store=True, index=True)

    applicant_name = fields.Char(required=True, tracking=True)
    identification_type = fields.Selection(
        [("national", "National ID"), ("dimex", "DIMEX"), ("passport", "Passport"), ("other", "Other")],
        required=True,
        default="national",
        tracking=True,
    )
    identification = fields.Char(required=True, tracking=True, index=True)
    birth_date = fields.Date(required=True, tracking=True)
    age = fields.Integer(compute="_compute_age", store=False)
    email = fields.Char(required=True, tracking=True)
    phone = fields.Char(required=True, tracking=True)
    country_id = fields.Many2one("res.country", required=True, tracking=True)
    state_id = fields.Many2one("res.country.state", required=True, tracking=True, domain="[('country_id', '=', country_id)]")
    canton = fields.Char(required=True, tracking=True)
    district = fields.Char(required=True, tracking=True)
    street = fields.Char(required=True, tracking=True)

    state = fields.Selection([
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("auto_review", "Automatic review"),
        ("admin_review", "Administrative review"),
        ("academic_review", "Academic review"),
        ("correction", "Correction requested"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("enrolled", "Enrolled"),
        ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True, index=True)

    crm_lead_id = fields.Many2one("crm.lead", copy=False, readonly=True)
    document_ids = fields.One2many("academic.application.document", "application_id", string="Documents")
    event_ids = fields.One2many("academic.application.event", "application_id", string="Audit events", readonly=True)
    guarantor_ids = fields.One2many("academic.guarantor", "application_id", string="Guarantors")
    convalidation_ids = fields.One2many("academic.convalidation", "application_id", string="Convalidations")
    student_id = fields.Many2one("academic.student", copy=False, readonly=True)
    enrollment_id = fields.Many2one("academic.enrollment", copy=False, readonly=True)

    requires_guarantor = fields.Boolean(compute="_compute_requires_guarantor")
    missing_required_documents = fields.Integer(compute="_compute_document_status")
    invalid_documents = fields.Integer(compute="_compute_document_status")
    all_documents_ready = fields.Boolean(compute="_compute_document_status")
    rejection_reason = fields.Text(tracking=True)
    correction_note = fields.Text(tracking=True)
    conesup_status = fields.Selection([
        ("not_checked", "Not checked"), ("pending", "Pending"), ("valid", "Valid"), ("invalid", "Invalid"), ("error", "Error")
    ], default="not_checked", tracking=True)
    conesup_message = fields.Text(readonly=True)

    _sql_constraints = [
        ("application_identification_offering_uniq", "unique(identification, offering_id)", "This applicant already has an application for the selected offering."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("academic.application") or _("New")
        records = super().create(vals_list)
        for rec in records:
            rec._sync_partner()
            rec._log_event("created", _("Application created"))
        return records

    @api.depends("birth_date")
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.age = relativedelta(today, rec.birth_date).years if rec.birth_date else 0

    def _minimum_age(self):
        return int(self.env["ir.config_parameter"].sudo().get_param("academic.minimum_age", "18") or 18)

    @api.depends("birth_date")
    def _compute_requires_guarantor(self):
        require = self.env["ir.config_parameter"].sudo().get_param("academic.require_guarantor_minor", "True") == "True"
        minimum = self._minimum_age()
        for rec in self:
            rec.requires_guarantor = bool(require and rec.birth_date and rec.age < minimum)

    @api.depends("document_ids.state", "document_ids.document_type_id", "offering_id")
    def _compute_document_status(self):
        Requirement = self.env["academic.document.requirement"]
        for rec in self:
            required_types = Requirement.search([
                ("active", "=", True),
                ("required", "=", True),
                "|", ("offering_id", "=", rec.offering_id.id),
                     "&", ("offering_id", "=", False), ("program_id", "in", [False, rec.offering_id.program_id.id]),
            ]).mapped("document_type_id")
            docs_by_type = {d.document_type_id.id: d for d in rec.document_ids if d.attachment_id}
            missing = sum(1 for t in required_types if t.id not in docs_by_type)
            invalid = len(rec.document_ids.filtered(lambda d: d.state in ("rejected", "error")))
            rec.missing_required_documents = missing
            rec.invalid_documents = invalid
            rec.all_documents_ready = missing == 0 and invalid == 0 and all(
                d.state in ("approved", "pending", "review") for d in rec.document_ids if d.attachment_id
            )

    @api.constrains("birth_date")
    def _check_birth_date(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.birth_date and rec.birth_date > today:
                raise ValidationError(_("Birth date cannot be in the future."))

    def _sync_partner(self):
        for rec in self:
            vals = {
                "name": rec.applicant_name,
                "email": rec.email,
                "phone": rec.phone,
                "country_id": rec.country_id.id,
                "state_id": rec.state_id.id,
                "street": rec.street,
                "academic_identification_type": rec.identification_type,
                "academic_identification": rec.identification,
                "academic_birth_date": rec.birth_date,
                "academic_canton": rec.canton,
                "academic_district": rec.district,
                "academic_is_applicant": True,
            }
            applicant_tag = self.env.ref("academic_admission_enrollment.partner_category_academic_applicant", raise_if_not_found=False)
            if applicant_tag:
                vals["category_id"] = [(4, applicant_tag.id)]
            rec.partner_id.write(vals)

    def _log_event(self, code, description):
        Event = self.env["academic.application.event"].sudo()
        for rec in self:
            Event.create({"application_id": rec.id, "code": code, "description": description, "user_id": self.env.user.id})

    def _ensure_required_documents(self):
        for rec in self:
            if rec.missing_required_documents:
                raise ValidationError(_("There are %s required document(s) missing.") % rec.missing_required_documents)

    def _ensure_guarantor(self):
        for rec in self:
            if rec.requires_guarantor and not rec.guarantor_ids.filtered(lambda g: g.state == "approved"):
                raise ValidationError(_("An approved guarantor/responsible person is required for this applicant."))

    def _ensure_required_documents_approved(self):
        Requirement = self.env["academic.document.requirement"]
        for rec in self:
            requirements = Requirement.search([
                ("active", "=", True), ("required", "=", True),
                "|", ("offering_id", "=", rec.offering_id.id),
                     "&", ("offering_id", "=", False), ("program_id", "in", [False, rec.offering_id.program_id.id]),
            ])
            for doc_type in requirements.mapped("document_type_id"):
                document = rec.document_ids.filtered(lambda d: d.document_type_id == doc_type)[:1]
                if not document or document.state != "approved":
                    raise ValidationError(_("Required document '%s' must be approved before continuing.") % doc_type.name)

    def _create_crm_lead(self):
        auto = self.env["ir.config_parameter"].sudo().get_param("academic.auto_create_lead", "True") == "True"
        for rec in self.filtered(lambda r: not r.crm_lead_id and auto):
            lead = self.env["crm.lead"].create({
                "name": _("Academic application %s - %s") % (rec.name, rec.applicant_name),
                "partner_id": rec.partner_id.id,
                "contact_name": rec.applicant_name,
                "email_from": rec.email,
                "phone": rec.phone,
                "type": "opportunity",
                "academic_application_id": rec.id,
                "description": _("Academic offering: %s") % rec.offering_id.display_name,
            })
            rec.crm_lead_id = lead.id
            rec._log_event("crm_created", _("CRM opportunity created: %s") % lead.display_name)

    def action_submit(self):
        for rec in self:
            if rec.state not in ("draft", "correction"):
                continue
            rec._sync_partner()
            rec._ensure_required_documents()
            if rec.requires_guarantor and not rec.guarantor_ids:
                raise ValidationError(_("A guarantor/responsible person must be registered before submission."))
            review_mode = self.env["ir.config_parameter"].sudo().get_param("academic.review_mode", "manual")
            next_state = "auto_review" if review_mode == "assisted" else "admin_review"
            rec.write({"state": next_state, "correction_note": False})
            rec._create_crm_lead()
            if review_mode == "assisted":
                rec.document_ids.filtered(lambda d: d.state == "pending").action_queue_ocr()
            rec._log_event("submitted", _("Application submitted"))
            rec._send_template("academic_admission_enrollment.mail_template_application_submitted")
        return True

    def action_send_admin_review(self):
        self.write({"state": "admin_review"})
        self._log_event("admin_review", _("Sent to administrative review"))

    def action_send_academic_review(self):
        self._ensure_required_documents()
        self._ensure_required_documents_approved()
        if self.filtered(lambda r: r.invalid_documents):
            raise ValidationError(_("Rejected or errored documents must be resolved before academic review."))
        self.write({"state": "academic_review"})
        self._log_event("academic_review", _("Sent to academic review"))

    def action_request_correction(self):
        for rec in self:
            if not rec.correction_note:
                raise ValidationError(_("Enter a correction note before requesting corrections."))
        self.write({"state": "correction"})
        self._log_event("correction", _("Corrections requested"))
        self._send_template("academic_admission_enrollment.mail_template_application_correction")

    def action_approve(self):
        self._ensure_required_documents()
        self._ensure_required_documents_approved()
        self._ensure_guarantor()
        for rec in self:
            rec.write({"state": "approved", "rejection_reason": False})
            rec._log_event("approved", _("Application approved"))
            auto_student = self.env["ir.config_parameter"].sudo().get_param("academic.auto_create_student", "False") == "True"
            if auto_student and not rec.student_id:
                rec.action_create_student()
            rec._send_template("academic_admission_enrollment.mail_template_application_approved")
        return True

    def action_reject(self):
        for rec in self:
            if not rec.rejection_reason:
                raise ValidationError(_("Enter a rejection reason."))
            rec.write({"state": "rejected"})
            rec._log_event("rejected", rec.rejection_reason)
            rec._send_template("academic_admission_enrollment.mail_template_application_rejected")
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        self._log_event("cancelled", _("Application cancelled"))

    def action_reset_draft(self):
        self.write({"state": "draft"})
        self._log_event("reset", _("Application reset to draft"))

    def action_create_student(self):
        Student = self.env["academic.student"]
        for rec in self:
            if rec.state not in ("approved", "enrolled"):
                raise UserError(_("The application must be approved before creating a student."))
            if not rec.student_id:
                student = Student.create_from_application(rec)
                rec.student_id = student.id
                rec._log_event("student_created", _("Student created: %s") % student.display_name)
        return True

    def action_enroll(self):
        Enrollment = self.env["academic.enrollment"]
        for rec in self:
            if rec.state != "approved":
                raise UserError(_("Only approved applications can be enrolled."))
            rec.offering_id.check_capacity_for_enrollment()
            if not rec.student_id:
                rec.action_create_student()
            enrollment = Enrollment.create_from_application(rec)
            rec.write({"enrollment_id": enrollment.id, "state": "enrolled"})
            enrolled_tag = self.env.ref("academic_admission_enrollment.partner_category_academic_enrolled", raise_if_not_found=False)
            if enrolled_tag:
                rec.partner_id.write({"category_id": [(4, enrolled_tag.id)]})
            rec._log_event("enrolled", _("Enrollment created: %s") % enrollment.display_name)
            rec._send_template("academic_admission_enrollment.mail_template_application_enrolled")
        return True

    def action_check_conesup(self):
        enabled = self.env["ir.config_parameter"].sudo().get_param("academic.conesup_enabled", "False") == "True"
        if not enabled:
            raise UserError(_("CONESUP integration is disabled until official technical specifications are configured."))
        service = self.env["academic.conesup.service"]
        for rec in self:
            result = service.validate_application(rec)
            rec.write({"conesup_status": result.get("status", "pending"), "conesup_message": result.get("message")})
            rec._log_event("conesup", result.get("message") or _("CONESUP validation executed"))
        return True

    def _send_template(self, xmlid):
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if template:
            for rec in self:
                template.send_mail(rec.id, force_send=False)

    def _compute_access_url(self):
        super()._compute_access_url()
        for rec in self:
            rec.access_url = "/my/admissions/%s" % rec.id


class AcademicApplicationEvent(models.Model):
    _name = "academic.application.event"
    _description = "Academic Application Audit Event"
    _order = "event_date desc, id desc"

    application_id = fields.Many2one("academic.application", required=True, ondelete="cascade", index=True)
    event_date = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, readonly=True)
    code = fields.Char(required=True, readonly=True)
    description = fields.Text(required=True, readonly=True)
