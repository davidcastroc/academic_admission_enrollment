from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class AcademicCourse(models.Model):
    _name = 'academic.course'
    _description = 'Curso / Asignatura'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'code, name'

    name = fields.Char('Nombre', required=True, translate=True, tracking=True)
    code = fields.Char('Código', required=True, index=True, tracking=True)
    program_id = fields.Many2one('academic.program', string='Programa', required=True, ondelete='cascade', tracking=True)
    credits = fields.Float('Créditos', default=3.0, tracking=True)
    hours = fields.Float('Horas', default=48.0)
    description = fields.Html('Descripción', translate=True)
    prerequisite_ids = fields.Many2many('academic.course', 'academic_course_prereq_rel', 'course_id', 'prereq_id', string='Prerrequisitos')
    active = fields.Boolean('Activo', default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    _sql_constraints = [('course_code_company_uniq', 'unique(code, company_id)', 'El código del curso debe ser único por compañía.')]


class AcademicProfessor(models.Model):
    _name = 'academic.professor'
    _description = 'Profesor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    partner_id = fields.Many2one('res.partner', string='Contacto', required=True, ondelete='restrict', tracking=True)
    user_id = fields.Many2one('res.users', string='Usuario', ondelete='set null', tracking=True)
    employee_code = fields.Char('Código de profesor', index=True, tracking=True)
    title = fields.Char('Título / especialidad')
    biography = fields.Html('Biografía')
    active = fields.Boolean('Activo', default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    section_ids = fields.Many2many('academic.section', 'academic_section_professor_rel', 'professor_id', 'section_id', string='Secciones')
    name = fields.Char(compute='_compute_name', store=True)

    @api.depends('partner_id.name', 'employee_code')
    def _compute_name(self):
        for rec in self:
            rec.name = '%s%s' % (rec.partner_id.name or '', (' · ' + rec.employee_code) if rec.employee_code else '')


class AcademicSection(models.Model):
    _name = 'academic.section'
    _description = 'Sección académica'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_id desc, course_id, code'

    name = fields.Char(compute='_compute_name', store=True)
    code = fields.Char('Sección', required=True, default='01', tracking=True)
    course_id = fields.Many2one('academic.course', string='Curso', required=True, ondelete='restrict', tracking=True)
    period_id = fields.Many2one('academic.period', string='Periodo', required=True, ondelete='restrict', tracking=True)
    professor_ids = fields.Many2many('academic.professor', 'academic_section_professor_rel', 'section_id', 'professor_id', string='Profesores', tracking=True)
    modality = fields.Selection([('onsite','Presencial'),('virtual','Virtual'),('hybrid','Híbrida')], string='Modalidad', default='onsite', required=True)
    campus = fields.Char('Sede')
    room = fields.Char('Aula / enlace')
    schedule = fields.Char('Horario', help='Ej.: Lunes y miércoles 18:00–20:00')
    capacity = fields.Integer('Cupo', default=30)
    registration_ids = fields.One2many('academic.course.registration', 'section_id', string='Estudiantes')
    assessment_ids = fields.One2many('academic.assessment', 'section_id', string='Evaluaciones')
    assignment_ids = fields.One2many('academic.assignment', 'section_id', string='Tareas')
    announcement_ids = fields.One2many('academic.announcement', 'section_id', string='Anuncios')
    enrolled_count = fields.Integer('Matriculados', compute='_compute_enrolled_count')
    available_seats = fields.Integer('Cupos disponibles', compute='_compute_enrolled_count')
    state = fields.Selection([('draft','Borrador'),('open','Abierta'),('closed','Cerrada'),('finished','Finalizada'),('cancelled','Cancelada')], default='draft', tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    @api.depends('course_id', 'period_id', 'code')
    def _compute_name(self):
        for rec in self:
            rec.name = '%s · %s · %s' % (rec.course_id.display_name or '', rec.code or '', rec.period_id.display_name or '')

    def _compute_enrolled_count(self):
        for rec in self:
            rec.enrolled_count = len(rec.registration_ids.filtered(lambda r: r.state == 'enrolled'))
            rec.available_seats = max(rec.capacity - rec.enrolled_count, 0) if rec.capacity else 0

    def action_open(self): self.write({'state': 'open'})
    def action_close(self): self.write({'state': 'closed'})
    def action_finish(self): self.write({'state': 'finished'})


class AcademicCourseRegistration(models.Model):
    _name = 'academic.course.registration'
    _description = 'Matrícula de curso'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(compute='_compute_name', store=True)
    student_id = fields.Many2one('academic.student', string='Estudiante', required=True, ondelete='restrict', tracking=True, index=True)
    section_id = fields.Many2one('academic.section', string='Sección', required=True, ondelete='restrict', tracking=True, index=True)
    period_id = fields.Many2one(related='section_id.period_id', store=True, index=True)
    course_id = fields.Many2one(related='section_id.course_id', store=True, index=True)
    state = fields.Selection([('requested','Solicitada'),('enrolled','Matriculado'),('waitlist','Lista de espera'),('withdrawn','Retirado'),('completed','Completado')], default='requested', tracking=True)
    final_grade = fields.Float('Nota final', compute='_compute_final_grade', store=True, digits=(5,2))
    passed = fields.Boolean('Aprobado', compute='_compute_final_grade', store=True)
    grade_ids = fields.One2many('academic.grade', 'registration_id', string='Calificaciones')
    attendance_ids = fields.One2many('academic.attendance', 'registration_id', string='Asistencia')
    company_id = fields.Many2one(related='section_id.company_id', store=True, index=True)
    _sql_constraints = [('registration_uniq', 'unique(student_id, section_id)', 'El estudiante ya está registrado en esta sección.')]

    @api.depends('student_id', 'section_id')
    def _compute_name(self):
        for rec in self: rec.name = '%s · %s' % (rec.student_id.display_name or '', rec.section_id.display_name or '')

    @api.depends('grade_ids.score', 'grade_ids.assessment_id.weight', 'grade_ids.state')
    def _compute_final_grade(self):
        for rec in self:
            grades = rec.grade_ids.filtered(lambda g: g.state == 'published')
            total_weight = sum(grades.mapped('assessment_id.weight'))
            rec.final_grade = sum((g.percentage * g.assessment_id.weight / 100.0) for g in grades) / total_weight * 100.0 if total_weight else 0.0
            rec.passed = rec.final_grade >= 70.0

    def action_enroll(self):
        for rec in self:
            if rec.section_id.capacity and rec.section_id.enrolled_count >= rec.section_id.capacity and rec.state != 'enrolled':
                rec.state = 'waitlist'
            else: rec.state = 'enrolled'
    def action_withdraw(self): self.write({'state':'withdrawn'})


class AcademicAssessment(models.Model):
    _name = 'academic.assessment'
    _description = 'Evaluación'
    _order = 'date, sequence, id'

    name = fields.Char('Evaluación', required=True, translate=True)
    section_id = fields.Many2one('academic.section', string='Sección', required=True, ondelete='cascade', index=True)
    assessment_type = fields.Selection([('exam','Examen'),('quiz','Prueba corta'),('assignment','Tarea'),('project','Proyecto'),('participation','Participación'),('other','Otro')], string='Tipo', default='exam', required=True)
    date = fields.Date('Fecha')
    sequence = fields.Integer('Orden', default=10)
    max_score = fields.Float('Puntaje máximo', default=100.0, required=True)
    weight = fields.Float('Peso %', default=10.0, required=True)
    published = fields.Boolean('Visible al estudiante', default=False)
    grade_ids = fields.One2many('academic.grade', 'assessment_id', string='Notas')
    company_id = fields.Many2one(related='section_id.company_id', store=True, index=True)

    @api.constrains('max_score','weight')
    def _check_values(self):
        for rec in self:
            if rec.max_score <= 0 or rec.weight < 0 or rec.weight > 100: raise ValidationError(_('Revise el puntaje máximo y el peso de la evaluación.'))


class AcademicGrade(models.Model):
    _name = 'academic.grade'
    _description = 'Calificación'
    _inherit = ['mail.thread']
    _order = 'assessment_id, registration_id'

    registration_id = fields.Many2one('academic.course.registration', string='Matrícula', required=True, ondelete='cascade', index=True)
    assessment_id = fields.Many2one('academic.assessment', string='Evaluación', required=True, ondelete='cascade', index=True)
    student_id = fields.Many2one(related='registration_id.student_id', store=True, index=True)
    section_id = fields.Many2one(related='registration_id.section_id', store=True, index=True)
    score = fields.Float('Puntaje', tracking=True)
    percentage = fields.Float('Porcentaje', compute='_compute_percentage', store=True)
    feedback = fields.Html('Retroalimentación')
    state = fields.Selection([('draft','Borrador'),('published','Publicada')], default='draft', tracking=True)
    company_id = fields.Many2one(related='registration_id.company_id', store=True, index=True)
    _sql_constraints = [('grade_uniq','unique(registration_id, assessment_id)','Ya existe una nota para esta evaluación y estudiante.')]

    @api.depends('score','assessment_id.max_score')
    def _compute_percentage(self):
        for rec in self: rec.percentage = (rec.score / rec.assessment_id.max_score * 100.0) if rec.assessment_id.max_score else 0.0

    @api.constrains('score','assessment_id')
    def _check_score(self):
        for rec in self:
            if rec.score < 0 or (rec.assessment_id and rec.score > rec.assessment_id.max_score): raise ValidationError(_('La nota debe estar entre 0 y el puntaje máximo.'))

    def action_publish(self): self.write({'state':'published'})


class AcademicAttendance(models.Model):
    _name = 'academic.attendance'
    _description = 'Asistencia'
    _order = 'date desc'

    registration_id = fields.Many2one('academic.course.registration', string='Matrícula', required=True, ondelete='cascade', index=True)
    student_id = fields.Many2one(related='registration_id.student_id', store=True, index=True)
    section_id = fields.Many2one(related='registration_id.section_id', store=True, index=True)
    date = fields.Date('Fecha', required=True, default=fields.Date.context_today)
    status = fields.Selection([('present','Presente'),('late','Tardía'),('absent','Ausente'),('excused','Justificada')], string='Estado', required=True, default='present')
    note = fields.Char('Observación')
    company_id = fields.Many2one(related='registration_id.company_id', store=True, index=True)
    _sql_constraints = [('attendance_uniq','unique(registration_id,date)','Ya existe asistencia para este estudiante en esta fecha.')]


class AcademicAssignment(models.Model):
    _name = 'academic.assignment'
    _description = 'Tarea académica'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'due_date desc'

    name = fields.Char('Título', required=True, translate=True)
    section_id = fields.Many2one('academic.section', string='Sección', required=True, ondelete='cascade', index=True)
    instructions = fields.Html('Instrucciones', translate=True)
    due_date = fields.Datetime('Fecha límite', required=True)
    max_score = fields.Float('Puntaje máximo', default=100.0)
    published = fields.Boolean('Publicada', default=False)
    submission_ids = fields.One2many('academic.assignment.submission','assignment_id', string='Entregas')
    company_id = fields.Many2one(related='section_id.company_id', store=True, index=True)


class AcademicAssignmentSubmission(models.Model):
    _name = 'academic.assignment.submission'
    _description = 'Entrega de tarea'
    _inherit = ['mail.thread']
    _order = 'submitted_at desc'

    assignment_id = fields.Many2one('academic.assignment', string='Tarea', required=True, ondelete='cascade', index=True)
    registration_id = fields.Many2one('academic.course.registration', string='Matrícula', required=True, ondelete='cascade', index=True)
    student_id = fields.Many2one(related='registration_id.student_id', store=True, index=True)
    submitted_at = fields.Datetime('Entregada el', default=fields.Datetime.now)
    text = fields.Html('Respuesta')
    attachment_ids = fields.Many2many('ir.attachment', string='Archivos')
    score = fields.Float('Puntaje', tracking=True)
    feedback = fields.Html('Retroalimentación')
    state = fields.Selection([('submitted','Entregada'),('graded','Calificada'),('returned','Devuelta')], default='submitted', tracking=True)
    company_id = fields.Many2one(related='assignment_id.company_id', store=True, index=True)
    _sql_constraints = [('submission_uniq','unique(assignment_id,registration_id)','Ya existe una entrega para esta tarea.')]


class AcademicAnnouncement(models.Model):
    _name = 'academic.announcement'
    _description = 'Anuncio académico'
    _inherit = ['mail.thread']
    _order = 'publish_date desc, id desc'

    name = fields.Char('Título', required=True, translate=True)
    section_id = fields.Many2one('academic.section', string='Sección', ondelete='cascade', index=True)
    body = fields.Html('Contenido', required=True, translate=True)
    publish_date = fields.Datetime('Publicación', default=fields.Datetime.now)
    active = fields.Boolean('Activo', default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)


class AcademicIntegrationConnector(models.Model):
    _name = 'academic.integration.connector'
    _description = 'Conector educativo externo'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Nombre', required=True)
    provider = fields.Selection([('moodle','Moodle'),('canvas','Canvas LMS'),('microsoft_teams','Microsoft Teams / Education'),('google_classroom','Google Classroom'),('blackboard','Blackboard'),('custom','API personalizada')], string='Proveedor', required=True)
    base_url = fields.Char('URL base')
    client_id = fields.Char('Client ID')
    secret = fields.Char('Secreto / token', groups='academic_admission_enrollment.group_academic_manager')
    active = fields.Boolean('Activo', default=True)
    sync_students = fields.Boolean('Sincronizar estudiantes', default=True)
    sync_courses = fields.Boolean('Sincronizar cursos', default=True)
    sync_grades = fields.Boolean('Sincronizar calificaciones', default=True)
    sync_assignments = fields.Boolean('Sincronizar tareas', default=True)
    last_sync = fields.Datetime('Última sincronización', readonly=True)
    state = fields.Selection([('draft','Sin configurar'),('ready','Listo'),('error','Error')], default='draft', tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    def action_mark_ready(self):
        for rec in self:
            if not rec.base_url: raise UserError(_('Configure la URL base del servicio.'))
            rec.state = 'ready'
    def action_sync(self):
        self.write({'last_sync': fields.Datetime.now()})
        for rec in self: rec.message_post(body=_('Sincronización solicitada. El conector queda preparado para implementar la API/OAuth específica de %s.') % dict(rec._fields['provider'].selection).get(rec.provider))
