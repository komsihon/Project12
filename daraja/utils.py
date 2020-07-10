import logging
from datetime import datetime
from threading import Thread

from django.conf import settings
from django.template import Context
from django.template.loader import get_template
from django.utils.translation import activate, gettext as _

from ikwen.conf import settings as ikwen_settings
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member
from ikwen.core.models import Service, Application
from ikwen.core.utils import add_database, set_counters, increment_history_field, add_event, get_mail_content, \
    XEmailMessage

from daraja.models import DARAJA, Follower, REFEREE_JOINED_EVENT, Dara, DaraRequest

logger = logging.getLogger('ikwen')


def get_service_instance(request, using=None):
    app = Application.objects.get(slug=DARAJA)
    if using:
        return Service.objects.using(using).get(app=app, member=request.user)
    return Service.objects.get(app=app, member=request.user)


def set_customer_dara(service, referrer, member):
    """
    Binds referrer to member referred.
    :param service: Referred Service
    :param referrer: Member who referred (The Dara)
    :param member: Referred Member
    :return:
    """
    try:
        db = service.database
        add_database(db)
        app = Application.objects.using(db).get(slug=DARAJA)
        dara_service = Service.objects.using(db).get(app=app, member=referrer)
        follower, change = Follower.objects.using(db).get_or_create(member=member)
        if follower.referrer:
            return

        follower.referrer = dara_service
        follower.save()

        dara_db = dara_service.database
        add_database(dara_db)
        member.save(using=dara_db)
        follower.save(using=dara_db)
        try:
            dara_umbrella = Dara.objects.using(UMBRELLA).get(member=referrer)
            if dara_umbrella.level == 2:
                if dara_umbrella.xp in [2, 3, 4]:
                    dara_umbrella.xp += 1
                    dara_umbrella.save()
        except:
            pass

        service_mirror = Service.objects.using(dara_db).get(pk=service.id)
        set_counters(service_mirror)
        increment_history_field(service_mirror, 'community_history')

        daraja_service = Service.objects.using(UMBRELLA).get(project_name_slug=DARAJA)
        add_event(daraja_service, REFEREE_JOINED_EVENT,
                  member=referrer, model='accesscontrol.Member', object_id=member.id)

        diff = datetime.now() - member.date_joined

        activate(referrer.language)
        sender = "%s via ikwen <no-reply@ikwen.com>" % member.full_name
        if diff.days > 1:
            subject = _("I'm back on %s !" % service.project_name)
        else:
            subject = _("I just joined %s !" % service.project_name)
        html_content = get_mail_content(subject, template_name='daraja/mails/referee_joined.html',
                                        extra_context={'referred_service_name': service.project_name, 'referee': member,
                                                       'referred_service_url': service.url})
        msg = XEmailMessage(subject, html_content, sender, [referrer.email])
        msg.content_subtype = "html"
        Thread(target=lambda m: m.send(), args=(msg, )).start()
    except:
        logger.error("%s - Error while setting Customer Dara", exc_info=True)


def referee_registration_callback(request, *args, **kwargs):
    """
    This function should run upon registration. This is achieved
    by adding its path to the IKWEN_REGISTER_EVENTS in settings file.
    This does necessary operations to bind a Dara to the Member newly login in.
    """
    referrer = request.COOKIES.get('referrer')
    if referrer:
        try:
            service = Service.objects.get(pk=getattr(settings, 'IKWEN_SERVICE_ID'))
            dara_member = Member.objects.get(pk=referrer)
            set_customer_dara(service, dara_member, request.user)
        except:
            pass


def send_dara_notification_email(dara_service, amount, referrer_earnings, tx_on):
    service = Service.objects.get(pk=getattr(settings, 'IKWEN_SERVICE_ID'))
    config = service.config
    template_name = 'daraja/mails/new_transaction.html'

    activate(dara_service.member.language)
    subject = _("New transaction on %s" % config.company_name)
    try:
        dashboard_url = 'http://daraja.ikwen.com/daraja/dashboard'
        html_content = get_mail_content(subject, template_name=template_name,
                                        extra_context={'currency_symbol': config.currency_symbol, 'amount': amount,
                                                       'dara_earnings': referrer_earnings,
                                                       'transaction_time': tx_on.strftime('%Y-%m-%d %H:%M:%S'),
                                                       'account_balance': dara_service.balance,
                                                       'dashboard_url': dashboard_url})
        sender = 'ikwen Daraja <no-reply@ikwen.com>'
        msg = XEmailMessage(subject, html_content, sender, [dara_service.member.email])
        msg.content_subtype = "html"
        Thread(target=lambda m: m.send(), args=(msg,)).start()
    except:
        logger.error("Failed to notify %s Dara after follower purchase." % service, exc_info=True)


def render_referee_joined_event(event, request):
    """
    Renders the RefereeJoined Event on ikwen console
    """
    try:
        member = Member.objects.get(pk=event.object_id)
    except :
        return ''
    html_template = get_template('daraja/events/referee_joined.html')
    context = {'event': event, 'member': member, 'IKWEN_MEDIA_URL': ikwen_settings.MEDIA_URL}
    c = Context(context)
    return html_template.render(c)


def render_request_access_event(event, request):
    """
    Renders the RequestAccess Event on ikwen console
    """
    try:
        dara_request = DaraRequest.objects.select_related('service', 'member').get(pk=event.object_id)
        dara = Dara.objects.get(member=dara_request.member)
    except :
        return ''
    html_template = get_template('daraja/events/dara_request_access.html')
    context = {'event': event, 'dara': dara, 'member': dara_request.member,
               'service': dara_request.service, 'IKWEN_MEDIA_URL': ikwen_settings.MEDIA_URL}
    c = Context(context)
    return html_template.render(c)
