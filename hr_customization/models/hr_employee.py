from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Employee(models.Model):
    _inherit = 'hr.employee'

    payslip_ids = fields.One2many(
        'hr.payslip',
        'employee_id',
        string="Payslips",
    )

    bank_amount = fields.Float(
        string="Bank Amount",
        store=True,
        inverse="_inverse_bank_amount",
    )


    def _inverse_bank_amount(self):
        """When user edits bank_amount in employee, update latest payslip but
        ensure it doesn’t exceed payslip’s total net."""
        for employee in self:
            payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('state', 'in', ['draft', 'verify'])
            ])
            for slip in payslips:
                # Compute net amount
                gross_amount = sum(slip.line_ids.filtered(lambda l: l.code == 'GROSS').mapped('amount'))
                ded_amount = sum(slip.line_ids.filtered(lambda l: l.category_id.code == 'DED').mapped('amount'))
                net_amount = sum(slip.line_ids.filtered(lambda l: l.code == 'NET').mapped('amount')) or (gross_amount - ded_amount)

                # If bank amount exceeds net, cap it
                if employee.bank_amount > net_amount:
                    slip.bank_amount = net_amount
                else:
                    slip.bank_amount = employee.bank_amount