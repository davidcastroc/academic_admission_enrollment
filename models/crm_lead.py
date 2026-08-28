from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    academic_application_id = fields.Many2one("academic.application", string="Academic application", ondelete="set null", index=True)
    academic_convalidation_id = fields.Many2one("academic.convalidation", string="Convalidation request", ondelete="set null", index=True)
