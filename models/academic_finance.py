from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AcademicFeeRule(models.Model):
    _name = 'academic.fee.rule'
    _description = 'Regla de arancel académico'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char('Arancel', required=True, tracking=True)
    code = fields.Char('Código', required=True, index=True)
    sequence = fields.Integer(default=10)
    charge_type = fields.Selection([('admission','Admisión'),('enrollment','Matrícula'),('credit','Por crédito'),('course','Por materia'),('lab','Laboratorio'),('graduation','Graduación'),('service','Servicio'),('penalty','Recargo'),('other','Otro')], required=True, default='enrollment')
    program_id = fields.Many2one('academic.program', string='Programa')
    amount = fields.Monetary('Monto', required=True)
    currency_id = fields.Many2one('res.currency', required=True, default=lambda s: s.env.company.currency_id)
    product_id = fields.Many2one('product.product', string='Producto contable', required=True, domain="[('sale_ok','=',True)]")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company, index=True)
    _sql_constraints = [('fee_code_company_uniq','unique(code, company_id)','El código de arancel debe ser único por compañía.')]


class AcademicScholarship(models.Model):
    _name = 'academic.scholarship'
    _description = 'Beca / beneficio'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Beca / beneficio', required=True)
    code = fields.Char('Código', required=True)
    discount_type = fields.Selection([('percent','Porcentaje'),('fixed','Monto fijo')], default='percent', required=True)
    value = fields.Float('Valor', required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)


class AcademicStudentScholarship(models.Model):
    _name = 'academic.student.scholarship'
    _description = 'Beca del estudiante'
    _inherit = ['mail.thread']

    student_id = fields.Many2one('academic.student', required=True, ondelete='cascade', tracking=True)
    scholarship_id = fields.Many2one('academic.scholarship', required=True, ondelete='restrict', tracking=True)
    period_id = fields.Many2one('academic.period', string='Periodo')
    state = fields.Selection([('draft','Borrador'),('approved','Aprobada'),('suspended','Suspendida'),('expired','Vencida')], default='draft', tracking=True)
    notes = fields.Text()
    company_id = fields.Many2one(related='student_id.company_id', store=True)


class AcademicCharge(models.Model):
    _name = 'academic.charge'
    _description = 'Cargo académico'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'due_date desc, id desc'

    name = fields.Char(default=lambda s: _('Nuevo'), readonly=True, copy=False, index=True)
    student_id = fields.Many2one('academic.student', required=True, ondelete='restrict', tracking=True, index=True)
    period_id = fields.Many2one('academic.period', string='Periodo', tracking=True)
    fee_rule_id = fields.Many2one('academic.fee.rule', string='Arancel', required=True, ondelete='restrict')
    description = fields.Char('Descripción', required=True)
    charge_date = fields.Date('Fecha', default=fields.Date.context_today, required=True)
    due_date = fields.Date('Vencimiento', required=True, tracking=True)
    amount = fields.Monetary('Monto', required=True, tracking=True)
    discount_amount = fields.Monetary('Becas / descuentos', default=0, tracking=True)
    net_amount = fields.Monetary('Neto', compute='_compute_amounts', store=True)
    paid_amount = fields.Monetary('Pagado', compute='_compute_amounts', store=True)
    balance = fields.Monetary('Saldo', compute='_compute_amounts', store=True)
    currency_id = fields.Many2one('res.currency', required=True, default=lambda s: s.env.company.currency_id)
    invoice_id = fields.Many2one('account.move', string='Factura', readonly=True, copy=False)
    state = fields.Selection([('draft','Borrador'),('posted','Pendiente'),('partial','Pago parcial'),('paid','Pagado'),('cancelled','Anulado')], default='draft', tracking=True)
    company_id = fields.Many2one(related='student_id.company_id', store=True, index=True)

    @api.depends('amount','discount_amount','invoice_id.amount_residual','invoice_id.amount_total','invoice_id.payment_state')
    def _compute_amounts(self):
        for rec in self:
            rec.net_amount = max(rec.amount - rec.discount_amount, 0)
            if rec.invoice_id and rec.invoice_id.state == 'posted':
                rec.paid_amount = max(rec.invoice_id.amount_total - rec.invoice_id.amount_residual, 0)
                rec.balance = rec.invoice_id.amount_residual
                rec.state = 'paid' if rec.invoice_id.payment_state in ('paid','in_payment') and not rec.invoice_id.amount_residual else ('partial' if rec.paid_amount else 'posted')
            else:
                rec.paid_amount = 0
                rec.balance = rec.net_amount

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('academic.charge') or _('Nuevo')
        return super().create(vals_list)

    def action_post(self):
        for rec in self:
            if rec.invoice_id:
                continue
            partner = rec.student_id.partner_id
            invoice = self.env['account.move'].create({
                'move_type':'out_invoice','partner_id':partner.id,'invoice_date':rec.charge_date,
                'invoice_date_due':rec.due_date,'company_id':rec.company_id.id,
                'invoice_line_ids':[(0,0,{'product_id':rec.fee_rule_id.product_id.id,'name':rec.description,'quantity':1,'price_unit':rec.net_amount})]
            })
            invoice.action_post()
            rec.write({'invoice_id':invoice.id,'state':'posted'})
        return True

    def action_cancel(self):
        for rec in self:
            if rec.invoice_id and rec.invoice_id.state == 'posted' and rec.invoice_id.payment_state != 'not_paid':
                raise UserError(_('No puede anular un cargo con pagos aplicados.'))
            rec.state = 'cancelled'


class AcademicPaymentPlan(models.Model):
    _name = 'academic.payment.plan'
    _description = 'Plan de pago estudiantil'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Plan', required=True)
    student_id = fields.Many2one('academic.student', required=True, ondelete='restrict', tracking=True)
    period_id = fields.Many2one('academic.period', string='Periodo')
    line_ids = fields.One2many('academic.payment.plan.line','plan_id', string='Cuotas')
    total_amount = fields.Monetary(compute='_compute_total', store=True)
    currency_id = fields.Many2one('res.currency', required=True, default=lambda s:s.env.company.currency_id)
    state = fields.Selection([('draft','Borrador'),('active','Activo'),('completed','Completado'),('cancelled','Cancelado')], default='draft', tracking=True)
    company_id = fields.Many2one(related='student_id.company_id', store=True)

    @api.depends('line_ids.amount')
    def _compute_total(self):
        for rec in self: rec.total_amount = sum(rec.line_ids.mapped('amount'))


class AcademicPaymentPlanLine(models.Model):
    _name = 'academic.payment.plan.line'
    _description = 'Cuota del plan de pago'
    _order = 'due_date, id'

    plan_id = fields.Many2one('academic.payment.plan', required=True, ondelete='cascade')
    due_date = fields.Date('Vencimiento', required=True)
    amount = fields.Monetary('Monto', required=True)
    currency_id = fields.Many2one(related='plan_id.currency_id')
    charge_id = fields.Many2one('academic.charge', string='Cargo asociado')
    state = fields.Selection([('pending','Pendiente'),('paid','Pagada'),('overdue','Vencida')], default='pending')


class AcademicStudentFinance(models.Model):
    _inherit = 'academic.student'

    charge_ids = fields.One2many('academic.charge','student_id', string='Estado de cuenta')
    scholarship_ids = fields.One2many('academic.student.scholarship','student_id', string='Becas')
    outstanding_balance = fields.Monetary('Saldo pendiente', compute='_compute_finance', currency_field='company_currency_id')
    overdue_balance = fields.Monetary('Saldo vencido', compute='_compute_finance', currency_field='company_currency_id')
    company_currency_id = fields.Many2one(related='company_id.currency_id')

    def _compute_finance(self):
        today = fields.Date.today()
        for rec in self:
            charges = rec.charge_ids.filtered(lambda c: c.state not in ('draft','cancelled','paid'))
            rec.outstanding_balance = sum(charges.mapped('balance'))
            rec.overdue_balance = sum(charges.filtered(lambda c: c.due_date and c.due_date < today).mapped('balance'))
