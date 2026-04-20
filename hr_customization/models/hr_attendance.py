# -*- coding: utf-8 -*-

from odoo import api,fields,models,_
from odoo.osv import expression
from odoo.tools import float_compare, float_is_zero
from odoo.exceptions import ValidationError, UserError, AccessError
from datetime import datetime, timedelta, date
import time
import pytz
import logging
from odoo.addons.hr_attendance.models.hr_attendance import HrAttendance
def write(self, vals):
    if vals.get('employee_id') and \
        vals['employee_id'] not in self.env.user.employee_ids.ids and \
        not self.env.user.has_group('hr_attendance.group_hr_attendance_officer'):
        raise AccessError(_("Do not have access, user cannot edit the attendances that are not his own."))
    # attendances_dates = self._get_attendances_dates()
    result = super(HrAttendance, self).write(vals)
    #Update
    # if any(field in vals for field in ['employee_id', 'check_in', 'check_out']):
    #     # Merge attendance dates before and after write to recompute the
    #     # overtime if the attendances have been moved to another day
    #     for emp, dates in self._get_attendances_dates().items():
    #         attendances_dates[emp] |= dates
    #     self._update_overtime(attendances_dates)
    #Update
    return result
HrAttendance.write=write

class HrAttendanceInh(models.Model):
    _inherit = 'hr.attendance'

    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_validity(self):
        """ Verifies the validity of the attendance record compared to the others from the same employee.
            For the same employee we must have :
                * maximum 1 "open" attendance record (without check_out)
                * no overlapping time slices with previous employee records
        """
        for attendance in self:
            # we take the latest attendance before our check_in time and check it doesn't overlap with ours
            last_attendance_before_check_in = self.env['hr.attendance'].search([
                ('employee_id', '=', attendance.employee_id.id),
                ('check_in', '<=', attendance.check_in),
                ('id', '!=', attendance.id),
            ], order='check_in desc', limit=1)
            if last_attendance_before_check_in and last_attendance_before_check_in.check_out and last_attendance_before_check_in.check_out > attendance.check_in:
                continue
                # raise ValidationError(_("Cannot create new attendance record for %(empl_name)s, the employee was already checked in on %(datetime)s",
                #                                    empl_name=attendance.employee_id.name,
                #                                    datetime=format_datetime(self.env, attendance.check_in, dt_format=False)))

            if not attendance.check_out:
                # if our attendance is "open" (no check_out), we verify there is no other "open" attendance
                no_check_out_attendances = self.env['hr.attendance'].search([
                    ('employee_id', '=', attendance.employee_id.id),
                    ('check_out', '=', False),
                    ('id', '!=', attendance.id),
                ], order='check_in desc', limit=1)
                if no_check_out_attendances:
                    continue
                    # raise ValidationError(_("Cannot create new attendance record for %(empl_name)s, the employee hasn't checked out since %(datetime)s",
                    #                                    empl_name=attendance.employee_id.name,
                    #                                    datetime=format_datetime(self.env, no_check_out_attendances.check_in, dt_format=False)))
            else:
                # we verify that the latest attendance with check_in time before our check_out time
                # is the same as the one before our check_in time computed before, otherwise it overlaps
                last_attendance_before_check_out = self.env['hr.attendance'].search([
                    ('employee_id', '=', attendance.employee_id.id),
                    ('check_in', '<', attendance.check_out),
                    ('id', '!=', attendance.id),
                ], order='check_in desc', limit=1)
                if last_attendance_before_check_out and last_attendance_before_check_in != last_attendance_before_check_out:
                    continue
                    # raise ValidationError(_("Cannot create new attendance record for %(empl_name)s, the employee was already checked in on %(datetime)s",
                    #                                    empl_name=attendance.employee_id.name,
                    #                                    datetime=format_datetime(self.env, last_attendance_before_check_out.check_in, dt_format=False)))


    def conv_time_float(self, value):
        vals = value.split(':')
        t, hours = divmod(float(vals[0]), 24)
        t, minutes = divmod(float(vals[1]), 60)
        minutes = minutes / 60.0
        return hours + minutes

    def get_public_holiday(self, date, emp):
        public_holiday = []
        public_holidays = self.env['hr.public.holiday'].sudo().search(
            [('date_from', '<=', date), ('date_to', '>=', date),
             ('state', '=', 'active')])
        for ph in public_holidays:
            if not ph.emp_ids:
                return public_holidays
            if emp.id in ph.emp_ids.ids:
                public_holiday.append(ph.id)
            if emp.department_id in ph.dep_ids.ids:
                public_holiday.append(ph.id)


        return public_holiday

    def get_schedule_swaps(self, date, emp):
        swap_schedule = self.env['hr.employee.schedule']
        swap_schedules = self.env['hr.employee.schedule'].sudo().search(
            [('date_from', '<=', date), ('date_to', '>=', date),
             ('emp_id', '=', emp.id),
             ('state', '=', 'active')])
        for ph in swap_schedules:
            swap_schedule |= ph
        return swap_schedule


    def calculate_day_hours(self, start_datetime, end_datetime, morning_start_hour=6, night_end_hour=18):
        """Calculates day hours BETWEEN two datetimes, from morning_start_hour to night_end_hour."""

        total_day_seconds = 0

        current_date = start_datetime.date()  # Start from the date of the start_datetime

        while current_date <= end_datetime.date():  # Iterate through the dates
            morning_start = datetime(current_date.year, current_date.month, current_date.day, morning_start_hour, 0, 0)
            night_end = datetime(current_date.year, current_date.month, current_date.day, night_end_hour, 0, 0)

            if night_end < morning_start:  # Overnight shift
                night_end = night_end + timedelta(days=1)  # Add one day to the night_end
                # datetime(current_date.year, current_date.month, current_date.day + 1, night_end_hour, 0, 0)

            # Check if there's any overlap between day hours and the specified time range
            if (morning_start <= end_datetime and night_end >= start_datetime):  # There is an overlap
                # Calculate the intersection between the times and the day schedule for the current day.
                intersection_start = max(start_datetime, morning_start)
                intersection_end = min(end_datetime, night_end)

                if intersection_start < intersection_end:  # Only count if there's a valid overlap
                    day_seconds_in_slice = (intersection_end - intersection_start).total_seconds()
                    total_day_seconds += day_seconds_in_slice

            current_date += timedelta(days=1)  # Move to the next day

        return total_day_seconds / 3600  # Convert seconds to hours

    @api.depends('employee_id', 'check_in', 'check_out')
    def _compute_target_hours(self):
        for this in self:
            this.is_weekend = False
            this.is_holiday = False
            this.is_absence = False
            this.target_hours = 0
            this.late_count = 0
            this.late_hours = 0
            this.overtime_count = 0
            this.ro_overtime_hours = 0
            this.ro_overtime_morning_hours = 0
            this.ro_overtime_night_hours = 0
            this.early_leave_count = 0
            this.early_leave_hours = 0

            if this.employee_id and this.check_in and this.check_out:
                contracts = self.env['hr.contract'].search([
                    ('employee_id', '=', this.employee_id.id),
                    ('state', '=', 'open')
                ], limit=1)

                if contracts:
                    this.target_hours = contracts.resource_calendar_id.hours_per_day
                    print(this.target_hours)
                    tz = pytz.timezone(self.env.user.tz or 'UTC')
                    print(tz)

                    check_in = this.check_in.astimezone(tz).replace(tzinfo=None)
                    check_out = this.check_out.astimezone(tz).replace(tzinfo=None)

                    policy_id = contracts.att_policy_id
                    checkin_hour = self.conv_time_float(check_in.strftime("%H:%M"))
                    print(checkin_hour)
                    checkout_hour = self.conv_time_float(check_out.strftime("%H:%M")) if check_out else False

                    in_check_factor = 24 - checkin_hour
                    out_check_factor = 24 - checkout_hour if checkout_hour else 0

                    if check_in.date() == check_out.date():
                        check_in_range = check_in.date()
                    elif (check_in + timedelta(hours=3)).date() == check_out.date():
                        check_in_range = check_out.date()
                    elif in_check_factor < out_check_factor:
                        check_in_range = check_in.date()
                    else:
                        check_in_range = check_in.date()

                    today_name = check_in_range.strftime("%A")
                    day_ref = {
                        'Monday': '0', 'Tuesday': '1', 'Wednesday': '2',
                        'Thursday': '3', 'Friday': '4', 'Saturday': '5', 'Sunday': '6'
                    }.get(today_name, False)

                    if contracts.resource_calendar_id.attendance_ids:
                        schedule_swaps = self.get_schedule_swaps(check_in_range, this.employee_id)
                        day_in_calender = contracts.resource_calendar_id.attendance_ids.filtered(
                            lambda x: x.dayofweek == day_ref and x.date_from
                        )

                        for day in day_in_calender:
                            in_calender_hour = time.strftime("%H:%M:%S", time.gmtime(day.hour_from * 3600))
                            out_calender_hour = time.strftime("%H:%M:%S", time.gmtime(day.hour_to * 3600))

                            # ✅ Skip invalid date_from/date_to values
                            if not day.date_from or not day.date_to:
                                continue

                            try:
                                in_calender = datetime.strptime(f"{day.date_from} {in_calender_hour}", "%Y-%m-%d %H:%M:%S")
                                out_calender = datetime.strptime(f"{day.date_to} {out_calender_hour}", "%Y-%m-%d %H:%M:%S")
                            except Exception as e:
                                logging.warning(f"Skipping invalid calendar day for attendance {this.id}: {e}")
                                continue

                            if (check_in >= in_calender - timedelta(hours=2) and check_in < out_calender) or \
                               (check_out >= in_calender and check_out <= out_calender + timedelta(hours=2)):
                                day_in_calender = day
                                check_in_range = day.date_from
                                break

                        if not day_in_calender:
                            day_in_calender = contracts.resource_calendar_id.attendance_ids.filtered(
                                lambda x: x.dayofweek == day_ref and not x.date_from
                            )
                            print(day_in_calender,"calender")


                        calender_from = calender_to = 0
                        if day_in_calender or schedule_swaps:

                            if schedule_swaps:
                                calender_date_from = schedule_swaps[0].date_from
                                calender_date_to = schedule_swaps[0].date_to
                                calender_from = schedule_swaps[0].hour_from
                                calender_to = schedule_swaps[0].hour_to
                            else:
                                calender_date_from = day_in_calender[0].date_from
                                calender_date_to = day_in_calender[0].date_to
                                calender_from = day_in_calender[0].hour_from
                                print(calender_from,"ddd")
                                calender_to = day_in_calender[0].hour_to
                                print(calender_to,"ddd")

                            # ✅ Validate before parsing
                            cal_date_from = calender_date_from or check_in_range
                            cal_date_to = calender_date_to or check_in_range

                            in_calender_hour = time.strftime("%H:%M:%S", time.gmtime(calender_from * 3600))
                            out_calender_hour = time.strftime("%H:%M:%S", time.gmtime(calender_to * 3600))

                            in_calender = datetime.strptime(
                                f"{cal_date_from} {in_calender_hour}",
                                "%Y-%m-%d %H:%M:%S"
                            )

                            out_calender = datetime.strptime(
                                f"{cal_date_to} {out_calender_hour}",
                                "%Y-%m-%d %H:%M:%S"
                            )

                            # 🕒 Late check
                            print(in_calender,"calender_in")
                            print(out_calender,"calender_out")
                            if check_in > in_calender:
                                in_diff = (check_in - in_calender).seconds / 3600
                                if policy_id:
                                    policy_late, late_cnt = policy_id.get_late(in_diff, [])
                                    if policy_late > in_diff:
                                        policy_late -= in_diff
                                    if policy_late > contracts.resource_calendar_id.late_deduct:
                                        this.late_hours = policy_late
                                        this.late_count = 1
                                    elif contracts.resource_calendar_id.allowed_late < policy_late <= contracts.resource_calendar_id.late_deduct:
                                        this.late_hours = policy_late
                                        this.late_count = 0.5

                            # ⏱ Overtime
                            out_diff = (check_out - out_calender).total_seconds() / 3600
                            if out_diff > 0 and policy_id:
                                this.overtime_count = 1
                                overtime_policy = policy_id.get_overtime() or {}
                                wd_after = overtime_policy.get('wd_after', 0)
                                wd_rate = overtime_policy.get('wd_rate', 0)

                                if out_diff >= wd_after:
                                    out_diff += out_diff * wd_rate
                                    night_overtime = this.calculate_day_hours(out_calender, check_out, 18, 6)
                                    morning_overtime = this.calculate_day_hours(out_calender, check_out, 6, 18)
                                else:
                                    out_diff = 0
                                    night_overtime = morning_overtime = 0

                                this.ro_overtime_hours = out_diff
                                this.ro_overtime_morning_hours = morning_overtime
                                this.ro_overtime_night_hours = night_overtime

                            # 🕔 Early leave
                            if check_out < out_calender and policy_id:
                                print(policy_id,"peppe")
                                out_diff = (out_calender - check_out).seconds / 3600
                                early_leave_policy = policy_id.get_diff(out_diff)
                                this.early_leave_hours = early_leave_policy
                                if this.early_leave_hours:
                                    this.early_leave_count = 1
                        else:
                            this.is_weekend = True

                        # 🎉 Public holiday
                        print(check_in_range)
                        if self.get_public_holiday(check_in_range, this.employee_id):
                            this.is_holiday = True

                        # 🚫 Absence
                        if not this.is_weekend and not this.is_holiday:
                            print("id")
                            is_absence_check = False
                            if (in_calender > check_in and (in_calender - check_in).seconds / 3600 > 6) or \
                               (in_calender < check_in and (check_in - in_calender).seconds / 3600 > 6):
                                is_absence_check = True
                            if out_calender > check_out and (out_calender - check_out).seconds / 3600 > 6:
                                is_absence_check = True

                            if is_absence_check:
                                this.is_absence = True
                                this.late_hours = 0
                                this.early_leave_hours = 0
                                this.ro_overtime_hours = 0
                                this.ro_overtime_morning_hours = 0
                                this.ro_overtime_night_hours = 0
            else:
                this.target_hours = 0

    target_hours= fields.Float('Target Hours', compute='_compute_target_hours', store=True)

    late_count= fields.Float('Late count', compute='_compute_target_hours', store=True)
    late_hours= fields.Float('Late Hours', compute='_compute_target_hours', store=True)

    overtime_count= fields.Float('OverTime Count', compute='_compute_target_hours', store=True)
    ro_overtime_hours= fields.Float('OverTime Hours', compute='_compute_target_hours', store=True)

    ro_overtime_morning_hours= fields.Float('Morning Hours', compute='_compute_target_hours', store=True)
    ro_overtime_night_hours= fields.Float('Night Hours', compute='_compute_target_hours', store=True)

    early_leave_count= fields.Float('Early Leave Count', compute='_compute_target_hours', store=True)
    early_leave_hours= fields.Float('Early Leave Hours', compute='_compute_target_hours', store=True)

    is_weekend = fields.Boolean('Is Weekend', compute='_compute_target_hours', store=True)
    is_holiday = fields.Boolean('Is Holyday', compute='_compute_target_hours', store=True)
    is_absence = fields.Boolean('Is Absance', compute='_compute_target_hours', store=True,readonly=False)
    approve_overtime = fields.Boolean('Approve Overtime', store=True)
    remove_late = fields.Boolean('Remove Late',  store=True)
    remove_early = fields.Boolean('Remove Early',  store=True)

    def action_approve_overtime(self):
        for record in self:
            record.approve_overtime = True
    def action_remove_late(self):
        for record in self:
            record.remove_late = True
    def action_remove_early(self):
        for record in self:
            record.remove_early = True
