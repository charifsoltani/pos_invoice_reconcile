// add User selection popup
function openerp_pos_partial_payment_screens_update(instance, module){ //module is instance.point_of_sale
    var QWeb = instance.web.qweb,
    _t = instance.web._t;


          // now in pos the invoice button is not enabled
          module.PaymentScreenWidget = module.PaymentScreenWidget.extend({
              update_payment_summary: function() {
              // same logic of pos with small changes
                        var currentOrder = this.pos.get('selectedOrder');
                        var paidTotal = currentOrder.getPaidTotal();
                        var dueTotal = currentOrder.getTotalTaxIncluded();
                        var remaining = dueTotal > paidTotal ? dueTotal - paidTotal : 0;
                        var change = paidTotal > dueTotal ? paidTotal - dueTotal : 0;

                        this.$('.payment-due-total').html(this.format_currency(dueTotal));
                        this.$('.payment-paid-total').html(this.format_currency(paidTotal));
                        this.$('.payment-remaining').html(this.format_currency(remaining));
                        this.$('.payment-change').html(this.format_currency(change));
                        if(currentOrder.selected_orderline === undefined){
                            remaining = 1;  // What is this ?
                        }

                        if(this.pos_widget.action_bar){
                            this.pos_widget.action_bar.set_button_disabled('validation', !this.is_paid());
                            // Enable credit always because credit will create an invoice for the client
                            // and payment should be on that invoice not in this  cashBox.
                            //this.pos_widget.action_bar.set_button_disabled('invoice', !this.is_paid());
                        }
                    },
                    is_paid: function(){
                        var currentOrder = this.pos.get('selectedOrder');

                        return (currentOrder.getTotalTaxIncluded() < 0.000001?
                                // when user return products
                                currentOrder.getPaidTotal() - 0.000001 <= currentOrder.getTotalTaxIncluded() :
                                // when the client bay products
                                currentOrder.getPaidTotal() + 0.000001 >= currentOrder.getTotalTaxIncluded());

                    },
                // save_order
                validate_order: function(options) {
                    // i keep the same logic in pos validate_order but with small change
                    // to pass the check if the order is payed when the order is invoiced
                    var self = this;
                    options = options || {};

                    var currentOrder = self.pos.get('selectedOrder');

                    if(currentOrder.get('orderLines').models.length === 0){
                        self.pos_widget.screen_selector.show_popup('error',{
                            'message': _t('Empty Order'),
                            'comment': _t('There must be at least one product in your order before it can be validated'),
                        });
                        return;
                    }

                    var plines = currentOrder.get('paymentLines').models;
                    for (var i = 0; i < plines.length; i++) {
                        if (plines[i].get_type() === 'bank' && plines[i].get_amount() < 0) {
                            self.pos_widget.screen_selector.show_popup('error',{
                                'message': _t('Negative Bank Payment'),
                                'comment': _t('You cannot have a negative amount in a Bank payment. Use a cash payment method to return money to the customer.'),
                            });
                            return;
                        }
                    }

                    // only stop the order from being send if the user didn't invoice the order
                    if(!self.is_paid() && !options.invoice){
                        //TODO: show error for users so he will not be confused!!
                        return;
                    }

                    // The exact amount must be paid if there is no cash payment method defined.
                    if (!options.invoice && Math.abs(currentOrder.getTotalTaxIncluded() - currentOrder.getPaidTotal()) > 0.00001) {
                        var cash = false;
                        for (var i = 0; i < self.pos.cashregisters.length; i++) {
                            cash = cash || (self.pos.cashregisters[i].journal.type === 'cash');
                        }
                        if (!cash) {
                            self.pos_widget.screen_selector.show_popup('error',{
                                message: _t('Cannot return change without a cash payment method'),
                                comment: _t('There is no cash payment method available in this point of sale to handle the change.\n\n Please pay the exact amount or add a cash payment method in the point of sale configuration'),
                            });
                            return;
                        }
                    }

                    if (self.pos.config.iface_cashdrawer) {
                            self.pos.proxy.open_cashbox();
                    }

                    if(options.invoice){
                        // deactivate the validation button while we try to send the order
                        self.pos_widget.action_bar.set_button_disabled('validation',true);
                        self.pos_widget.action_bar.set_button_disabled('invoice',true);

                        var invoiced = self.pos.push_and_invoice_order(currentOrder);

                        invoiced.fail(function(error){
                            if(error === 'error-no-client'){
                                self.pos_widget.screen_selector.show_popup('error',{
                                    message: _t('An anonymous order cannot be invoiced'),
                                    comment: _t('Please select a client for this order. This can be done by clicking the order tab'),
                                });
                            }else{
                                self.pos_widget.screen_selector.show_popup('error',{
                                    message: _t('The order could not be sent'),
                                    comment: _t('Check your internet connection and try again.'),
                                });
                            }
                            self.pos_widget.action_bar.set_button_disabled('validation', !self.is_paid());
                            self.pos_widget.action_bar.set_button_disabled('invoice',false);
                        });

                        invoiced.done(function(){
                            self.pos_widget.action_bar.set_button_disabled('validation',false);
                            self.pos_widget.action_bar.set_button_disabled('invoice',false);
                            self.pos.get('selectedOrder').destroy();
                        });

                    }else{
                        self.pos.push_order(currentOrder)
                        if(self.pos.config.iface_print_via_proxy){
                            var receipt = currentOrder.export_for_printing();
                            self.pos.proxy.print_receipt(QWeb.render('XmlReceipt',{
                                receipt: receipt, widget: self,
                            }));
                            self.pos.get('selectedOrder').destroy();    //finish order and go back to scan screen
                        }else{
                            self.pos_widget.screen_selector.set_current_screen(self.next_screen);
                        }
                    }

                    // hide onscreen (iOS) keyboard
                    setTimeout(function(){
                        document.activeElement.blur();
                        $("input").blur();
                    },250);
                },
          });

}
