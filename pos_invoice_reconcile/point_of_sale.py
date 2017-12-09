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
            is_paid = False
            if amount_total >= 0.0000001:
                is_paid = float_compare(amount_paid, amount_total, precision_digits=6) >= 0
            else:
                # in return pos is paid if amount_paid is less than total_amount
                is_paid = float_compare(amount_total, amount_paid, precision_digits=6) >= 0

            if not is_paid and tmp_order.get('to_invoice', False):
                tmp_order['data']['amount_return'] = 0.0

        return super(PosOrder, self).create_from_ui(cr, uid, orders, context)

    def action_invoice(self, cr, uid, ids, context=None):
        """
            Handle refund and creating stock picking for invoiced orders,
            we say this is refund when all quantities of order lines are all negative.
            I needed to copy the whole logic because i cannot use the code of super they don't
            handle dynamic type of the invoice.
        """
        inv_ref = self.pool.get('account.invoice')
        inv_line_ref = self.pool.get('account.invoice.line')
        product_obj = self.pool.get('product.product')
        inv_ids = []

        for order in self.pool.get('pos.order').browse(cr, uid, ids, context=context):
            if order.invoice_id:
                inv_ids.append(order.invoice_id.id)
                continue
            if not order.partner_id:
                raise osv.except_osv(_('Error!'), _('Please provide a partner for the sale.'))

            # check if all quantities of the order are negative  values
            # TODO: add configuration for this features.
            is_refund = all(line.qty <= 0 for line in order.lines)
            if is_refund:
                _logger.info('Creating refund for return : %s', order.name)

            acc = order.partner_id.property_account_receivable.id
            invoice_type = is_refund and 'out_refund' or 'out_invoice'
            inv = {
                'name': order.name,
                'origin': order.name,
                'account_id': acc,
                'journal_id': order.sale_journal.id or None,
                'type': invoice_type,
                'reference': order.name,
                'partner_id': order.partner_id.id,
                'comment': order.note or '',
                'currency_id': order.pricelist_id.currency_id.id,  # considering partner's sale pricelist's currency
            }
            inv.update(inv_ref.onchange_partner_id(cr, uid, [], invoice_type, order.partner_id.id)['value'])
            inv.update({'fiscal_position': False})
            if not inv.get('account_id', None):
                inv['account_id'] = acc
            inv_id = inv_ref.create(cr, uid, inv, context=context)

            self.write(cr, uid, [order.id], {'invoice_id': inv_id, 'state': 'invoiced'}, context=context)

            inv_ids.append(inv_id)
            for line in order.lines:
                inv_line = {
                    'invoice_id': inv_id,
                    'product_id': line.product_id.id,
                    # if it's refund when we create invoice we must transform qty from negative to positive
                    'quantity': is_refund and (-1 * line.qty) or line.qty,
                }
                inv_name = product_obj.name_get(cr, uid, [line.product_id.id], context=context)[0][1]
                inv_line.update(inv_line_ref.product_id_change(cr, uid, [],
                                                               line.product_id.id,
                                                               line.product_id.uom_id.id,
                                                               line.qty, partner_id=order.partner_id.id)['value'])
                if not inv_line.get('account_analytic_id', False):
                    inv_line['account_analytic_id'] = \
                        self._prepare_analytic_account(cr, uid, line,
                                                       context=context)
                inv_line['price_unit'] = line.price_unit
                inv_line['discount'] = line.discount
                inv_line['name'] = inv_name
                inv_line['invoice_line_tax_id'] = [(6, 0, inv_line['invoice_line_tax_id'])]
                inv_line_ref.create(cr, uid, inv_line, context=context)
            inv_ref.button_reset_taxes(cr, uid, [inv_id], context=context)
            self.signal_workflow(cr, uid, [order.id], 'invoice')
            inv_ref.signal_workflow(cr, uid, [inv_id], 'validate')

        if not inv_ids: return {}

        # creating picking move after invoicing.
        # TODO: add configuration for this features.
        self.create_picking(cr, uid, ids, context=context)

        mod_obj = self.pool.get('ir.model.data')
        res = mod_obj.get_object_reference(cr, uid, 'account', 'invoice_form')
        res_id = res and res[1] or False

        return {
            'name': _('Customer Invoice'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': [res_id],
            'res_model': 'account.invoice',
            'context': "{'type':'out_invoice'}",
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current',
            'res_id': inv_ids and inv_ids[0] or False,
        }

    def create_picking(self, cr, uid, ids, context=None):
        """
            Create a picking for each order and validate it.
            i kept the same logic just add Exception Handling when validating the picking.
            because this make an error for product that need Serial number.
        """
        picking_obj = self.pool.get('stock.picking')
        partner_obj = self.pool.get('res.partner')
        move_obj = self.pool.get('stock.move')

        for order in self.browse(cr, uid, ids, context=context):
            if all(t == 'service' for t in order.lines.mapped('product_id.type')):
                continue
            addr = order.partner_id and partner_obj.address_get(cr, uid, [order.partner_id.id], ['delivery']) or {}
            picking_type = order.picking_type_id
            picking_id = False
            if picking_type:
                picking_id = picking_obj.create(cr, uid, {
                    'origin': order.name,
                    'partner_id': addr.get('delivery', False),
                    'date_done': order.date_order,
                    'picking_type_id': picking_type.id,
                    'company_id': order.company_id.id,
                    'move_type': 'direct',
                    'note': order.note or "",
                    'invoice_state': 'none',
                }, context=context)
                self.write(cr, uid, [order.id], {'picking_id': picking_id}, context=context)
            location_id = order.location_id.id
            if order.partner_id:
                destination_id = order.partner_id.property_stock_customer.id
            elif picking_type:
                if not picking_type.default_location_dest_id:
                    raise osv.except_osv(_('Error!'), _(
                        'Missing source or destination location for picking type %s. Please configure those fields and try again.' % (
                            picking_type.name,)))
                destination_id = picking_type.default_location_dest_id.id
            else:
                destination_id = partner_obj.default_get(cr, uid, ['property_stock_customer'], context=context)[
                    'property_stock_customer']

            move_list = []
            for line in order.lines:
                if line.product_id and line.product_id.type == 'service':
                    continue

                move_list.append(move_obj.create(cr, uid, {
                    'name': line.name,
                    'product_uom': line.product_id.uom_id.id,
                    'product_uos': line.product_id.uom_id.id,
                    'picking_id': picking_id,
                    'picking_type_id': picking_type.id,
                    'product_id': line.product_id.id,
                    'product_uos_qty': abs(line.qty),
                    'product_uom_qty': abs(line.qty),
                    'state': 'draft',
                    'location_id': location_id if line.qty >= 0 else destination_id,
                    'location_dest_id': destination_id if line.qty >= 0 else location_id,
                }, context=context))

            if picking_id:
                picking_obj.action_confirm(cr, uid, [picking_id], context=context)
                picking_obj.force_assign(cr, uid, [picking_id], context=context)
                try:
                    picking_obj.action_done(cr, uid, [picking_id], context=context)
                except Exception as e:
                    _logger.error('Automatic validation of picking fails do to %s', e)
            elif move_list:
                move_obj.action_confirm(cr, uid, move_list, context=context)
                move_obj.force_assign(cr, uid, move_list, context=context)
                try:
                    move_obj.action_done(cr, uid, move_list, context=context)
                except Exception as e:
                    _logger.error('Automatic validation of picking move fails do to %s', e)
        return True

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
