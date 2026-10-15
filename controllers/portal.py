import base64

from odoo import http, fields, _
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class AcademicPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "admission_count" in counters:
            values["admission_count"] = request.env["academic.application"].sudo().search_count([
                ("partner_id", "=", request.env.user.partner_id.id)
            ])
        if "academic_suite_count" in counters:
            student = request.env["academic.student"].sudo().search([("partner_id", "=", request.env.user.partner_id.id)], limit=1)
            values["academic_suite_count"] = request.env["academic.course.registration"].sudo().search_count([("student_id", "=", student.id)]) if student else 0
        return values

    def _owned_application(self, application_id):
        application = request.env["academic.application"].sudo().browse(int(application_id)).exists()
        owner = request.env.user.partner_id
        if not application or application.partner_id.commercial_partner_id != owner:
            raise AccessError(_("You do not have access to this application."))
        return application

    def _portal_error(self, message, application=None):
        values = {"error": str(message)}
        if application:
            values.update(self._application_values(application))
            return request.render("academic_admission_enrollment.portal_application_detail", values)
        values.update(self._application_form_values())
        return request.render("academic_admission_enrollment.portal_application_form", values)

    def _application_form_values(self):
        partner = request.env.user.partner_id
        now = fields.Datetime.now()
        offerings = request.env["academic.offering"].sudo().search([
            ("active", "=", True), ("is_published", "=", True),
            "|", ("period_id.application_start", "=", False), ("period_id.application_start", "<=", now),
            "|", ("period_id.application_end", "=", False), ("period_id.application_end", ">=", now),
        ])
        return {
            "offerings": offerings,
            "countries": request.env["res.country"].sudo().search([]),
            "states": request.env["res.country.state"].sudo().search([]),
            "partner": partner,
        }

    def _application_values(self, application):
        requirements = request.env["academic.document.requirement"].sudo().search([
            ("active", "=", True),
            "|", ("offering_id", "=", application.offering_id.id),
                 "&", ("offering_id", "=", False), ("program_id", "in", [False, application.offering_id.program_id.id]),
        ], order="sequence, id")
        doc_types = requirements.mapped("document_type_id")
        if not doc_types:
            doc_types = request.env["academic.document.type"].sudo().search([("active", "=", True)])
        return {
            "application": application,
            "requirements": requirements,
            "document_types": doc_types,
            "countries": request.env["res.country"].sudo().search([]),
            "states": request.env["res.country.state"].sudo().search([]),
        }

    @http.route(["/my/admissions"], type="http", auth="user", website=True)
    def portal_admissions(self, **kw):
        partner = request.env.user.partner_id
        applications = request.env["academic.application"].sudo().search([
            ("partner_id", "=", partner.id)
        ], order="create_date desc")
        return request.render("academic_admission_enrollment.portal_my_applications", {"applications": applications})

    @http.route(["/my/admissions/<int:application_id>"], type="http", auth="user", website=True)
    def portal_application_detail(self, application_id, **kw):
        try:
            application = self._owned_application(application_id)
        except AccessError:
            return request.redirect("/my")
        return request.render("academic_admission_enrollment.portal_application_detail", self._application_values(application))

    @http.route(["/academic/apply"], type="http", auth="user", methods=["GET"], website=True)
    def portal_application_form(self, **kw):
        return request.render("academic_admission_enrollment.portal_application_form", self._application_form_values())

    @http.route(["/academic/apply/submit"], type="http", auth="user", methods=["POST"], website=True, csrf=True)
    def portal_application_create(self, **post):
        try:
            offering = request.env["academic.offering"].sudo().browse(int(post.get("offering_id", 0))).exists()
            if not offering or not offering.active or not offering.is_published:
                raise ValidationError(_("The selected academic offering is not available."))
            required = ["applicant_name", "identification_type", "identification", "birth_date", "email", "phone", "country_id", "state_id", "canton", "district", "street"]
            missing = [key for key in required if not post.get(key)]
            if missing:
                raise ValidationError(_("Complete all required fields."))
            country = request.env["res.country"].sudo().browse(int(post["country_id"])).exists()
            state = request.env["res.country.state"].sudo().browse(int(post["state_id"])).exists()
            if not country or not state or state.country_id != country:
                raise ValidationError(_("Select a valid province/state for the selected country."))
            partner = request.env.user.partner_id
            application = request.env["academic.application"].sudo().create({
                "partner_id": partner.id,
                "offering_id": offering.id,
                "applicant_name": post["applicant_name"].strip(),
                "identification_type": post["identification_type"],
                "identification": post["identification"].strip(),
                "birth_date": post["birth_date"],
                "email": post["email"].strip(),
                "phone": post["phone"].strip(),
                "country_id": country.id,
                "state_id": state.id,
                "canton": post["canton"].strip(),
                "district": post["district"].strip(),
                "street": post["street"].strip(),
            })
            return request.redirect("/my/admissions/%s" % application.id)
        except (ValidationError, ValueError) as exc:
            return self._portal_error(exc)

    @http.route(["/my/admissions/<int:application_id>/upload"], type="http", auth="user", methods=["POST"], website=True, csrf=True)
    def portal_upload_document(self, application_id, **post):
        try:
            application = self._owned_application(application_id)
            if application.state not in ("draft", "correction"):
                raise ValidationError(_("Documents can only be changed while the application is in Draft or Correction Required."))
            document_type = request.env["academic.document.type"].sudo().browse(int(post.get("document_type_id", 0))).exists()
            upload = request.httprequest.files.get("document")
            if not document_type or not upload or not upload.filename:
                raise ValidationError(_("Select a document type and file."))
            content = upload.read()
            max_mb = int(request.env["ir.config_parameter"].sudo().get_param("academic.max_upload_mb", "10") or 10)
            if len(content) > max_mb * 1024 * 1024:
                raise ValidationError(_("The file exceeds the maximum size of %s MB.") % max_mb)
            mime = upload.mimetype or "application/octet-stream"
            if mime not in {"application/pdf", "image/jpeg", "image/png"}:
                raise ValidationError(_("Only PDF, JPG/JPEG and PNG files are allowed."))
            existing = request.env["academic.application.document"].sudo().search([
                ("application_id", "=", application.id),
                ("document_type_id", "=", document_type.id),
            ], limit=1)

            attachment = request.env["ir.attachment"].sudo().create({
                "name": upload.filename,
                "datas": base64.b64encode(content),
                "mimetype": mime,
            })

            if existing:
                old_attachment = existing.attachment_id
                existing.write({
                    "attachment_id": attachment.id,
                    "state": "pending",
                    "review_note": False,
                })
                if old_attachment and old_attachment.exists():
                    old_attachment.unlink()
            else:
                request.env["academic.application.document"].sudo().create({
                    "application_id": application.id,
                    "document_type_id": document_type.id,
                    "attachment_id": attachment.id,
                })
            return request.redirect("/my/admissions/%s" % application.id)
        except (AccessError, ValidationError, ValueError) as exc:
            return self._portal_error(exc, application if "application" in locals() else None)

    @http.route(["/my/admissions/<int:application_id>/guarantor"], type="http", auth="user", methods=["POST"], website=True, csrf=True)
    def portal_add_guarantor(self, application_id, **post):
        try:
            application = self._owned_application(application_id)
            if application.state not in ("draft", "correction"):
                raise ValidationError(_("The guarantor can no longer be changed in the current state."))
            required = ["name", "relationship", "identification", "phone", "email"]
            if any(not post.get(k) for k in required):
                raise ValidationError(_("Complete all guarantor fields."))
            Partner = request.env["res.partner"].sudo()
            partner = Partner.search([("academic_identification", "=", post["identification"].strip())], limit=1)
            if not partner:
                partner = Partner.create({
                    "name": post["name"].strip(), "phone": post["phone"].strip(), "email": post["email"].strip(),
                    "academic_identification": post["identification"].strip(), "academic_identification_type": "other",
                })
            request.env["academic.guarantor"].sudo().create({
                "application_id": application.id, "partner_id": partner.id,
                "relationship": post["relationship"].strip(), "identification": post["identification"].strip(),
                "phone": post["phone"].strip(), "email": post["email"].strip(),
            })
            return request.redirect("/my/admissions/%s" % application.id)
        except (AccessError, ValidationError) as exc:
            return self._portal_error(exc, application if "application" in locals() else None)


    @http.route(["/my/admissions/<int:application_id>/update"], type="http", auth="user", methods=["POST"], website=True, csrf=True)
    def portal_update_application(self, application_id, **post):
        try:
            application = self._owned_application(application_id)
            if application.state not in ("draft", "correction"):
                raise ValidationError(_("The application data can no longer be changed in the current state."))
            required = ["applicant_name", "identification_type", "identification", "birth_date", "email", "phone", "country_id", "state_id", "canton", "district", "street"]
            if any(not post.get(k) for k in required):
                raise ValidationError(_("Complete all required fields."))
            country = request.env["res.country"].sudo().browse(int(post["country_id"])).exists()
            state = request.env["res.country.state"].sudo().browse(int(post["state_id"])).exists()
            if not country or not state or state.country_id != country:
                raise ValidationError(_("Select a valid province/state for the selected country."))
            application.write({
                "applicant_name": post["applicant_name"].strip(),
                "identification_type": post["identification_type"],
                "identification": post["identification"].strip(),
                "birth_date": post["birth_date"],
                "email": post["email"].strip(),
                "phone": post["phone"].strip(),
                "country_id": country.id,
                "state_id": state.id,
                "canton": post["canton"].strip(),
                "district": post["district"].strip(),
                "street": post["street"].strip(),
            })
            application._sync_partner()
            application._log_event("portal_updated", _("Applicant updated application data from portal"))
            return request.redirect("/my/admissions/%s" % application.id)
        except (AccessError, ValidationError, ValueError) as exc:
            return self._portal_error(exc, application if "application" in locals() else None)

    @http.route(["/my/admissions/<int:application_id>/convalidation"], type="http", auth="user", methods=["POST"], website=True, csrf=True)
    def portal_request_convalidation(self, application_id, **post):
        try:
            application = self._owned_application(application_id)
            if application.state not in ("approved", "enrolled"):
                raise ValidationError(_("Convalidation can only be requested once the admission has been approved."))
            description = (post.get("description") or "").strip()
            if not description:
                raise ValidationError(_("Describe the convalidation request."))
            convalidation = request.env["academic.convalidation"].sudo().create({
                "application_id": application.id,
                "description": description,
            })
            attachments = request.env["ir.attachment"].sudo()
            max_mb = int(request.env["ir.config_parameter"].sudo().get_param("academic.max_upload_mb", "10") or 10)
            for upload in request.httprequest.files.getlist("convalidation_documents"):
                if not upload or not upload.filename:
                    continue
                content = upload.read()
                mime = upload.mimetype or "application/octet-stream"
                if mime not in {"application/pdf", "image/jpeg", "image/png"}:
                    raise ValidationError(_("Convalidation attachments must be PDF, JPG/JPEG or PNG."))
                if len(content) > max_mb * 1024 * 1024:
                    raise ValidationError(_("A convalidation attachment exceeds the maximum size of %s MB.") % max_mb)
                attachment = request.env["ir.attachment"].sudo().create({
                    "name": upload.filename,
                    "datas": base64.b64encode(content),
                    "mimetype": mime,
                    "res_model": "academic.convalidation",
                    "res_id": convalidation.id,
                })
                attachments |= attachment
            if attachments:
                convalidation.write({"attachment_ids": [(6, 0, attachments.ids)]})
            convalidation.action_submit()
            return request.redirect("/my/admissions/%s" % application.id)
        except (AccessError, ValidationError, UserError) as exc:
            if "convalidation" in locals() and convalidation and convalidation.state == "draft":
                convalidation.unlink()
            return self._portal_error(exc, application if "application" in locals() else None)

    @http.route(["/my/admissions/<int:application_id>/submit"], type="http", auth="user", methods=["POST"], website=True, csrf=True)
    def portal_submit_application(self, application_id, **post):
        try:
            application = self._owned_application(application_id)
            application.action_submit()
            return request.redirect("/my/admissions/%s" % application.id)
        except (AccessError, ValidationError, UserError) as exc:
            return self._portal_error(exc, application if "application" in locals() else None)
