import mimetypes

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class AcademicDocumentType(models.Model):
    _name = "academic.document.type"
    _description = "Academic Document Type"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
    validity_required = fields.Boolean(string="Requires expiration/validity check")
    ai_classification_hint = fields.Char(string="OCR/AI classification hint")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    _sql_constraints = [("doc_type_code_company_uniq", "unique(code, company_id)", "Document type code must be unique per company.")]


class AcademicDocumentRequirement(models.Model):
    _name = "academic.document.requirement"
    _description = "Academic Document Requirement"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    document_type_id = fields.Many2one("academic.document.type", required=True, ondelete="cascade")
    program_id = fields.Many2one("academic.program", ondelete="cascade", help="Leave empty to make the requirement generic.")
    offering_id = fields.Many2one("academic.offering", ondelete="cascade", help="Offering-specific requirement takes precedence.")
    required = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    notes = fields.Char()
    company_id = fields.Many2one(related="document_type_id.company_id", store=True)

    @api.constrains("program_id", "offering_id")
    def _check_scope(self):
        for rec in self:
            if rec.program_id and rec.offering_id and rec.offering_id.program_id != rec.program_id:
                raise ValidationError(_("The offering does not belong to the selected program."))


class AcademicApplicationDocument(models.Model):
    _name = "academic.application.document"
    _description = "Academic Application Document"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    application_id = fields.Many2one("academic.application", required=True, ondelete="cascade", index=True)
    document_type_id = fields.Many2one("academic.document.type", required=True, ondelete="restrict", tracking=True)
    attachment_id = fields.Many2one("ir.attachment", required=True, ondelete="cascade")
    filename = fields.Char(related="attachment_id.name", readonly=True)
    mimetype = fields.Char(related="attachment_id.mimetype", readonly=True)
    file_size = fields.Integer(related="attachment_id.file_size", readonly=True)
    state = fields.Selection([
        ("pending", "Pending"),
        ("queued", "Queued for OCR/AI"),
        ("review", "Needs review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("error", "Processing error"),
    ], default="pending", required=True, tracking=True, index=True)
    reviewer_id = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    review_note = fields.Text(tracking=True)
    expiry_date = fields.Date(tracking=True)
    ocr_confidence = fields.Float(readonly=True)
    ocr_result = fields.Text(readonly=True)
    detected_document_type = fields.Char(readonly=True)
    is_expired = fields.Boolean(compute="_compute_expired")
    company_id = fields.Many2one(related="application_id.company_id", store=True, index=True)

    _sql_constraints = [
        ("one_type_per_application", "unique(application_id, document_type_id)", "Only one active document per document type is allowed for each application."),
    ]

    @api.depends("application_id", "document_type_id")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s - %s" % (rec.application_id.name or "", rec.document_type_id.name or "")

    @api.depends("expiry_date")
    def _compute_expired(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_expired = bool(rec.expiry_date and rec.expiry_date < today)

    @api.constrains("attachment_id")
    def _check_attachment(self):
        max_mb = int(self.env["ir.config_parameter"].sudo().get_param("academic.max_upload_mb", "10") or 10)
        allowed = {"application/pdf", "image/jpeg", "image/png"}
        for rec in self:
            if rec.attachment_id.mimetype not in allowed:
                raise ValidationError(_("Only PDF, JPG/JPEG and PNG documents are allowed."))
            if rec.attachment_id.file_size and rec.attachment_id.file_size > max_mb * 1024 * 1024:
                raise ValidationError(_("The document exceeds the maximum upload size of %s MB.") % max_mb)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec.attachment_id.write({"res_model": rec._name, "res_id": rec.id})
            rec.application_id._log_event("document_uploaded", _("Document uploaded: %s") % rec.document_type_id.name)
        return records

    def action_queue_ocr(self):
        enabled = self.env["ir.config_parameter"].sudo().get_param("academic.ocr_enabled", "False") == "True"
        if not enabled:
            self.write({"state": "review"})
            return True
        self.filtered(lambda d: d.state in ("pending", "error")).write({"state": "queued"})
        return True

    def action_run_ocr(self):
        service = self.env["academic.ocr.service"]
        for rec in self:
            if rec.state not in ("queued", "pending", "error"):
                continue
            try:
                result = service.analyze_document(rec)
                state = result.get("state", "review")
                vals = {
                    "state": state,
                    "ocr_confidence": float(result.get("confidence", 0.0) or 0.0),
                    "ocr_result": result.get("message") or result.get("text"),
                    "detected_document_type": result.get("document_type"),
                }
                if result.get("expiry_date"):
                    vals["expiry_date"] = result["expiry_date"]
                rec.write(vals)
                rec.application_id._log_event("ocr", result.get("message") or _("OCR/AI analysis completed"))
            except Exception as exc:
                rec.write({"state": "error", "ocr_result": str(exc)})
                rec.application_id._log_event("ocr_error", str(exc))
        return True

    @api.model
    def _cron_process_ocr_queue(self):
        enabled = self.env["ir.config_parameter"].sudo().get_param("academic.ocr_enabled", "False") == "True"
        if enabled:
            self.search([("state", "=", "queued")], limit=20).action_run_ocr()

    def action_approve(self):
        for rec in self:
            if rec.is_expired:
                raise ValidationError(_("An expired document cannot be approved."))
        self.write({"state": "approved", "reviewer_id": self.env.user.id, "reviewed_at": fields.Datetime.now()})
        for rec in self:
            rec.application_id._log_event("document_approved", _("Document approved: %s") % rec.document_type_id.name)
        return True

    def action_reject(self):
        for rec in self:
            if not rec.review_note:
                raise ValidationError(_("Enter a review note before rejecting the document."))
        self.write({"state": "rejected", "reviewer_id": self.env.user.id, "reviewed_at": fields.Datetime.now()})
        for rec in self:
            rec.application_id._log_event("document_rejected", _("Document rejected: %s - %s") % (rec.document_type_id.name, rec.review_note))
        return True


class AcademicGuarantor(models.Model):
    _name = "academic.guarantor"
    _description = "Academic Guarantor / Responsible Person"
    _inherit = ["mail.thread"]

    application_id = fields.Many2one("academic.application", required=True, ondelete="cascade", index=True)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict", tracking=True)
    relationship = fields.Char(required=True, tracking=True)
    identification = fields.Char(required=True, tracking=True)
    phone = fields.Char(required=True)
    email = fields.Char(required=True)
    state = fields.Selection([("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")], default="pending", tracking=True)
    note = fields.Text()
    company_id = fields.Many2one(related="application_id.company_id", store=True)

    def action_approve(self):
        self.write({"state": "approved"})
        for rec in self:
            rec.application_id._log_event("guarantor_approved", _("Guarantor approved: %s") % rec.partner_id.display_name)

    def action_reject(self):
        self.write({"state": "rejected"})
        for rec in self:
            rec.application_id._log_event("guarantor_rejected", _("Guarantor rejected: %s") % rec.partner_id.display_name)
