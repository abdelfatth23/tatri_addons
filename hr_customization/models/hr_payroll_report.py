
from odoo import fields, models, _ ,api


class InheritHrPayrollReport(models.Model):
    _inherit = "hr.payroll.report"

    # bonus_work = fields.Float('عمل اضافي', readonly=True)
    # incentives = fields.Float('حوافز', readonly=True)
    # assignment_allowance = fields.Float('بدل انتداب', readonly=True)

    # debit = fields.Float('سلف و قروض', readonly=True)
    # delays = fields.Float('غياب وتاخيرات', readonly=True)
    # early_dismissal = fields.Float('تأخر و انصراف مبكر', readonly=True)
    # penalties = fields.Float('جزاءات', readonly=True)


    # def _select(self, additional_rules):
    #     return super()._select(additional_rules) + """,
    #             p.bonus_work as bonus_work,
    #             p.incentives as incentives,
    #             p.assignment_allowance as assignment_allowance,

    #             p.debit as debit,
    #             p.delays as delays,
    #             p.early_dismissal as early_dismissal,
    #             p.penalties as penalties"""

    # def _group_by(self, additional_rules):
    #     return super()._group_by(additional_rules) + """,
    #             p.bonus_work,
    #             p.incentives,
    #             p.assignment_allowance,

    #             p.debit,
    #             p.delays,
    #             p.early_dismissal,
    #             p.penalties"""
