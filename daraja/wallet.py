from time import strptime

from django.views.generic import TemplateView
from ikwen.core.models import OperatorWallet
from ikwen.cashout.models import CashOutRequest, CashOutAddress, CashOutMethod
from ikwen.accesscontrol.backends import UMBRELLA

from daraja.models import Dara
from daraja.utils import get_service_instance


class Payments(TemplateView):
    template_name = 'cashout/payments.html'

    def get_context_data(self, **kwargs):
        service = get_service_instance(self.request, using=UMBRELLA)
        context = super(Payments, self).get_context_data(**kwargs)
        from datetime import datetime
        cash_out_min = service.config.cash_out_min
        wallets = OperatorWallet.objects.using('wallets').filter(nonrel_id=service.id)
        context['wallets'] = wallets
        payments = []
        for p in CashOutRequest.objects.using('wallets').filter(service_id=service.id).order_by('-id')[:10]:
            # Re-transform created_on into a datetime object
            try:
                p.created_on = datetime(*strptime(p.created_on[:19], '%Y-%m-%d %H:%M:%S')[:6])
            except TypeError:
                pass
            if p.amount_paid:
                p.amount = p.amount_paid
            payments.append(p)
        dara, update = Dara.objects.using(UMBRELLA).get_or_create(member=self.request.user)
        context['dara'] = dara
        context['payments'] = payments
        context['payment_addresses'] = CashOutAddress.objects.using(UMBRELLA).filter(service=service)
        context['payment_methods'] = CashOutMethod.objects.using(UMBRELLA).all()
        context['cash_out_min'] = cash_out_min
        context['can_cash_out'] = wallets.filter(balance__gte=cash_out_min).count() > 0
        return context
