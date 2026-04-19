# -*- coding: utf-8 -*-
{
    'name': "Add Fields in Payslip",

    'summary': """
        Add Fields in Payslip
        """,

    'description': """
        Add Fields in Payslip
    """,

    'author': "Roaya",
    'website': "https://www.roayadm.com",

    'category': '',
    'version': '17.0',

    # any module necessary for this one to work correctly
    'depends': ['hr','hr_payroll','hr_payroll_account','hr_contract','rm_eg_hr_payroll','ro_hr_shift_swap'],

    # always loaded
    'data': [
        'data/data.xml',
        'views/hr_contract_view.xml',
        'views/view.xml',
        'views/resource_calender_view.xml',
        'views/hr_attendance_view.xml',
    ],
    'license': 'OPL-1'
}
