from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class AcademicProgramUltra(models.Model):
    _inherit = 'academic.program'
    degree_type = fields.Selection([('certificate','Certificado'),('technical','Técnico'),('diploma','Diplomado'),('bachelor','Bachillerato'),('licentiate','Licenciatura'),('master','Maestría'),('doctorate','Doctorado')], string='Grado académico', default='bachelor')
    expected_periods = fields.Integer('Duración en periodos', default=8)
    max_periods = fields.Integer('Máximo de periodos', default=16)
    min_credits_period = fields.Float('Créditos mínimos por periodo')
    max_credits_period = fields.Float('Créditos máximos por periodo', default=18)
    passing_grade = fields.Float('Nota mínima general', default=70)
    attendance_min = fields.Float('Asistencia mínima %', default=0)


class AcademicPeriodUltra(models.Model):
    _inherit = 'academic.period'
    registration_start = fields.Datetime('Inicio matrícula')
    registration_end = fields.Datetime('Fin matrícula')
    add_drop_end = fields.Datetime('Fin cambios sin penalización')
    withdrawal_end = fields.Datetime('Fin retiro académico')
    grades_deadline = fields.Datetime('Fecha límite de notas')
    state = fields.Selection([('planned','Planificado'),('registration','Matrícula'),('classes','En clases'),('grading','Cierre de notas'),('closed','Cerrado')], default='planned', string='Estado académico')


class AcademicCourseUltra(models.Model):
    _inherit = 'academic.course'
    duration_weeks = fields.Integer('Duración (semanas)', default=16)
    contact_hours = fields.Float('Horas con docente')
    independent_hours = fields.Float('Horas de trabajo independiente')
    lab_hours = fields.Float('Horas laboratorio')
    course_type = fields.Selection([('theory','Teórico'),('lab','Laboratorio'),('mixed','Teórico-práctico'),('practice','Práctica'),('seminar','Seminario'),('thesis','TFG / Tesis')], default='theory', string='Tipo')
    min_credits_required = fields.Float('Créditos aprobados requeridos')
    min_gpa_required = fields.Float('Promedio mínimo requerido')
    syllabus = fields.Html('Programa / Sílabo')
    learning_outcomes = fields.Html('Resultados de aprendizaje')
    methodology = fields.Html('Metodología')
    bibliography = fields.Html('Bibliografía')


class AcademicCurriculumLineUltra(models.Model):
    _inherit = 'academic.curriculum.line'
    period_label = fields.Char('Periodo sugerido')
    area = fields.Char('Área académica')
    unlocks_ids = fields.Many2many('academic.course', 'academic_curriculum_unlock_rel', 'line_id', 'course_id', string='Desbloquea')


class AcademicScheduleSlot(models.Model):
    _name = 'academic.schedule.slot'
    _description = 'Bloque horario académico'
    _order = 'weekday, hour_from'
    section_id = fields.Many2one('academic.section', required=True, ondelete='cascade', index=True)
    weekday = fields.Selection([('0','Lunes'),('1','Martes'),('2','Miércoles'),('3','Jueves'),('4','Viernes'),('5','Sábado'),('6','Domingo')], required=True, string='Día')
    hour_from = fields.Float('Desde', required=True)
    hour_to = fields.Float('Hasta', required=True)
    room = fields.Char('Aula')
    campus = fields.Char('Sede')
    @api.constrains('hour_from','hour_to')
    def _check_hours(self):
        for r in self:
            if r.hour_from < 0 or r.hour_to > 24 or r.hour_from >= r.hour_to:
                raise ValidationError(_('El bloque horario no es válido.'))


class AcademicSectionUltra(models.Model):
    _inherit = 'academic.section'
    schedule_slot_ids = fields.One2many('academic.schedule.slot', 'section_id', string='Horario estructurado')
    start_date = fields.Date('Inicio de clases')
    end_date = fields.Date('Fin de clases')
    registration_deadline = fields.Datetime('Cierre matrícula de sección')
    waitlist_capacity = fields.Integer('Cupo lista de espera', default=10)
    delivery_language = fields.Char('Idioma')


class AcademicRegistrationUltra(models.Model):
    _inherit = 'academic.course.registration'
    attempt_number = fields.Integer('Intento', default=1, readonly=True)
    eligibility_state = fields.Selection([('eligible','Elegible'),('blocked','Bloqueado'),('override','Excepción autorizada')], default='eligible', string='Elegibilidad', tracking=True)
    eligibility_message = fields.Text('Detalle de elegibilidad', readonly=True)
    override_user_id = fields.Many2one('res.users', 'Autorizado por', readonly=True)
    progress_percent = fields.Float('Avance del curso %', compute='_compute_progress')

    @api.depends('grade_ids.state','grade_ids.assessment_id.weight')
    def _compute_progress(self):
        for r in self:
            r.progress_percent = min(sum(r.grade_ids.filtered(lambda g:g.state=='published').mapped('assessment_id.weight')), 100.0)

    def _passed_course_ids(self):
        self.ensure_one()
        return set(self.search([('student_id','=',self.student_id.id),('state','=','completed'),('passed','=',True)]).mapped('course_id').ids)

    def check_eligibility(self, raise_error=False):
        for r in self:
            reasons=[]
            holds=r.student_id.hold_ids.filtered(lambda h:h.active and h.blocking and (not h.date_to or h.date_to >= fields.Date.today()))
            if holds: reasons.append(_('Tiene bloqueos activos: %s') % ', '.join(holds.mapped('name')))
            passed=r._passed_course_ids()
            missing=r.course_id.prerequisite_ids.filtered(lambda c:c.id not in passed)
            if missing: reasons.append(_('Faltan prerrequisitos: %s') % ', '.join(missing.mapped('code')))
            if r.course_id.min_credits_required and r.student_id.credits_approved < r.course_id.min_credits_required:
                reasons.append(_('Requiere %.1f créditos aprobados.') % r.course_id.min_credits_required)
            if r.course_id.min_gpa_required and r.student_id.gpa < r.course_id.min_gpa_required:
                reasons.append(_('Requiere promedio mínimo %.2f.') % r.course_id.min_gpa_required)
            others=self.search([('student_id','=',r.student_id.id),('period_id','=',r.period_id.id),('state','in',['requested','enrolled']),('id','!=',r.id)])
            for other in others:
                for a in r.section_id.schedule_slot_ids:
                    for b in other.section_id.schedule_slot_ids:
                        if a.weekday==b.weekday and max(a.hour_from,b.hour_from) < min(a.hour_to,b.hour_to):
                            reasons.append(_('Choque de horario con %s.') % other.course_id.code); break
            r.eligibility_state='blocked' if reasons else 'eligible'
            r.eligibility_message='\n'.join(reasons) if reasons else _('Cumple todos los requisitos de matrícula.')
            if reasons and raise_error: raise UserError(r.eligibility_message)
        return True

    def action_enroll(self):
        self.check_eligibility(raise_error=True)
        return super().action_enroll()


class AcademicStudentUltra(models.Model):
    _inherit = 'academic.student'
    credits_approved = fields.Float('Créditos aprobados', compute='_compute_academic_kpis')
    credits_attempted = fields.Float('Créditos cursados', compute='_compute_academic_kpis')
    gpa = fields.Float('Promedio ponderado', compute='_compute_academic_kpis')
    career_progress = fields.Float('Avance de carrera %', compute='_compute_academic_kpis')
    remaining_credits = fields.Float('Créditos pendientes', compute='_compute_academic_kpis')
    expected_graduation = fields.Date('Graduación estimada')

    def _compute_academic_kpis(self):
        Reg=self.env['academic.course.registration']
        for s in self:
            regs=Reg.search([('student_id','=',s.id),('state','=','completed')])
            approved=regs.filtered('passed')
            s.credits_attempted=sum(regs.mapped('course_id.credits'))
            s.credits_approved=sum(approved.mapped('course_id.credits'))
            denom=sum(regs.mapped('course_id.credits'))
            s.gpa=(sum(r.final_grade*r.course_id.credits for r in regs)/denom) if denom else 0
            required=s.curriculum_id.graduation_credits if s.curriculum_id else 0
            s.career_progress=min((s.credits_approved/required*100),100) if required else 0
            s.remaining_credits=max(required-s.credits_approved,0)


class AcademicServiceCatalog(models.Model):
    _name='academic.service.catalog'
    _description='Catálogo de trámites estudiantiles'
    name=fields.Char('Trámite', required=True, translate=True)
    category=fields.Selection([('academic','Académico'),('financial','Financiero'),('records','Registro'),('graduation','Graduación'),('student_life','Vida estudiantil'),('other','Otro')], default='academic', required=True)
    description=fields.Html('Descripción')
    fee=fields.Monetary('Costo')
    currency_id=fields.Many2one('res.currency', default=lambda s:s.env.company.currency_id)
    sla_days=fields.Integer('Tiempo objetivo (días)', default=3)
    requires_attachment=fields.Boolean('Requiere adjunto')
    active=fields.Boolean(default=True)
    company_id=fields.Many2one('res.company', default=lambda s:s.env.company, required=True)
