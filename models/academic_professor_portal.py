from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AcademicSectionProfessorPortal(models.Model):
    _inherit = 'academic.section'

    gradebook_state = fields.Selection([
        ('draft', 'En preparación'), ('open', 'Captura abierta'),
        ('submitted', 'Enviado a revisión'), ('closed', 'Acta cerrada')
    ], default='draft', string='Estado del acta', tracking=True)
    gradebook_submitted_at = fields.Datetime('Acta enviada el', readonly=True)
    gradebook_closed_at = fields.Datetime('Acta cerrada el', readonly=True)
    class_notes = fields.Html('Bitácora / notas docentes')

    def action_open_gradebook(self):
        self.write({'gradebook_state': 'open'})

    def action_submit_gradebook(self):
        for rec in self:
            total = sum(rec.assessment_ids.mapped('weight'))
            if abs(total - 100.0) > 0.01:
                raise UserError(_('La ponderación de evaluaciones debe sumar 100%%. Actualmente suma %.2f%%.') % total)
            missing = []
            enrolled = rec.registration_ids.filtered(lambda r: r.state in ('enrolled', 'completed'))
            for assessment in rec.assessment_ids:
                graded = assessment.grade_ids.mapped('registration_id')
                for registration in enrolled - graded:
                    missing.append('%s / %s' % (assessment.name, registration.student_id.display_name))
            if missing:
                raise UserError(_('No puede enviar el acta: existen calificaciones pendientes.\n%s') % '\n'.join(missing[:20]))
            rec.write({'gradebook_state': 'submitted', 'gradebook_submitted_at': fields.Datetime.now()})

    def action_close_gradebook(self):
        self.write({'gradebook_state': 'closed', 'gradebook_closed_at': fields.Datetime.now()})


class AcademicAssessmentProfessorPortal(models.Model):
    _inherit = 'academic.assessment'

    instructions = fields.Html('Instrucciones')
    due_datetime = fields.Datetime('Fecha y hora límite')

    @api.constrains('section_id', 'weight')
    def _check_section_total_weight(self):
        for rec in self:
            if rec.section_id:
                total = sum(rec.section_id.assessment_ids.filtered(lambda a: a.id != rec.id).mapped('weight')) + rec.weight
                if total > 100.01:
                    raise ValidationError(_('La ponderación total de la sección no puede superar 100%%.'))


class AcademicGradeProfessorPortal(models.Model):
    _inherit = 'academic.grade'

    published_at = fields.Datetime('Publicada el', readonly=True)
    published_by = fields.Many2one('res.users', 'Publicada por', readonly=True)

    def write(self, vals):
        if any(key in vals for key in ('score', 'feedback', 'assessment_id', 'registration_id')):
            closed = self.filtered(lambda g: g.section_id.gradebook_state == 'closed')
            if closed and not self.env.user.has_group('academic_admission_enrollment.group_academic_registrar') and not self.env.user.has_group('academic_admission_enrollment.group_academic_manager'):
                raise UserError(_('El acta está cerrada. Solicite una rectificación de nota a Registro Académico.'))
        return super().write(vals)

    def action_publish(self):
        self.write({'state': 'published', 'published_at': fields.Datetime.now(), 'published_by': self.env.user.id})


class AcademicGradeChangeRequest(models.Model):
    _name = 'academic.grade.change.request'
    _description = 'Solicitud de rectificación de nota'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(default=lambda self: _('Rectificación de nota'), required=True)
    grade_id = fields.Many2one('academic.grade', required=True, ondelete='restrict', tracking=True)
    professor_id = fields.Many2one('academic.professor', required=True, ondelete='restrict', tracking=True)
    student_id = fields.Many2one(related='grade_id.student_id', store=True)
    section_id = fields.Many2one(related='grade_id.section_id', store=True)
    old_score = fields.Float(related='grade_id.score', string='Nota actual', readonly=True)
    requested_score = fields.Float('Nota solicitada', required=True, tracking=True)
    reason = fields.Text('Justificación', required=True, tracking=True)
    evidence_ids = fields.Many2many('ir.attachment', string='Evidencias')
    state = fields.Selection([('draft','Borrador'),('submitted','En revisión'),('approved','Aprobada'),('rejected','Rechazada')], default='draft', tracking=True)
    reviewed_by = fields.Many2one('res.users', readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    company_id = fields.Many2one(related='section_id.company_id', store=True)

    @api.constrains('requested_score', 'grade_id')
    def _check_requested_score(self):
        for rec in self:
            if rec.requested_score < 0 or (rec.grade_id and rec.requested_score > rec.grade_id.assessment_id.max_score):
                raise ValidationError(_('La nota solicitada está fuera del rango permitido.'))

    def action_submit(self): self.write({'state': 'submitted'})
    def action_approve(self):
        for rec in self:
            rec.grade_id.sudo().write({'score': rec.requested_score})
            rec.write({'state':'approved','reviewed_by':self.env.user.id,'reviewed_at':fields.Datetime.now()})
    def action_reject(self):
        self.write({'state':'rejected','reviewed_by':self.env.user.id,'reviewed_at':fields.Datetime.now()})
