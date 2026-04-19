from odoo import models, fields

class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    include_weekend = fields.Boolean(
        string="Include Weekends",
        help="If checked, this leave type counts weekends in duration calculation."
    )
