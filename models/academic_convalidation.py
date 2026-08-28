from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AcademicConvalidation(models.Model):
    _name = "academic.convalidation"
    _description = "Academic Convalidation Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True)
    application_id = fields.Many2one("academic.application", required=True, ondelete="cascade", tracking=True)
    partner_id = fields.Many2one(related="application_id.partner_id", store=True)
    student_id = fields.Many2one(related="application_id.student_id", store=True)
    description = fields.Text(required=True, tracking=True)
    attachment_ids = fields.Many2many("ir.attachment", string="Supporting documents")
    state = fields.Selection([("draft", "Draft"), ("submitted", "Submitted"), ("review", "Under review"), ("approved", "Approved"), ("rejected", "Rejected")], default="draft", tracking=True)
    crm_lead_id = fields.Many2one("crm.lead", readonly=True, copy=False)
    decision_note = fields.Text(tracking=True)
    company_id = fields.Many2one(related="application_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("academic.convalidation") or _("New")
        return super().create(vals_list)

    def _ensure_first_enrollment(self):
        Enrollment = self.env["academic.enrollment"]
        for rec in self:
            student = rec.application_id.student_id
            if student:
                previous = Enrollment.search_count([
                    ("student_id", "=", student.id),
                    ("state", "=", "confirmed"),
                    ("application_id", "!=", rec.application_id.id),
                ])
                if previous:
                    raise ValidationError(_("Convalidation requests are only allowed during the first enrollment."))

    def action_submit(self):
        self._ensure_first_enrollment()
        for rec in self:
            vals = {"state": "submitted"}
            if not rec.crm_lead_id:
                lead = self.env["crm.lead"].create({
                    "name": _("Convalidation %s - %s") % (rec.name, rec.partner_id.display_name),
                    "partner_id": rec.partner_id.id,
                    "type": "opportunity",
                    "academic_convalidation_id": rec.id,
                    "description": rec.description,
                })
                vals["crm_lead_id"] = lead.id
            rec.write(vals)
            rec.application_id._log_event("convalidation_submitted", _("Convalidation submitted: %s") % rec.name)
        return True

    def action_review(self):
        self.write({"state": "review"})

    def action_approve(self):
        self._ensure_first_enrollment()
        self.write({"state": "approved"})
        for rec in self:
            rec.application_id._log_event("convalidation_approved", _("Convalidation approved: %s") % rec.name)

    def action_reject(self):
        for rec in self:
            if not rec.decision_note:
                raise ValidationError(_("Enter a decision note before rejecting."))
        self.write({"state": "rejected"})
        for rec in self:
            rec.application_id._log_event("convalidation_rejected", _("Convalidation rejected: %s") % rec.name)
