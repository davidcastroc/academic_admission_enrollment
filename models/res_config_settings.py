from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    academic_identifier_mode = fields.Selection(
        [("national_id", "Identification number"), ("student_card", "Student card")],
        string="Unique student identifier",
        default="national_id",
        config_parameter="academic.identifier_mode",
    )
    academic_review_mode = fields.Selection(
        [("manual", "Manual"), ("assisted", "Assisted (OCR/AI + human review)")],
        string="Document review mode",
        default="manual",
        config_parameter="academic.review_mode",
    )
    academic_minimum_age = fields.Integer(
        string="Minimum age without guarantor",
        default=18,
        config_parameter="academic.minimum_age",
    )
    academic_require_guarantor_minor = fields.Boolean(
        string="Require guarantor for underage applicants",
        default=True,
        config_parameter="academic.require_guarantor_minor",
    )
    academic_auto_create_lead = fields.Boolean(
        string="Create CRM opportunity on submission",
        default=True,
        config_parameter="academic.auto_create_lead",
    )
    academic_auto_create_student = fields.Boolean(
        string="Create student when application is approved",
        default=False,
        config_parameter="academic.auto_create_student",
    )
    academic_ocr_enabled = fields.Boolean(
        string="Enable OCR/AI queue",
        default=False,
        config_parameter="academic.ocr_enabled",
    )
    academic_ocr_provider = fields.Char(
        string="OCR/AI adapter code",
        default="manual",
        config_parameter="academic.ocr_provider",
        help="Technical adapter code. External provider modules can extend academic.ocr.service.",
    )
    academic_max_upload_mb = fields.Integer(
        string="Maximum upload size (MB)",
        default=10,
        config_parameter="academic.max_upload_mb",
    )
    academic_conesup_enabled = fields.Boolean(
        string="Enable CONESUP integration",
        default=False,
        config_parameter="academic.conesup_enabled",
    )
    academic_conesup_base_url = fields.Char(
        string="CONESUP service base URL",
        config_parameter="academic.conesup_base_url",
        help="Only configure after receiving the official technical specification.",
    )
