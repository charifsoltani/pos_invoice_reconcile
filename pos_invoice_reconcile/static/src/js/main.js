
openerp.pos_partial_payment = function(instance) {

     var module = instance.point_of_sale;

     // update the screen a little bit to enable invoice when the user didn't save payment
     openerp_pos_partial_payment_screens_update(instance, module);

};

    
