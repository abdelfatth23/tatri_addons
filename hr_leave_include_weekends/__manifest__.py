{
    'name': 'HR Leave Include Weekends',
    'version': '17.0.1.1.0',
    'summary': 'Force all time off requests to include weekends when calculating duration',
    'category': 'Human Resources',
    'author': 'Avalon-AI',
    'depends': ['hr_holidays'],
    'data': [
        'views/hr_leave_type_view.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
