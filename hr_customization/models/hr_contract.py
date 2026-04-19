# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.addons import decimal_precision as dp


class HrContract(models.Model):
    _inherit = 'hr.contract'
    _description = 'Employee Contract'

    labor_day_allowance = fields.Float(string="منحة عيد العمال")
    cost_of_living_allowance = fields.Float(string="بدل غلاء معيشة", compute="get_fields_amount", store=True, readonly=False)
    nature_of_work_allowance = fields.Float(string="بدل طبيعة عمل", compute="get_fields_amount", store=True, readonly=False)
    production_incentive_allowance = fields.Float(string="حافز الأنتاج", compute="get_fields_amount", store=True, readonly=False)
    regular_incentive_allowance = fields.Float(string="حافز أنتظام", compute="get_fields_amount", store=True, readonly=False)
    transportation_allowance_in_kind = fields.Float(string='بدل انتقال عيني', compute="get_fields_amount", store=True, readonly=False)
    #depends rm_eg_hr_payroll
    basic_salary = fields.Float(string="Basic Salary",
                                digits=dp.get_precision('Payroll'), compute="get_fields_amount", store=True, readonly=True)
    daily_wage = fields.Float('أجر اليوم', compute="get_fields_amount", store=True, readonly=True)
    hourly_wage = fields.Float('أجر الساعه', compute="get_fields_amount", store=True, readonly=True)

    @api.depends('wage','employee_id')
    def get_fields_amount(self):
        for rec in self:
            rec.cost_of_living_allowance = 0
            rec.production_incentive_allowance = 0
            rec.nature_of_work_allowance = 0
            rec.basic_salary = 0
            rec.daily_wage = 0
            rec.hourly_wage = 0
            rec.regular_incentive_allowance = 0

            rec.basic_salary = rec.wage * .70
            rec.cost_of_living_allowance = (rec.wage-rec.basic_salary) * .20
            rec.nature_of_work_allowance = (rec.wage-rec.basic_salary) * .20
            rec.production_incentive_allowance = (rec.wage-rec.basic_salary) * .60

            rec.daily_wage = rec.wage / 30
            rec.hourly_wage = rec.daily_wage / 8
            if rec.wage >= 20000:
                rec.regular_incentive_allowance = 1000
            elif rec.wage >= 10000:
                rec.regular_incentive_allowance = 700
            elif rec.wage >= 5000:
                rec.regular_incentive_allowance = 500
            elif rec.wage >= 3500:
                rec.regular_incentive_allowance = 300
