from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError


class AcademicProfessorPortal(http.Controller):
    def _professor(self):
        professor = request.env['academic.professor'].sudo().search([('user_id', '=', request.env.user.id), ('active', '=', True)], limit=1)
        if not professor:
            raise AccessError(_('Su usuario no está vinculado a un perfil docente activo.'))
        return professor

    def _section(self, section_id):
        professor = self._professor()
        section = request.env['academic.section'].sudo().browse(section_id).exists()
        if not section or professor not in section.professor_ids:
            raise AccessError(_('No tiene acceso a esta sección.'))
        return professor, section

    @http.route('/my/professor', type='http', auth='user', website=True)
    def dashboard(self, **kw):
        p = self._professor()
        sections = request.env['academic.section'].sudo().search([('professor_ids', 'in', p.id), ('state', '!=', 'cancelled')], order='period_id desc, course_id')
        submissions = request.env['academic.assignment.submission'].sudo().search([('assignment_id.section_id', 'in', sections.ids), ('state', '=', 'submitted')], limit=10)
        return request.render('academic_admission_enrollment.portal_professor_dashboard', {'professor': p, 'sections': sections, 'pending_submissions': submissions})

    @http.route('/my/professor/section/<int:section_id>', type='http', auth='user', website=True)
    def section(self, section_id, **kw):
        p, s = self._section(section_id)
        regs = s.registration_ids.filtered(lambda r: r.state in ('enrolled','completed')).sorted(lambda r: r.student_id.display_name or '')
        return request.render('academic_admission_enrollment.portal_professor_section', {'professor':p,'section':s,'registrations':regs})

    @http.route('/my/professor/section/<int:section_id>/gradebook', type='http', auth='user', website=True, methods=['GET','POST'], csrf=True)
    def gradebook(self, section_id, **post):
        p, s = self._section(section_id)
        regs = s.registration_ids.filtered(lambda r: r.state in ('enrolled','completed')).sorted(lambda r: r.student_id.display_name or '')
        if request.httprequest.method == 'POST':
            if s.gradebook_state == 'closed':
                raise UserError(_('El acta ya está cerrada.'))
            for assessment in s.assessment_ids:
                for reg in regs:
                    key = 'score_%s_%s' % (assessment.id, reg.id)
                    if key not in post or post[key] == '':
                        continue
                    try: score = float(post[key])
                    except (TypeError, ValueError): continue
                    grade = request.env['academic.grade'].sudo().search([('assessment_id','=',assessment.id),('registration_id','=',reg.id)], limit=1)
                    vals = {'score': score}
                    if grade: grade.write(vals)
                    else: request.env['academic.grade'].sudo().create(dict(vals, assessment_id=assessment.id, registration_id=reg.id))
            return request.redirect('/my/professor/section/%s/gradebook?saved=1' % s.id)
        grades = request.env['academic.grade'].sudo().search([('section_id','=',s.id)])
        grade_map = {(g.assessment_id.id,g.registration_id.id):g for g in grades}
        return request.render('academic_admission_enrollment.portal_professor_gradebook', {'professor':p,'section':s,'registrations':regs,'assessments':s.assessment_ids.sorted(lambda a:(a.sequence,a.id)),'grade_map':grade_map,'saved':kw.get('saved')})

    @http.route('/my/professor/section/<int:section_id>/assessment/new', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def assessment_new(self, section_id, **post):
        p, s = self._section(section_id)
        request.env['academic.assessment'].sudo().create({'name':post.get('name') or _('Evaluación'),'section_id':s.id,'assessment_type':post.get('assessment_type') or 'exam','max_score':float(post.get('max_score') or 100),'weight':float(post.get('weight') or 0),'date':post.get('date') or False})
        return request.redirect('/my/professor/section/%s/gradebook' % s.id)

    @http.route('/my/professor/section/<int:section_id>/grades/publish', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def grades_publish(self, section_id, **post):
        p, s = self._section(section_id)
        s.assessment_ids.mapped('grade_ids').action_publish()
        return request.redirect('/my/professor/section/%s/gradebook' % s.id)

    @http.route('/my/professor/section/<int:section_id>/gradebook/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def gradebook_submit(self, section_id, **post):
        p, s = self._section(section_id); s.action_submit_gradebook()
        return request.redirect('/my/professor/section/%s/gradebook' % s.id)

    @http.route('/my/professor/section/<int:section_id>/attendance', type='http', auth='user', website=True, methods=['GET','POST'], csrf=True)
    def attendance(self, section_id, **post):
        p, s = self._section(section_id)
        regs = s.registration_ids.filtered(lambda r:r.state in ('enrolled','completed')).sorted(lambda r:r.student_id.display_name or '')
        date = post.get('date') or request.params.get('date') or fields.Date.today().isoformat()
        if request.httprequest.method == 'POST':
            for reg in regs:
                status = post.get('status_%s' % reg.id, 'present')
                att = request.env['academic.attendance'].sudo().search([('registration_id','=',reg.id),('date','=',date)],limit=1)
                vals={'status':status,'note':post.get('note_%s'%reg.id) or False}
                if att: att.write(vals)
                else: request.env['academic.attendance'].sudo().create(dict(vals,registration_id=reg.id,date=date))
            return request.redirect('/my/professor/section/%s/attendance?date=%s&saved=1' % (s.id,date))
        atts=request.env['academic.attendance'].sudo().search([('section_id','=',s.id),('date','=',date)])
        return request.render('academic_admission_enrollment.portal_professor_attendance', {'professor':p,'section':s,'registrations':regs,'date':date,'attendance_map':{a.registration_id.id:a for a in atts},'saved':kw.get('saved')})

    @http.route('/my/professor/section/<int:section_id>/assignments', type='http', auth='user', website=True, methods=['GET','POST'], csrf=True)
    def assignments(self, section_id, **post):
        p,s=self._section(section_id)
        if request.httprequest.method=='POST' and post.get('name'):
            request.env['academic.assignment'].sudo().create({'name':post['name'],'section_id':s.id,'due_date':post.get('due_date'),'max_score':float(post.get('max_score') or 100),'instructions':post.get('instructions'),'published':bool(post.get('published'))})
            return request.redirect('/my/professor/section/%s/assignments' % s.id)
        return request.render('academic_admission_enrollment.portal_professor_assignments', {'professor':p,'section':s,'assignments':s.assignment_ids})

    @http.route('/my/professor/submission/<int:submission_id>/grade', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def grade_submission(self, submission_id, **post):
        p=self._professor(); sub=request.env['academic.assignment.submission'].sudo().browse(submission_id).exists()
        if not sub or p not in sub.assignment_id.section_id.professor_ids: raise AccessError(_('Sin acceso.'))
        sub.write({'score':float(post.get('score') or 0),'feedback':post.get('feedback') or False,'state':'graded'})
        return request.redirect('/my/professor/section/%s/assignments' % sub.assignment_id.section_id.id)
