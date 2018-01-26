
openerp.pos_invoice_reconcile = function(instance) {
    console.info('rani hna');

     var module = instance.point_of_sale;


     // update the screen a little bit to enable invoice when the user didn't save payment
     openerp_pos_partial_payment_screens_update(instance, module);

};

    
