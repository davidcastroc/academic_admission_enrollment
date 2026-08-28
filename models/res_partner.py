from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    academic_identification_type = fields.Selection(
        [("national", "National ID"), ("dimex", "DIMEX"), ("passport", "Passport"), ("other", "Other")],
        string="Academic identification type",
        tracking=True,
    )
    academic_identification = fields.Char(string="Academic identification", index=True, tracking=True)
    academic_birth_date = fields.Date(string="Birth date", tracking=True)
    academic_canton = fields.Char(string="Canton")
    academic_district = fields.Char(string="District")
    academic_is_applicant = fields.Boolean(string="Academic applicant", default=False, index=True)
    academic_is_student = fields.Boolean(string="Academic student", default=False, index=True)
    academic_student_id = fields.Many2one("academic.student", string="Student record", readonly=True)

    @api.constrains("academic_identification")
    def _check_academic_identification_unique(self):
        for partner in self.filtered("academic_identification"):
            duplicate = self.search_count([
                ("id", "!=", partner.id),
                ("academic_identification", "=", partner.academic_identification),
                ("company_id", "in", [False, partner.company_id.id]),
            ])
            if duplicate:
                raise ValidationError("The academic identification is already assigned to another contact.")
