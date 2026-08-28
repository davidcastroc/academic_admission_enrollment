from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AcademicStudent(models.Model):
    _name = "academic.student"
    _description = "Academic Student"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"

    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict", index=True, tracking=True)
    code = fields.Char(copy=False, readonly=True, index=True, tracking=True)
    identification = fields.Char(required=True, index=True, tracking=True)
    program_id = fields.Many2one("academic.program", required=True, ondelete="restrict", tracking=True)
    admission_application_id = fields.Many2one("academic.application", required=True, ondelete="restrict", copy=False)
    state = fields.Selection([("active", "Active"), ("inactive", "Inactive"), ("graduated", "Graduated"), ("withdrawn", "Withdrawn")], default="active", tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    enrollment_ids = fields.One2many("academic.enrollment", "student_id", string="Enrollments")
    enrollment_count = fields.Integer(compute="_compute_enrollment_count")
    name = fields.Char(compute="_compute_name", store=True)

    @api.depends("partner_id.name", "code", "identification")
    def _compute_name(self):
        for rec in self:
            ident = rec.code or rec.identification or ""
            rec.name = "%s - %s" % (ident, rec.partner_id.name or "")

    @api.depends("enrollment_ids")
    def _compute_enrollment_count(self):
        for rec in self:
            rec.enrollment_count = len(rec.enrollment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        mode = self.env["ir.config_parameter"].sudo().get_param("academic.identifier_mode", "national_id")
        for rec in records:
            if mode == "student_card" and not rec.code:
                rec.code = self.env["ir.sequence"].next_by_code("academic.student") or False
            elif mode == "national_id" and not rec.code:
                rec.code = rec.identification
            rec.partner_id.write({"academic_is_student": True, "academic_student_id": rec.id})
        return records

    @api.constrains("code", "identification", "company_id")
    def _check_unique_student_identifier(self):
        mode = self.env["ir.config_parameter"].sudo().get_param("academic.identifier_mode", "national_id")
        for rec in self:
            field_name = "code" if mode == "student_card" else "identification"
            value = rec[field_name]
            if value and self.search_count([(field_name, "=", value), ("company_id", "=", rec.company_id.id), ("id", "!=", rec.id)]):
                raise ValidationError(_("The configured unique student identifier is already in use."))

    @api.model
    def create_from_application(self, application):
        existing = self.search([("partner_id", "=", application.partner_id.id), ("company_id", "=", application.company_id.id)], limit=1)
        if existing:
            return existing
        return self.create({
            "partner_id": application.partner_id.id,
            "identification": application.identification,
            "program_id": application.offering_id.program_id.id,
            "admission_application_id": application.id,
            "company_id": application.company_id.id,
        })


class AcademicEnrollment(models.Model):
    _name = "academic.enrollment"
    _description = "Academic Enrollment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "enrollment_date desc, id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True, index=True)
    student_id = fields.Many2one("academic.student", required=True, ondelete="restrict", tracking=True, index=True)
    offering_id = fields.Many2one("academic.offering", required=True, ondelete="restrict", tracking=True, index=True)
    application_id = fields.Many2one("academic.application", required=True, ondelete="restrict", copy=False)
    enrollment_date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    state = fields.Selection([("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")], default="confirmed", tracking=True)
    company_id = fields.Many2one(related="offering_id.company_id", store=True, index=True)

    _sql_constraints = [("student_offering_uniq", "unique(student_id, offering_id)", "The student is already enrolled in this offering.")]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("academic.enrollment") or _("New")
        return super().create(vals_list)

    @api.model
    def create_from_application(self, application):
        application.offering_id.check_capacity_for_enrollment()
        return self.create({
            "student_id": application.student_id.id,
            "offering_id": application.offering_id.id,
            "application_id": application.id,
        })
