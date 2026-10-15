from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class AcademicCurriculum(models.Model):
    _name = 'academic.curriculum'
    _description = 'Plan de estudios'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'program_id, effective_from desc'

    name = fields.Char('Plan', required=True, tracking=True)
    code = fields.Char('Código', required=True, index=True)
    program_id = fields.Many2one('academic.program', string='Programa', required=True, ondelete='cascade', tracking=True)
    version = fields.Char('Versión', required=True, default='1.0')
    effective_from = fields.Date('Vigente desde', required=True, default=fields.Date.context_today)
    effective_to = fields.Date('Vigente hasta')
    graduation_credits = fields.Float('Créditos para graduación', required=True, default=120)
    min_gpa = fields.Float('Promedio mínimo', default=70)
    line_ids = fields.One2many('academic.curriculum.line', 'curriculum_id', string='Malla curricular')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company, index=True)
    _sql_constraints = [('curriculum_code_company_uniq','unique(code, company_id)','El código del plan debe ser único por compañía.')]


class AcademicCurriculumLine(models.Model):
    _name = 'academic.curriculum.line'
    _description = 'Materia del plan de estudios'
    _order = 'level, sequence, id'

    curriculum_id = fields.Many2one('academic.curriculum', required=True, ondelete='cascade', index=True)
    course_id = fields.Many2one('academic.course', string='Materia', required=True, ondelete='restrict')
    level = fields.Integer('Nivel / ciclo', default=1, required=True)
    sequence = fields.Integer('Orden', default=10)
    requirement_type = fields.Selection([('required','Obligatoria'),('elective','Electiva'),('optional','Optativa'),('thesis','TFG / Tesis'),('practice','Práctica profesional')], default='required', required=True)
    corequisite_ids = fields.Many2many('academic.course', 'academic_curriculum_coreq_rel', 'line_id', 'course_id', string='Correquisitos')
    min_grade = fields.Float('Nota mínima', default=70)
    credits = fields.Float(related='course_id.credits', store=True)
    _sql_constraints = [('curriculum_course_uniq','unique(curriculum_id, course_id)','La materia ya está en este plan de estudios.')]


class AcademicHold(models.Model):
    _name = 'academic.hold'
    _description = 'Bloqueo del estudiante'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'active desc, blocking desc, id desc'

    name = fields.Char('Motivo', required=True, tracking=True)
    student_id = fields.Many2one('academic.student', required=True, ondelete='cascade', index=True, tracking=True)
    hold_type = fields.Selection([('financial','Financiero'),('academic','Académico'),('disciplinary','Disciplinario'),('documents','Documentación'),('library','Biblioteca'),('other','Otro')], required=True, default='academic')
    blocking = fields.Boolean('Impide matrícula', default=True, tracking=True)
    blocks_graduation = fields.Boolean('Impide graduación', default=False)
    date_from = fields.Date('Desde', default=fields.Date.context_today, required=True)
    date_to = fields.Date('Hasta')
    notes = fields.Text('Detalle')
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(related='student_id.company_id', store=True, index=True)


class AcademicRequest(models.Model):
    _name = 'academic.request'
    _description = 'Solicitud académica'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default=lambda s: _('Nueva'), copy=False, readonly=True)
    student_id = fields.Many2one('academic.student', required=True, ondelete='restrict', tracking=True)
    request_type = fields.Selection([('certificate','Certificación'),('transcript','Expediente / notas'),('withdrawal','Retiro de materia'),('program_change','Cambio de carrera'),('freeze','Congelamiento'),('reentry','Reingreso'),('graduation','Graduación'),('appeal','Apelación de nota'),('special_exam','Examen extraordinario'),('other','Otro')], required=True, tracking=True)
    description = fields.Text('Solicitud', required=True)

    service_id = fields.Many2one(
        'academic.service.catalog',
        string='Servicio solicitado',
        ondelete='restrict',
        tracking=True,
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'academic_request_attachment_rel',
        'request_id',
        'attachment_id',
        string='Documentos adjuntos',
    )
    service_fee = fields.Monetary(
        string='Costo del servicio',
        related='service_id.fee',
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='service_id.currency_id',
        readonly=True,
    )
    sla_days = fields.Integer(
        string='Tiempo objetivo (días)',
        related='service_id.sla_days',
        readonly=True,
    )

    state = fields.Selection([('draft','Borrador'),('submitted','Presentada'),('review','En revisión'),('approved','Aprobada'),('rejected','Rechazada'),('done','Completada'),('cancelled','Cancelada')], default='draft', tracking=True)
    resolution = fields.Text('Resolución')
    responsible_id = fields.Many2one('res.users', string='Responsable', tracking=True)
    date_submitted = fields.Datetime('Presentada el', readonly=True)
    company_id = fields.Many2one(related='student_id.company_id', store=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nueva')) == _('Nueva'):
                vals['name'] = self.env['ir.sequence'].next_by_code('academic.request') or _('Nueva')
        return super().create(vals_list)

    def action_submit(self): self.write({'state':'submitted','date_submitted':fields.Datetime.now()})
    def action_approve(self): self.write({'state':'approved'})
    def action_reject(self): self.write({'state':'rejected'})
    def action_done(self): self.write({'state':'done'})


class AcademicStudentEnterprise(models.Model):
    _inherit = 'academic.student'

    curriculum_id = fields.Many2one('academic.curriculum', string='Plan de estudios', tracking=True)
    advisor_id = fields.Many2one('academic.professor', string='Asesor académico', tracking=True)
    hold_ids = fields.One2many('academic.hold', 'student_id', string='Bloqueos')
    request_ids = fields.One2many('academic.request', 'student_id', string='Solicitudes')
    registration_ids = fields.One2many('academic.course.registration', 'student_id', string='Materias')
    active_hold_count = fields.Integer(compute='_compute_academic_metrics')
    earned_credits = fields.Float(compute='_compute_academic_metrics')
    attempted_credits = fields.Float(compute='_compute_academic_metrics')
    academic_average = fields.Float('Promedio académico', compute='_compute_academic_metrics')
    progress_percent = fields.Float('Avance %', compute='_compute_academic_metrics')
    academic_status = fields.Selection([('good','Regular'),('warning','En observación'),('probation','Prueba académica'),('suspended','Suspendido'),('graduated','Graduado')], default='good', tracking=True)

    def _compute_academic_metrics(self):
        for rec in self:
            regs = rec.registration_ids.filtered(lambda r: r.state in ('enrolled','completed'))
            completed = regs.filtered(lambda r: r.state == 'completed')
            passed = completed.filtered('passed')
            rec.active_hold_count = len(rec.hold_ids.filtered(lambda h: h.active and h.blocking and (not h.date_to or h.date_to >= fields.Date.today())))
            rec.attempted_credits = sum(completed.mapped('course_id.credits'))
            rec.earned_credits = sum(passed.mapped('course_id.credits'))
            weighted = sum(r.final_grade * (r.course_id.credits or 1) for r in completed)
            weights = sum((r.course_id.credits or 1) for r in completed)
            rec.academic_average = weighted / weights if weights else 0
            required = rec.curriculum_id.graduation_credits or 0
            rec.progress_percent = min(100.0, rec.earned_credits / required * 100.0) if required else 0


class AcademicRegistrationEnterprise(models.Model):
    _inherit = 'academic.course.registration'

    attempt_number = fields.Integer('Intento', default=1, readonly=True)
    registration_date = fields.Datetime('Fecha de matrícula', default=fields.Datetime.now)
    withdrawal_date = fields.Date('Fecha de retiro')
    withdrawal_reason = fields.Text('Motivo de retiro')

    def action_enroll(self):
        for rec in self:
            holds = rec.student_id.hold_ids.filtered(lambda h: h.active and h.blocking and (not h.date_to or h.date_to >= fields.Date.today()))
            if holds:
                raise UserError(_('El estudiante tiene bloqueos que impiden la matrícula: %s') % ', '.join(holds.mapped('name')))
            missing = rec.course_id.prerequisite_ids.filtered(lambda c: not self.search_count([('student_id','=',rec.student_id.id),('course_id','=',c.id),('state','=','completed'),('passed','=',True)]))
            if missing:
                raise UserError(_('No cumple los prerrequisitos: %s') % ', '.join(missing.mapped('display_name')))
        return super().action_enroll()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('student_id') and vals.get('section_id'):
                section = self.env['academic.section'].browse(vals['section_id'])
                previous = self.search_count([('student_id','=',vals['student_id']),('course_id','=',section.course_id.id),('state','in',['completed','withdrawn'])])
                vals['attempt_number'] = previous + 1
        return super().create(vals_list)
