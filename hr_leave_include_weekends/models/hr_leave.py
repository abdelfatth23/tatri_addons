from odoo import api, fields, models
from datetime import date

class HrLeave(models.Model):
    _inherit = 'hr.leave'

    @api.depends('date_from', 'date_to', 'holiday_status_id', 'employee_id')
    def _compute_duration(self):

        for leave in self:

            total_days = 0.0

            if leave.date_from and leave.date_to:

                date_from = fields.Datetime.to_datetime(leave.date_from)
                date_to = fields.Datetime.to_datetime(leave.date_to)

                if leave.holiday_status_id.include_weekend:
                    total_days = (date_to.date() - date_from.date()).days + 1


                else:
                    if leave.employee_id:

                        work_data_batch = leave.employee_id._get_work_days_data_batch(
                            date_from,
                            date_to,
                            domain=[]
                        )
                        print(work_data_batch)

                        work_data = work_data_batch.get(leave.employee_id.id, {})

                        hours = work_data.get('hours', 0.0)

                        calendar = leave.employee_id.resource_calendar_id
                        day_hours = 8.0

                        if calendar and calendar.hours_per_day:
                            day_hours = calendar.hours_per_day

                        if day_hours > 0:
                            total_days = hours / day_hours
                        else:
                            total_days = 0.0

                        if 0 < total_days < 1:
                            total_days = 1.0

                        if hours >= day_hours:
                            total_days = round(hours / day_hours, 2)

            leave.number_of_days = total_days
            leave.number_of_days_display = total_days