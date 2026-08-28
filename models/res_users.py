from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    academic_cashier_person_id = fields.Many2one(
        "res.partner",
        string="Identified cashier person",
        domain=[("is_company", "=", False)],
        help="Required for users assigned to the Academic / Cashier role.",
    )

    @api.constrains("groups_id", "academic_cashier_person_id")
    def _check_cashier_person(self):
        cashier_group = self.env.ref("academic_admission_enrollment.group_academic_cashier", raise_if_not_found=False)
        if not cashier_group:
            return
        for user in self:
            if cashier_group in user.groups_id and not user.academic_cashier_person_id:
                raise ValidationError("Cashier users must be linked to an identifiable physical person.")
