# -*- coding: utf-8 -*-
#
#    Charif Soltani, Odoo Developer
#    Copyright (C) 2013-2018 Charif Soltani.
#
#    This program is not free software: you cannot redistribute it and/or modify it.
#
#    Created by Charif Soltani on 2018-01-01.
#
import logging
from openerp import models, fields, api

from openerp.osv import osv
from openerp.tools.translate import _
from openerp.tools.float_utils import float_compare
_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def create_from_ui(self, cr, uid, orders, context=None):
        """
            when user invoice an order with partial payment we must prevent odoo from creating
            wrong journal_ids because of the return amount.
            Case 1: if the order is fully payed and the client pays more than enough we allow return
            Case 2: If the order is not fully payed we will not return money to the client
        """
        submitted_references = [o['data']['name'] for o in orders]
        existing_order_ids = self.search(cr, uid, [('pos_reference', 'in', submitted_references)], context=context)
        existing_orders = self.read(cr, uid, existing_order_ids, ['pos_reference'], context=context)
        existing_references = set([o['pos_reference'] for o in existing_orders])
        orders_to_save = [o for o in orders if o['data']['name'] not in existing_references]
        for tmp_order in orders_to_save:
            # when we invoice pos order nothing is returned if the client didn't pay the whole amount
            # and returned amount is marked as credit in the invoice.
            amount_paid = tmp_order['data']['amount_paid']
            amount_total = tmp_order['data']['amount_total']
            if amount_total >= 0.0000001:
                is_paid = float_compare(amount_paid, amount_total, precision_digits=6) >= 0
            else:
                # in return pos is paid if amount_paid is less than total_amount
                is_paid = float_compare(amount_total, amount_paid, precision_digits=6) >= 0

            if not is_paid and tmp_order.get('to_invoice', False):
                tmp_order['data']['amount_return'] = 0.0

        return super(PosOrder, self).create_from_ui(cr, uid, orders, context)

    @api.multi
    def _reconcile_payments(self):
        """reconcile account of the order or the invoice"""
        for order in self:
            journal_entries = order.statement_ids.mapped('journal_entry_id').mapped(
                'line_id')
            if order.account_move:
                account_moves = order.account_move.line_id
            else:
                account_moves = order.invoice_id.move_id.line_id

            receivable_ids = account_moves.filtered(
                lambda move: not move.reconcile_id and move.account_id.type == 'receivable')
            payment_moves = journal_entries.filtered(lambda move: not move.reconcile_id
                                                                  and not move.reconcile_partial_id
                                                                  and move.account_id.type == 'receivable')
            rec_ids = receivable_ids | payment_moves
            try:
                rec_ids.reconcile_partial()
                pass
            except Exception as e:
                # if something is wrong show error in log
                _logger.error('Reconciliation error %s',
                              e)
                _logger.error('Reconciliation did not work for order %s',
                              order.name)
                continue


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.multi
    def _confirm_orders(self):
        self.ensure_one()
        result = super(PosSession, self)._confirm_orders()
        # after creating moves reconcile them
        for session in self:
            orders = session.order_ids.filtered(
                lambda order: order.state in ['invoiced', 'done'])
            orders.sudo()._reconcile_payments()
        return result
