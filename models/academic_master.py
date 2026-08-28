from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AcademicProgram(models.Model):
    _name = "academic.program"
    _description = "Academic Program"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    description = fields.Html()
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)

    _sql_constraints = [("program_code_company_uniq", "unique(code, company_id)", "Program code must be unique per company.")]


class AcademicPeriod(models.Model):
    _name = "academic.period"
    _description = "Academic Period"
    _order = "date_start desc"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    application_start = fields.Datetime()
    application_end = fields.Datetime()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)

    _sql_constraints = [("period_code_company_uniq", "unique(code, company_id)", "Period code must be unique per company.")]

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_end < rec.date_start:
                raise ValidationError("Period end date cannot be before start date.")


class AcademicOffering(models.Model):
    _name = "academic.offering"
    _description = "Academic Offering"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period_id desc, program_id"

    name = fields.Char(compute="_compute_name", store=True)
    program_id = fields.Many2one("academic.program", required=True, ondelete="restrict", tracking=True)
    period_id = fields.Many2one("academic.period", required=True, ondelete="restrict", tracking=True)
    modality = fields.Selection(
        [("onsite", "On-site"), ("virtual", "Virtual"), ("hybrid", "Hybrid")],
        required=True,
        default="onsite",
        tracking=True,
    )
    campus = fields.Char(string="Campus", tracking=True)
    capacity = fields.Integer(default=0, tracking=True, help="0 means no configured capacity limit.")
    active = fields.Boolean(default=True)
    is_published = fields.Boolean(string="Available in portal", default=False, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    application_ids = fields.One2many("academic.application", "offering_id", string="Applications")
    application_count = fields.Integer(compute="_compute_counts")
    approved_count = fields.Integer(compute="_compute_counts")
    enrolled_count = fields.Integer(compute="_compute_counts")
    available_seats = fields.Integer(compute="_compute_counts")

    _sql_constraints = [
        ("offering_unique", "unique(program_id, period_id, modality, campus, company_id)", "This academic offering already exists."),
        ("capacity_nonnegative", "check(capacity >= 0)", "Capacity cannot be negative."),
    ]

    @api.depends("program_id", "period_id", "modality", "campus")
    def _compute_name(self):
        for rec in self:
            parts = [rec.program_id.name or "", rec.period_id.name or "", dict(rec._fields["modality"].selection).get(rec.modality, "")]
            if rec.campus:
                parts.append(rec.campus)
            rec.name = " - ".join(p for p in parts if p)

    def _compute_counts(self):
        Application = self.env["academic.application"]
        for rec in self:
            rec.application_count = Application.search_count([("offering_id", "=", rec.id), ("state", "!=", "cancelled")])
            rec.approved_count = Application.search_count([("offering_id", "=", rec.id), ("state", "in", ["approved", "enrolled"])])
            rec.enrolled_count = Application.search_count([("offering_id", "=", rec.id), ("state", "=", "enrolled")])
            rec.available_seats = max(rec.capacity - rec.enrolled_count, 0) if rec.capacity else 0

    def check_capacity_for_enrollment(self):
        self.ensure_one()
        if self.capacity and self.enrolled_count >= self.capacity:
            raise ValidationError("No enrollment seats are available for this offering.")
