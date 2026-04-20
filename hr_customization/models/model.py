from odoo import models, fields, api, _
from odoo.osv import expression
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import pytz
import logging

_logger = logging.getLogger(__name__)

class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    registration_number = fields.Char('Registration Number of the Employee', readonly=True)

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    has_custody = fields.Boolean('عُهد')
    custody_note = fields.Text('تفاصيل العهد')

    registration_number = fields.Char('Registration Number of the Employee', groups=False, copy=False, required=False)

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        """
        name search that supports searching by tag code
        """
        args = args or []
        domain = []
        if name:
            domain = ['|', ('registration_number', '=', name), ('name', operator, name)]
            if operator in expression.NEGATIVE_TERM_OPERATORS:
                domain = ['&'] + domain
        state = self.search(domain + args, limit=limit)
        return state.name_get()

    def name_get(self):
        employee_list = []
        for this in self:
            if this.registration_number:
                name = '%s [%s]' % (this.name or '', this.registration_number or '')
            else:
                name =  this.name or ''
            employee_list.append((this.id, name))
        return employee_list
    
    # @api.model_create_multi
    # def create(self, vals_list):
    #     for vals in vals_list:
    #         if vals.get('registration_number', _('New')) == _('New'):
    #             num = self.env['ir.sequence'].next_by_code('emp.registeration') or '/'
    #             vals['registration_number'] = num
    #             vals['pin'] = num
    #             vals['ro_device_id'] = num
    #     return super(HrEmployee, self).create(vals_list)

    @api.constrains('ro_device_id', 'registration_number')
    def _check_unique_fields(self):
        for rec in self:
            domain = []

            if rec.ro_device_id:
                domain += [('ro_device_id', '=', rec.ro_device_id)]
            
            if rec.registration_number:
                if domain:
                    domain.insert(0, '|')

                domain += [('registration_number', '=', rec.registration_number)]

            if domain and self.search_count(domain) > 1:
                raise ValidationError(_("Registration Number and Device ID must be unique!"))


class Payslip(models.Model):
    _inherit = 'hr.payslip'

    bank_amount = fields.Float(
        string="Bank Amount",
        compute="_compute_amounts_net",
        store=True,
    )
    # make cash_amount a plain stored field (so we can write to it safely)
    cash_amount = fields.Float(
        string="Cash Amount",
        store=True,
    )

    # flag to mark manual edit so compute doesn't overwrite user changes
    bank_amount_manual = fields.Boolean(
        string="Bank edited manually",
        default=False,
        copy=False,
        help="When True the automatic compute won't override bank/cash amounts."
    )

    def compute_sheet(self):
        self.bank_amount_manual = False
        return super().compute_sheet()

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        _logger.info(f"Updated with default_get bank amount")
        employee_id = defaults.get("employee_id")
        if employee_id:
            employee = self.env['hr.employee'].browse(employee_id)

            # get employee preferred bank amount
            emp_bank = getattr(employee, "bank_amount", 0.0)  # change name if needed

            # only set if exists and positive
            if "bank_amount" in fields_list and emp_bank > 0:
                defaults["bank_amount"] = emp_bank
                defaults["bank_amount_manual"] = False

        return defaults

    @api.onchange('employee_id')
    def _onchange_employee_id_default_bank(self):
        _logger.info(f"Updated with _onchange_employee_id_default_bank bank amount")
        if self.employee_id and not self.bank_amount_manual:
            self.bank_amount = self.employee_id.bank_amount or 0.0
            self.bank_amount_manual = False

    @api.depends('line_ids.amount',
                 'line_ids.total',
                 'line_ids.code',
                 'bank_amount_manual')
    def _compute_amounts_net(self):
        """Compute defaults for bank_amount and cash_amount.
        If bank_amount_manual is True, we DO NOT override values (user edited).
        """
        _logger.info(f"Running compute...")
        for rec in self:
            _logger.info(f"Updated with _compute_amounts_net bank amount = {rec.cash_amount}")

            if rec.bank_amount_manual:
                _logger.info("Skipping compute because bank_amount_manual = True")
                continue

            if not rec.line_ids:
                _logger.info("Skipping: no salary lines yet.")
                continue

            gross_amount = sum(rec.line_ids.filtered(lambda x: x.code == 'GROSS').mapped('amount'))
            ded_amount = sum(rec.line_ids.filtered(lambda x: x.category_id.code == 'DED').mapped('amount'))
            net_amount = sum(rec.line_ids.filtered(lambda x: x.code == 'NET').mapped('amount'))

            if gross_amount == 0 and ded_amount == 0 and net_amount == 0:
                _logger.info("Skipping compute because payslip has no line_ids yet.")
                continue

            if not net_amount:
                net_amount = gross_amount - ded_amount

            # --------------------------------------------
            # Employee default bank amount
            # --------------------------------------------
            emp_bank = getattr(rec.employee_id, "bank_amount", 0.0)

            # If employee has specific bank amount, use it
            if emp_bank > 0:
                _logger.info(f"Updated with employee bank amount = {rec.bank_amount}")
                rec.bank_amount = min(emp_bank, net_amount)
                rec.cash_amount = net_amount - rec.bank_amount
                rec.bank_amount_manual = False
                continue

            # --------------------------------------------
            # old logic
            # --------------------------------------------
            _logger.info(f"Updated with old logic bank amount = {rec.bank_amount}")
            has_bank = bool(
                (hasattr(rec.employee_id, 'x_studio_bank_account') and rec.employee_id.x_studio_bank_account)
                or rec.employee_id.bank_account_id
            )

            if has_bank:
                if gross_amount <= 12600:
                    rec.bank_amount = gross_amount - ded_amount
                    rec.cash_amount = 0.0
                else:
                    rec.bank_amount = 12600 - ded_amount
                    rec.cash_amount = gross_amount - 12600
            else:
                rec.bank_amount = 0.0
                rec.cash_amount = net_amount

    @api.onchange('bank_amount')
    def _onchange_bank_amount(self):
        for rec in self:
            if rec.bank_amount_manual:
                return
            gross_amount = sum(rec.line_ids.filtered(lambda x: x.code == 'GROSS').mapped('amount'))
            ded_amount = sum(rec.line_ids.filtered(lambda x: x.category_id.code == 'DED').mapped('amount'))
            net_amount = sum(rec.line_ids.filtered(lambda x: x.code == 'NET').mapped('amount'))
            if not net_amount:
                net_amount = gross_amount - ded_amount

            rec.cash_amount = max(0.0, net_amount - (rec.bank_amount or 0.0))
            rec.bank_amount_manual = True

    @api.onchange('cash_amount')
    def _onchange_cash_amount(self):
        _logger.info(f"Updated with _onchange_cash_amount bank amount")
        for rec in self:
            if rec.bank_amount_manual:
                return
            gross_amount = sum(rec.line_ids.filtered(lambda x: x.code == 'GROSS').mapped('amount'))
            ded_amount = sum(rec.line_ids.filtered(lambda x: x.category_id.code == 'DED').mapped('amount'))
            net_amount = sum(rec.line_ids.filtered(lambda x: x.code == 'NET').mapped('amount'))
            if not net_amount:
                net_amount = gross_amount - ded_amount

            rec.bank_amount = max(0.0, net_amount - (rec.cash_amount or 0.0))
            rec.bank_amount_manual = True

    # @api.depends('line_ids')
    # def get_amounts_net(self):
    #     _logger.info(f"Updated with get_amounts_net bank amount")
    #     for rec in self:
    #         _logger.info(f"Updated with get_amounts_net bank amount = {rec.cash_amount}")
    #         rec.bank_amount = 0
    #         rec.cash_amount = 0
    #
    #         if (hasattr(rec.employee_id,
    #                     'x_studio_bank_account') and rec.employee_id.x_studio_bank_account) or rec.employee_id.bank_account_id:
    #
    #             gross_amount = sum(rec.line_ids.filtered(lambda x: x.code == 'GROSS').mapped('amount'))
    #             ded_amount = sum(rec.line_ids.filtered(lambda x: x.category_id.code == 'DED').mapped('amount'))
    #             # net_amount = sum(rec.line_ids.filtered(lambda x:x.code =='NET').mapped('amount'))
    #             rec.bank_amount = gross_amount - ded_amount if gross_amount <= 12600 else (12600 - ded_amount)
    #             rec.cash_amount = gross_amount - 12600 if gross_amount > 12600 else 0
    #
    #         elif rec.employee_id.bank_account_id:
    #             gross_amount = sum(rec.line_ids.filtered(lambda x: x.code == 'GROSS').mapped('amount'))
    #             ded_amount = sum(rec.line_ids.filtered(lambda x: x.category_id.code == 'DED').mapped('amount'))
    #             # net_amount = sum(rec.line_ids.filtered(lambda x:x.code =='NET').mapped('amount'))
    #             rec.bank_amount = gross_amount - ded_amount if gross_amount <= 12600 else (12600 - ded_amount)
    #             rec.cash_amount = gross_amount - 12600 if gross_amount > 12600 else 0
    #
    #         else:
    #             net_amount = sum(rec.line_ids.filtered(lambda x: x.code == 'NET').mapped('amount'))
    #             rec.cash_amount = net_amount

    # @api.depends('line_ids')
    # def get_amounts_net(self):
    #     for rec in self:
    #         _logger.info(f"Updated with get_amounts_net bank amount = {rec.cash_amount}")
    #         rec.bank_amount = 0
    #         rec.cash_amount = 0
    #
    #         if (hasattr(rec.employee_id,
    #                     'x_studio_bank_account') and rec.employee_id.x_studio_bank_account) or rec.employee_id.bank_account_id:
    #
    #             gross_amount = sum(rec.line_ids.filtered(lambda x:x.code =='GROSS').mapped('amount'))
    #             ded_amount = sum(rec.line_ids.filtered(lambda x:x.category_id.code =='DED').mapped('amount'))
    #             # net_amount = sum(rec.line_ids.filtered(lambda x:x.code =='NET').mapped('amount'))
    #             rec.bank_amount = gross_amount-ded_amount if gross_amount<=12600 else (12600-ded_amount)
    #             rec.cash_amount = gross_amount - 12600 if gross_amount > 12600 else 0
    #
    #         elif rec.employee_id.bank_account_id:
    #             gross_amount = sum(rec.line_ids.filtered(lambda x:x.code =='GROSS').mapped('amount'))
    #             ded_amount = sum(rec.line_ids.filtered(lambda x:x.category_id.code =='DED').mapped('amount'))
    #             # net_amount = sum(rec.line_ids.filtered(lambda x:x.code =='NET').mapped('amount'))
    #             rec.bank_amount = gross_amount-ded_amount if gross_amount<=12600 else (12600-ded_amount)
    #             rec.cash_amount = gross_amount - 12600 if gross_amount > 12600 else 0
    #
    #         else:
    #             net_amount = sum(rec.line_ids.filtered(lambda x:x.code =='NET').mapped('amount'))
    #             rec.cash_amount = net_amount


    # bonus_work = fields.Float('Bonus Work')
    # incentives = fields.Float('incentives')
    # assignment_allowance = fields.Float('assignment allowance')

    # debit = fields.Float('debit')
    # delays = fields.Float('delays')
    # early_dismissal = fields.Float('Early Dismissal')
    # penalties = fields.Float('penalties')

    # Allowances
    labor_day_allowance = fields.Float(string="منحة عيد العمال", related='contract_id.labor_day_allowance')
    cost_of_living_allowance = fields.Float(string="بدل غلاء معيشة", related='contract_id.cost_of_living_allowance')
    production_incentive_allowance = fields.Float(string="حافز الأنتاج", related='contract_id.production_incentive_allowance')
    nature_of_work_allowance = fields.Float(string="بدل طبيعة عمل", related='contract_id.nature_of_work_allowance')
    transportation_allowance_in_kind = fields.Float(string='بدل انتقال عيني',related='contract_id.transportation_allowance_in_kind')
    food_allowance = fields.Float('بدل تغذية')
    exceptional_reward_allowance = fields.Float('مكافأة إسثنائية')
    previous_months_allowance = fields.Float('تسوية شهور سابقة')
    reward_regularity_allowance = fields.Float('مكافأة الانتظام')
    no_days_holidays = fields.Float('عدد ايام عمل  عطلات')
    no_hours_holidays = fields.Float('عدد ساعات إضافي عطلات')
    holidays_allowance = fields.Float('قيمة عمل عطلات', compute="get_fields_amount")
    morning_hours = fields.Float('ساعات النهارى')
    morning_hours_allowance = fields.Float('اضافى ساعات نهارى', compute="get_fields_amount")
    
    night_hours = fields.Float('ساعات الليلى')
    night_hours_allowance = fields.Float('اضافى ساعات ليلى', compute="get_fields_amount")

    #Deductions
    # days_deduction = fields.Float('ايام مخصومة')
    monthly_loans_deduction = fields.Float('سلفيات شهرية')
    loan_installment_deduction = fields.Float('قسط السلفة')
    # exit_permits_deduction = fields.Float('تصاريح خروج')
    delay_permits_hours = fields.Float('تصاريح تأخير')
    delay_permits_deduction = fields.Float('قيمة تصاريح تأخير', compute="get_fields_amount")

    prod_incentive_deduction = fields.Float('خصم حافز انتاج')
    custody_deduction = fields.Float('خصم عُهده')
    # insurance_deduction = fields.Float('حصة التأمينات')
    # hfm_deduction = fields.Float('مساهمة تكريم اسر الشهداء')
    # employment_tax_deduction = fields.Float('ضريبة كسب العمل')

    @api.depends('contract_id','no_days_holidays','morning_hours','night_hours')
    def get_fields_amount(self):
        for rec in self:
            rec.holidays_allowance = 0
            rec.morning_hours_allowance = 0
            rec.night_hours_allowance = 0
            rec.delay_permits_deduction = 0
            
            rec.holidays_allowance = rec.contract_id.daily_wage * 2 * rec.no_days_holidays
            rec.morning_hours_allowance = rec.contract_id.hourly_wage * 1.35 * rec.morning_hours
            rec.night_hours_allowance = rec.contract_id.hourly_wage * 1.7 * rec.night_hours

            rec.delay_permits_deduction = rec.contract_id.hourly_wage * rec.delay_permits_hours

    def _ro_get_contract_bonus_allowance(self):
        self.ensure_one()

        if not self.worked_days_line_ids:
            return self.bonus_work or 0

        return self.bonus_work or 0
    
    def _ro_get_contract_incentives(self):
        self.ensure_one()

        if not self.worked_days_line_ids:
            return self.incentives or 0

        return self.incentives or 0
    
    def _ro_get_contract_assignment_allowance(self):
        self.ensure_one()

        if not self.worked_days_line_ids:
            return self.assignment_allowance or 0

        return self.assignment_allowance or 0
    
    def _ro_get_deduction_loan_deduction(self):
        self.ensure_one()

        if not self.worked_days_line_ids:
            return self.debit or 0

        return self.debit or 0
    
    def _ro_get_contract_delays(self):
        self.ensure_one()

        if not self.worked_days_line_ids:
            return self.delays or 0

        return self.delays or 0
    
    def _ro_get_contract_early_dismissal(self):
        self.ensure_one()

        if not self.worked_days_line_ids:
            return self.early_dismissal or 0

        return self.early_dismissal or 0
    
    def _ro_get_contract_penalties(self):
        self.ensure_one()

        if not self.worked_days_line_ids:
            return self.penalties or 0

        return self.penalties or 0
    

    def _get_emp_leave_intervals(self, emp, start_datetime=None,
                                 end_datetime=None):
        leaves = []
        leave_obj = self.env['hr.leave']
        leave_ids = leave_obj.search([
            ('employee_id', '=', emp.id),
            ('state', '=', 'validate')])

        for leave in leave_ids:
            date_from = leave.date_from
            if end_datetime and date_from > end_datetime:
                continue
            date_to = leave.date_to
            if start_datetime and date_to < start_datetime:
                continue
            leaves.append((leave.number_of_days, date_from, date_to))
        return leaves

    @api.depends('employee_id', 'contract_id', 'struct_id', 'date_from', 'date_to')
    def _compute_worked_days_line_ids(self):
        res = super(Payslip, self)._compute_worked_days_line_ids()

        if not self or self.env.context.get('salary_simulation'):
            return res
        valid_slips = self.filtered(lambda p: p.employee_id and p.date_from and p.date_to and p.contract_id and p.struct_id)
        if not valid_slips:
            return res
        
        for slip in valid_slips:
            worked_days = []
            if all(slip.contract_id.resource_calendar_id.attendance_ids.mapped('date_from')):
                worked_days = slip.contract_id.resource_calendar_id.attendance_ids.filtered(lambda x: x.date_from >= slip.date_from and x.date_from <= slip.date_to)
                print(worked_days)
    
            leaves = self._get_emp_leave_intervals(slip.employee_id, datetime.combine(slip.date_from, datetime.min.time()), datetime.combine(slip.date_to, datetime.max.time()))

            tz = pytz.timezone(self.env.user.tz)

            resource = self.env['resource.resource']
            attendence_lines = slip.contract_id.resource_calendar_id._attendance_intervals_batch(
                datetime.combine(slip.date_from, datetime.min.time()).replace(tzinfo=tz), 
                datetime.combine(slip.date_to, datetime.max.time()).replace(tzinfo=tz) ,
                resources = resource
                )
            if len(worked_days) == 0:
                worked_days = attendence_lines[resource.id]
            current_attendance = self.env['hr.attendance'].search([('employee_id','=',slip.employee_id.id),('check_in','>=',slip.date_from), ('check_in','<=',slip.date_to), ('is_absence','=', False)])
            ovr_morning_hours = sum(current_attendance.filtered(lambda x: not x.is_holiday and not x.is_weekend  and x.approve_overtime).mapped('ro_overtime_morning_hours'))
            ovr_night_hours = sum(current_attendance.filtered(lambda x: not x.is_holiday and not x.is_weekend  and x.approve_overtime).mapped('ro_overtime_night_hours'))
            overtime_hours = sum(current_attendance.filtered(lambda x: not x.is_holiday and not x.is_weekend  and x.approve_overtime).mapped('ro_overtime_hours'))
            overtime_count = len(current_attendance.filtered(lambda x: not x.is_holiday and not x.is_weekend and x.approve_overtime).filtered(lambda x: x.ro_overtime_hours>0))

            slip.morning_hours = ovr_morning_hours
            slip.night_hours = ovr_night_hours
            
            weekend_hours = sum(current_attendance.filtered(lambda x: x.is_weekend).mapped('worked_hours'))
            weekend_count = len(current_attendance.filtered(lambda x: x.is_weekend))

            public_holiday_hours = sum(current_attendance.filtered(lambda x: x.is_holiday).mapped('worked_hours'))
            public_holiday_count = len(current_attendance.filtered(lambda x: x.is_holiday))

            slip.no_days_holidays = weekend_count + public_holiday_count

            holiday_overtime_hours = sum(current_attendance.filtered(lambda x: x.is_holiday  and x.approve_overtime or x.is_weekend).mapped('worked_hours'))
            slip.no_hours_holidays = holiday_overtime_hours

            late_hours = sum(current_attendance.filtered(lambda x: not x.remove_late).mapped('late_hours'))
            late_count = len(current_attendance.filtered(lambda x: x.late_hours>0 and not x.remove_late))

            slip.delay_permits_hours = late_hours

            early_leave_hours = sum(current_attendance.filtered(lambda x: not x.remove_early).mapped('early_leave_hours'))
            early_leave_count = len(current_attendance.filtered(lambda x: x.early_leave_hours>0 and not x.remove_early))

            # raise UserError("Worked days: %s \n Attendance: %s \n Leaves: %s"%(str(len(worked_days)), str(current_attendance), str(leaves)))
            total_leaves = sum([no_days[0] for no_days in leaves])
            current_attendance_without_holiday = current_attendance.filtered(lambda x:not x.is_weekend)
            # and not x.is_holiday

            abs_count = len(worked_days) - len(current_attendance_without_holiday) - total_leaves -public_holiday_count
            if abs_count < 0:
                abs_count = 0
            print(abs_count)
            print(len(worked_days))
            print(total_leaves)
            print(len(current_attendance_without_holiday))
            print(public_holiday_count)

            # sum(leaves.mapped('number_of_days'))

            work_entry_obj = self.env['hr.work.entry.type']
            overtime_work_entry = work_entry_obj.search([('code', '=', 'ATTSHOT')])
            weekend_work_entry = work_entry_obj.search([('code', '=', 'ATTSHWE')])
            public_holiday_work_entry = work_entry_obj.search([('code', '=', 'ATTSHPH')])
            latin_work_entry = work_entry_obj.search([('code', '=', 'ATTSHLI')])
            absence_work_entry = work_entry_obj.search([('code', '=', 'ATTSHAB')])
            difftime_work_entry = work_entry_obj.search([('code', '=', 'ATTSHDT')])
            if not overtime_work_entry:
                raise ValidationError(_(
                    'Please Add Work Entry Type For Attendance Sheet Overtime With Code ATTSHOT'))
            if not weekend_work_entry:
                raise ValidationError(_(
                    'Please Add Work Entry Type For Attendance Sheet Weekend With Code ATTSHWE'))
            if not public_holiday_work_entry:
                raise ValidationError(_(
                    'Please Add Work Entry Type For Attendance Sheet Public Holiday With Code ATTSHPH'))
            if not latin_work_entry:
                raise ValidationError(_(
                    'Please Add Work Entry Type For Attendance Sheet Late In With Code ATTSHLI'))
            if not absence_work_entry:
                raise ValidationError(_(
                    'Please Add Work Entry Type For Attendance Sheet Absence With Code ATTSHAB'))
            if not difftime_work_entry:
                raise ValidationError(_(
                    'Please Add Work Entry Type For Attendance Sheet Diff Time With Code ATTSHDT'))
            overtime = [{
                'name': "Overtime",
                'code': 'OVT',
                'work_entry_type_id': overtime_work_entry[0].id,
                'sequence': 30,
                'number_of_days': overtime_count,
                'number_of_hours': overtime_hours,
            }]
            weekend = [{
                'name': "Weekend",
                'code': 'OVTWE',
                'work_entry_type_id': weekend_work_entry[0].id,
                'sequence': 30,
                'number_of_days': weekend_count,
                'number_of_hours': weekend_hours,
            }]
            public_holiday = [{
                'name': "Public Holiday",
                'code': 'OVTPH',
                'work_entry_type_id': public_holiday_work_entry[0].id,
                'sequence': 30,
                'number_of_days': public_holiday_count,
                'number_of_hours': public_holiday_hours,
            }]
            absence = [{
                'name': "Absence",
                'code': 'ABS',
                'work_entry_type_id': absence_work_entry[0].id,
                'sequence': 35,
                'number_of_days': abs_count,
                'number_of_hours': 0,
            }]
            late = [{
                'name': "Late In",
                'code': 'LATE',
                'work_entry_type_id': latin_work_entry[0].id,
                'sequence': 40,
                'number_of_days': late_count,
                'number_of_hours': late_hours,
            }]
            difftime = [{
                'name': "Difference time",
                'code': 'DIFFT',
                'work_entry_type_id': difftime_work_entry[0].id,
                'sequence': 45,
                'number_of_days': early_leave_count,
                'number_of_hours': early_leave_hours,
            }]
            worked_days_lines = overtime + weekend + public_holiday + late + absence + difftime

            vals = []
            for line in worked_days_lines:
                vals.append((0,0,line))
            if  len(vals)>0:
                slip.update({'worked_days_line_ids': vals})
