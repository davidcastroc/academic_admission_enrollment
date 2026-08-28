# Academic Admission & Enrollment — Odoo 18

Production-oriented foundation for the first academic stage defined in the functional sessions: applicant portal, CRM intake, academic offering/capacity, application file, document requirements, manual or assisted review, guarantor rules, convalidation intake, approval, student creation and enrollment.

## Main capabilities

- Secure authenticated applicant portal (no public record-model ACLs).
- Draft → submission → automatic/manual review → administrative review → academic review → correction/approval/rejection → enrollment workflow.
- CRM opportunity created from every submitted application when enabled.
- Separate academic data model: CRM is not the student file.
- Academic programs, periods and offerings with capacity enforcement at enrollment.
- Configurable required document types by program/offering.
- PDF/JPG/PNG upload with MIME and size validation.
- OCR/AI processing queue and adapter extension point; default adapter routes to human review rather than inventing an external integration.
- Minor/guarantor rule with approval control.
- Convalidation request restricted to first enrollment and linked to CRM follow-up.
- Student and enrollment records with configurable student unique identifier (identification or generated card).
- Roles: Admissions, Direction/Academic Approval, Cashier and Administrator.
- Cashier users must be linked to an identifiable physical person.
- Company isolation rules.
- Immutable application audit-event model plus chatter tracking.
- Email templates for submission, correction, approval, rejection and enrollment.
- QWeb PDF application report.
- CONESUP service adapter extension point, deliberately inactive until official specs/whitelist are available.
- Transaction tests for workflow and offering capacity.

## Installation

1. Copy `academic_admission_enrollment` into an Odoo 18 custom addons path.
2. Update Apps List.
3. Install **Academic Admission & Enrollment**.
4. Assign an Academic security role to internal users.
5. Configure Academic settings from Settings.
6. Create programs, periods, offerings, document types and requirements.
7. Publish the offerings that must appear in the applicant portal.

CLI example:

```bash
odoo-bin -d DATABASE -i academic_admission_enrollment --stop-after-init
```

## Important integration note

The base addon does **not** make external OCR/AI or CONESUP calls because provider/API specifications and credentials are not part of the approved source requirements. Provider-specific addons should inherit:

- `academic.ocr.service`
- `academic.conesup.service`

This keeps the base addon installable, testable and safe while allowing the integrations to be added without rewriting the admission domain.

## Recommended next extensions

- Costa Rica geographic catalog integration if the target database has an authoritative canton/district source.
- Provider-specific OCR/AI adapter after selecting the provider and defining confidence/decision rules per document type.
- Official CONESUP adapter after receiving the API/web-service specification and whitelist authorization.
- Payment/cashier integration in the later Financial/Cash stage, rather than coupling it into admission.
- Academic curriculum/course/grade modules as a separate domain on top of `academic.student` and `academic.enrollment`.
