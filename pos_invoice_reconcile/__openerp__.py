# -*- coding: utf-8 -*-
#
#    Charif Soltani, Odoo Developer
#    Copyright (C) 2013-2018 Charif Soltani.
#
#    This program is not free software: you cannot redistribute it and/or modify it.
#
#    Created by Charif Soltani on 2018-01-01.
#
{
    'name': 'POS Invoice partial and full reconciliation',
    'version': '1.0.0',
    'category': 'Point of Sale',
    'author': 'Soltani Charif',
    'license': 'AGPL-3',
    'website': 'https://www.linkedin.com/in/soltani-charif-b0351811a/',
    'summary': """
           Keep track of client payments and invoices.
           Enable partial payment for invoiced orders.
        """,
    'images': [],
    'depends': [
        'point_of_sale',
    ],
    'data': [
        'views/point_of_sale.xml',
    ],
    'demo': [],
    'test': [],
    'application': True,
    'active': False,
    'installable': True,
}

