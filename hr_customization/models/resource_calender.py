# -*- coding: utf-8 -*-

from odoo import api,fields,models,_
from odoo.tools import float_compare, float_is_zero
from odoo.exceptions import ValidationError, UserError
import datetime

class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    allowed_late = fields.Float()
    late_deduct = fields.Float()



