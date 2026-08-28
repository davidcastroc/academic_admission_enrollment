from odoo import models, _


class AcademicOCRService(models.AbstractModel):
    _name = "academic.ocr.service"
    _description = "Academic OCR/AI Service Adapter"

    def analyze_document(self, document):
        """Extension point for OCR/AI provider modules.

        Expected result keys: state, confidence, message/text, document_type, expiry_date.
        The default implementation deliberately performs no external request.
        """
        provider = self.env["ir.config_parameter"].sudo().get_param("academic.ocr_provider", "manual")
        return {
            "state": "review",
            "confidence": 0.0,
            "message": _("OCR/AI adapter '%s' is not implemented. Document routed to human review.") % provider,
        }


class AcademicCONESUPService(models.AbstractModel):
    _name = "academic.conesup.service"
    _description = "Academic CONESUP Service Adapter"

    def validate_application(self, application):
        """Extension point for the official CONESUP API/web-service adapter."""
        return {
            "status": "pending",
            "message": _("CONESUP adapter is pending official API/web-service specifications and whitelist authorization."),
        }
