import base64

from odoo import http, _
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.http import request


class AcademicExperiencePortal(http.Controller):

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def _partner(self):
        return request.env.user.partner_id

    def _student(self, required=True):
        student = request.env["academic.student"].sudo().search([
            ("partner_id", "=", self._partner().id)
        ], limit=1)

        if required and not student:
            raise AccessError(
                _("No existe un expediente estudiantil asociado a este usuario.")
            )
        return student

    def _applications(self):
        return request.env["academic.application"].sudo().search([
            ("partner_id", "=", self._partner().id)
        ], order="create_date desc")

    def _dashboard_values(self):
        student = self._student(required=False)
        applications = self._applications()

        regs = request.env["academic.course.registration"].sudo()
        requests = request.env["academic.request"].sudo()
        services = request.env["academic.service.catalog"].sudo()

        if student:
            regs = regs.search([
                ("student_id", "=", student.id)
            ], order="id desc")

            requests = requests.search([
                ("student_id", "=", student.id)
            ], order="id desc")

            services = services.search([
                ("active", "=", True),
                ("company_id", "=", student.company_id.id),
            ], order="category, name")

        return {
            "partner": self._partner(),
            "student": student,
            "applications": applications,
            "registrations": regs,
            "active_regs": regs.filtered(lambda r: r.state == "enrolled"),
            "academic_requests": requests,
            "services": services,
        }

    # ---------------------------------------------------------
    # Dashboard unificado
    # ---------------------------------------------------------

    @http.route(
        "/my/academic",
        type="http",
        auth="user",
        website=True,
    )
    def academic_home(self, **kw):
        return request.render(
            "academic_admission_enrollment.portal_academic_home",
            self._dashboard_values(),
        )

    # ---------------------------------------------------------
    # Expediente / notas
    # ---------------------------------------------------------

    @http.route(
        "/my/academic/grades",
        type="http",
        auth="user",
        website=True,
    )
    def academic_grades(self, **kw):
        student = self._student()

        regs = request.env["academic.course.registration"].sudo().search([
            ("student_id", "=", student.id)
        ])

        return request.render(
            "academic_admission_enrollment.portal_academic_grades",
            {
                "student": student,
                "registrations": regs,
            },
        )

    # ---------------------------------------------------------
    # Matrícula por cursos
    # ---------------------------------------------------------

    @http.route(
        "/my/academic/enroll",
        type="http",
        auth="user",
        website=True,
    )
    def academic_enroll(self, **kw):
        student = self._student()

        sections = request.env["academic.section"].sudo().search([
            ("state", "=", "open"),
            ("course_id.program_id", "=", student.program_id.id),
        ])

        registered = request.env[
            "academic.course.registration"
        ].sudo().search([
            ("student_id", "=", student.id)
        ]).mapped("section_id").ids

        return request.render(
            "academic_admission_enrollment.portal_academic_enroll",
            {
                "student": student,
                "sections": sections,
                "registered_ids": registered,
            },
        )

    @http.route(
        "/my/academic/enroll/<int:section_id>",
        type="http",
        auth="user",
        methods=["POST"],
        website=True,
        csrf=True,
    )
    def academic_enroll_section(self, section_id, **post):
        student = self._student()

        section = request.env["academic.section"].sudo().browse(
            section_id
        ).exists()

        if (
            not section
            or section.state != "open"
            or section.course_id.program_id != student.program_id
        ):
            raise ValidationError(
                _("Esta sección no está disponible para matrícula.")
            )

        existing = request.env[
            "academic.course.registration"
        ].sudo().search([
            ("student_id", "=", student.id),
            ("section_id", "=", section.id),
            ("state", "in", ["requested", "enrolled", "waitlist"]),
        ], limit=1)

        if existing:
            raise ValidationError(
                _("Ya existe una matrícula o solicitud activa para esta sección.")
            )

        registration = request.env[
            "academic.course.registration"
        ].sudo().create({
            "student_id": student.id,
            "section_id": section.id,
        })

        registration.action_enroll()

        return request.redirect("/my/academic")

    # ---------------------------------------------------------
    # Plan de estudios
    # ---------------------------------------------------------

    @http.route(
        "/my/academic/plan",
        type="http",
        auth="user",
        website=True,
    )
    def academic_plan(self, **kw):
        student = self._student()

        lines = (
            student.curriculum_id.line_ids.sorted(
                lambda line: (line.level, line.sequence)
            )
            if student.curriculum_id
            else request.env["academic.curriculum.line"]
        )

        regs = request.env[
            "academic.course.registration"
        ].sudo().search([
            ("student_id", "=", student.id)
        ])

        passed = set(
            regs.filtered(
                lambda r: r.state == "completed" and r.passed
            ).mapped("course_id").ids
        )

        active = set(
            regs.filtered(
                lambda r: r.state == "enrolled"
            ).mapped("course_id").ids
        )

        return request.render(
            "academic_admission_enrollment.portal_academic_plan",
            {
                "student": student,
                "lines": lines,
                "passed": passed,
                "active": active,
            },
        )

    # ---------------------------------------------------------
    # Trámites estudiantiles
    # ---------------------------------------------------------

    @http.route(
        "/my/academic/services",
        type="http",
        auth="user",
        website=True,
    )
    def academic_services(self, **kw):
        student = self._student()

        services = request.env[
            "academic.service.catalog"
        ].sudo().search([
            ("active", "=", True),
            ("company_id", "=", student.company_id.id),
        ], order="category, name")

        reqs = request.env["academic.request"].sudo().search([
            ("student_id", "=", student.id)
        ], order="id desc")

        return request.render(
            "academic_admission_enrollment.portal_academic_services",
            {
                "student": student,
                "services": services,
                "requests": reqs,
                "success": kw.get("success"),
                "error": kw.get("error"),
            },
        )

    @http.route(
        "/my/academic/services/create",
        type="http",
        auth="user",
        methods=["POST"],
        website=True,
        csrf=True,
    )
    def academic_service_create(self, **post):
        student = self._student()

        service_id = post.get("service_id")
        description = (post.get("description") or "").strip()

        try:
            service_id = int(service_id or 0)
        except (TypeError, ValueError):
            service_id = 0

        service = request.env[
            "academic.service.catalog"
        ].sudo().browse(service_id).exists()

        if (
            not service
            or not service.active
            or service.company_id != student.company_id
        ):
            return request.redirect(
                "/my/academic/services?error=invalid_service"
            )

        if not description:
            return request.redirect(
                "/my/academic/services?error=missing_description"
            )

        uploads = [
            upload
            for upload in request.httprequest.files.getlist("attachments")
            if upload and upload.filename
        ]

        if service.requires_attachment and not uploads:
            return request.redirect(
                "/my/academic/services?error=attachment_required"
            )

        max_mb = int(
            request.env["ir.config_parameter"].sudo().get_param(
                "academic.max_upload_mb",
                "10",
            ) or 10
        )

        allowed_mimetypes = {
            "application/pdf",
            "image/jpeg",
            "image/png",
        }

        prepared_uploads = []

        for upload in uploads:
            content = upload.read()
            mimetype = upload.mimetype or "application/octet-stream"

            if mimetype not in allowed_mimetypes:
                return request.redirect(
                    "/my/academic/services?error=invalid_attachment"
                )

            if len(content) > max_mb * 1024 * 1024:
                return request.redirect(
                    "/my/academic/services?error=attachment_too_large"
                )

            prepared_uploads.append(
                (upload.filename, mimetype, content)
            )

        request_type_map = {
            "records": "transcript",
            "graduation": "graduation",
            "financial": "other",
            "student_life": "other",
            "academic": "other",
            "other": "other",
        }

        academic_request = request.env[
            "academic.request"
        ].sudo().create({
            "student_id": student.id,
            "service_id": service.id,
            "request_type": request_type_map.get(
                service.category,
                "other",
            ),
            "description": description,
        })

        attachments = request.env["ir.attachment"].sudo()

        try:
            for filename, mimetype, content in prepared_uploads:
                attachment = request.env[
                    "ir.attachment"
                ].sudo().create({
                    "name": filename,
                    "datas": base64.b64encode(content),
                    "mimetype": mimetype,
                    "res_model": "academic.request",
                    "res_id": academic_request.id,
                })

                attachments |= attachment

            if attachments:
                academic_request.write({
                    "attachment_ids": [(6, 0, attachments.ids)]
                })

            academic_request.action_submit()

        except Exception:
            attachments.unlink()
            academic_request.unlink()
            raise

        return request.redirect(
            "/my/academic/services?success=1"
        )

    # ---------------------------------------------------------
    # Curso
    # ---------------------------------------------------------

    @http.route(
        "/my/academic/course/<int:registration_id>",
        type="http",
        auth="user",
        website=True,
    )
    def academic_course_detail(self, registration_id, **kw):
        student = self._student()

        reg = request.env[
            "academic.course.registration"
        ].sudo().browse(registration_id).exists()

        if not reg or reg.student_id != student:
            raise AccessError(
                _("No tiene acceso a este curso.")
            )

        return request.render(
            "academic_admission_enrollment.portal_academic_course_detail",
            {
                "student": student,
                "r": reg,
            },
        )
