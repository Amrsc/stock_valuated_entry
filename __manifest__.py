# -*- coding: utf-8 -*-

{
    'name': 'Stock Entrée Valorisée',
    'version': '14.0e',
    'author': 'ALIK Amrane',
    'category': '',
    'sequence': 1,
    'website': '',
    'summary': '',
    'description': """

    """,
    'images': ['static/description/icon.png',],
    'depends': ['stock'],
    'data': [
        'views/entry.xml',
        'views/menu.xml',
        'views/sequence.xml',

        # security
        'security/ir.model.access.csv',
    ],
    'demo': [],
    'test': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
