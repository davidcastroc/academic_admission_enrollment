from datetime import date

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestAcademicFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.program = cls.env["academic.program"].create({"name": "Engineering", "code": "ENG", "company_id": cls.company.id})
        cls.period = cls.env["academic.period"].create({"name": "2026-3", "code": "2026-3", "date_start": "2026-09-01", "date_end": "2026-12-15", "company_id": cls.company.id})
        cls.offering = cls.env["academic.offering"].create({"program_id": cls.program.id, "period_id": cls.period.id, "modality": "onsite", "capacity": 1, "company_id": cls.company.id})
        cls.partner = cls.env["res.partner"].create({"name": "Test Applicant", "email": "test@example.com"})
        cls.country = cls.env.ref("base.cr")
        cls.state = cls.env["res.country.state"].search([("country_id", "=", cls.country.id)], limit=1)
        if not cls.state:
            cls.state = cls.env["res.country.state"].create({"name": "Test Province", "code": "TST", "country_id": cls.country.id})

    def _application(self, identification="111111111"):
        return self.env["academic.application"].create({
            "partner_id": self.partner.id,
            "offering_id": self.offering.id,
            "applicant_name": "Test Applicant",
            "identification_type": "national",
            "identification": identification,
            "birth_date": "1990-01-01",
            "email": "test@example.com",
            "phone": "88888888",
            "country_id": self.country.id,
            "state_id": self.state.id,
            "canton": "Central",
            "district": "Central",
            "street": "Test address",
        })

    def test_application_approval_and_enrollment(self):
        app = self._application()
        app.action_submit()
        app.action_send_academic_review()
        app.action_approve()
        self.assertEqual(app.state, "approved")
        app.action_enroll()
        self.assertEqual(app.state, "enrolled")
        self.assertTrue(app.student_id)
        self.assertTrue(app.enrollment_id)

    def test_capacity_is_enforced(self):
        app1 = self._application("111111111")
        app1.write({"state": "approved"})
        app1.action_enroll()
        partner2 = self.env["res.partner"].create({"name": "Applicant 2"})
        app2 = self.env["academic.application"].create({
            "partner_id": partner2.id, "offering_id": self.offering.id, "applicant_name": "Applicant 2",
            "identification_type": "national", "identification": "222222222", "birth_date": "1991-01-01",
            "email": "two@example.com", "phone": "87777777", "country_id": self.country.id,
            "state_id": self.state.id, "canton": "Central", "district": "Central", "street": "Address 2",
        })
        app2.write({"state": "approved"})
        with self.assertRaises(ValidationError):
            app2.action_enroll()
