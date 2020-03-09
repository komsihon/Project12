# -*- coding: utf-8 -*-
import logging
import subprocess
from datetime import datetime, timedelta
from threading import Thread

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.template.defaultfilters import slugify
from django.utils.translation import gettext as _
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import SUDO, Member
from ikwen.core.models import Service, SERVICE_DEPLOYED, Application, Config
from ikwen.core.tools import generate_random_key
from ikwen.core.utils import add_database_to_settings, add_event, get_mail_content, \
    get_service_instance, clear_counters, add_database
from permission_backend_nonrel.models import UserPermissionList

from daraja.models import DARAJA, DARAJA_IKWEN_SHARE_RATE, DarajaConfig, Dara

logger = logging.getLogger('ikwen')


if getattr(settings, 'LOCAL_DEV', False):
    CLOUD_HOME = '/home/komsihon/PycharmProjects/CloudTest/'
else:
    CLOUD_HOME = '/home/ikwen/Cloud/'

DARAJA_CLOUD_FOLDER = CLOUD_HOME + 'Daraja/'
SMS_API_URL = 'http://websms.mobinawa.com/http_api?action=sendsms&username=675187705&password=depotguinness&from=$label&to=$recipient&msg=$text'

CASH_OUT_MIN = 5000  # Default cash out min for Daras

# from captcha.fields import ReCaptchaField


def deploy(member):
    app = Application.objects.get(slug=DARAJA)
    daraja_service = Service.objects.get(project_name_slug=DARAJA)
    playground_service = Service.objects.get(project_name_slug='playground')
    project_name_slug = slugify(member.username.split('@')[0])
    ikwen_name = project_name_slug.replace('-', '')
    pname = ikwen_name
    i = 0
    while True:
        try:
            Service.objects.using(UMBRELLA).get(project_name_slug=pname)
            i += 1
            pname = "%s%d" % (ikwen_name, i)
        except Service.DoesNotExist:
            ikwen_name = pname
            break
    api_signature = generate_random_key(30, alpha_num=True)
    while True:
        try:
            Service.objects.using(UMBRELLA).get(api_signature=api_signature)
            api_signature = generate_random_key(30, alpha_num=True)
        except Service.DoesNotExist:
            break
    database = ikwen_name
    domain = 'go.' + ikwen_name + '.ikwen.com'
    now = datetime.now()
    expiry = now + timedelta(days=15)

    service = Service(member=member, app=app, project_name=member.full_name, project_name_slug=ikwen_name,
                      domain=domain, database=database, expiry=expiry, monthly_cost=0, version=Service.FREE,
                      api_signature=api_signature, is_public=False)
    service.save(using=UMBRELLA)
    logger.debug("Service %s successfully created" % ikwen_name)

    # Import template database and set it up
    db_folder = DARAJA_CLOUD_FOLDER + '000Tpl/DB/000Default'
    host = getattr(settings, 'DATABASES')['default'].get('HOST', '127.0.0.1')
    subprocess.call(['mongorestore', '--host', host, '-d', database, db_folder])
    logger.debug("Database %s successfully created on host %s from %s." % (database, host, db_folder))

    add_database_to_settings(database)

    for s in member.get_services():
        db = s.database
        add_database_to_settings(db)
        collaborates_on_fk_list = member.collaborates_on_fk_list + [daraja_service.id, playground_service.id]
        customer_on_fk_list = member.customer_on_fk_list + [daraja_service.id, playground_service.id]
        Member.objects.using(db).filter(pk=member.id).update(collaborates_on_fk_list=collaborates_on_fk_list,
                                                             customer_on_fk_list=customer_on_fk_list)

    member.collaborates_on_fk_list = collaborates_on_fk_list
    member.customer_on_fk_list = customer_on_fk_list

    member.is_iao = True
    member.save(using=UMBRELLA)

    member.is_bao = True
    member.is_staff = True
    member.is_superuser = True

    app.save(using=database)
    member.save(using=database)
    logger.debug("Member %s access rights successfully set for service %s" % (member.username, ikwen_name))

    # Add member to SUDO Group
    obj_list, created = UserPermissionList.objects.using(database).get_or_create(user=member)
    obj_list.save(using=database)
    logger.debug("Member %s successfully added to sudo group for service: %s" % (member.username, ikwen_name))
    config = Config(service=service, cash_out_rate=DARAJA_IKWEN_SHARE_RATE,
                    currency_code='XAF', currency_symbol='XAF', decimal_precision=0,
                    company_name=ikwen_name, contact_email=member.email, contact_phone=member.phone,
                    cash_out_min=CASH_OUT_MIN)
    config.save(using=UMBRELLA)
    logger.debug("Dara config created for %s" % ikwen_name)

    service.save(using=database)

    # Add Member as Dara for ikwen
    ikwen_service = get_service_instance()
    daraja_config = DarajaConfig.objects.get(service=ikwen_service)
    dara, change = Dara.objects.get_or_create(member=member)
    dara.uname = ikwen_name
    dara.share_rate = daraja_config.referrer_share_rate
    dara.save()
    ikwen_service.save(using=database)
    ikwen_service_mirror = Service.objects.using(database).get(pk=ikwen_service.id)
    clear_counters(ikwen_service_mirror)

    # Add Member as Dara for Playground
    playground_config = DarajaConfig.objects.get(service=playground_service)
    playground_db = playground_service.database
    add_database(playground_db)
    member.save(using=playground_db)
    member = Member.objects.using(playground_db).get(pk=member.id)
    UserPermissionList.objects.using(playground_db).get_or_create(user=member)
    dara, change = Dara.objects.using(playground_db).get_or_create(member=member)
    dara.share_rate = playground_config.referrer_share_rate
    dara.save()
    service.save(using=playground_db)
    playground_service.save(using=database)
    playground_service_mirror = Service.objects.using(database).get(pk=playground_service.id)
    clear_counters(playground_service_mirror)

    # Send notification and Invoice to customer
    add_event(ikwen_service, SERVICE_DEPLOYED, member=member, object_id=service.id)
    sender = 'ikwen Daraja <no-reply@ikwen.com>'
    sudo_group = Group.objects.using(UMBRELLA).get(name=SUDO)
    add_event(ikwen_service, SERVICE_DEPLOYED, group_id=sudo_group.id, object_id=service.id)
    subject = _("Welcome to the business network.")
    registered_company_list_url = ikwen_service.url + reverse('daraja:registered_company_list')
    html_content = get_mail_content(subject, template_name='daraja/mails/service_deployed.html',
                                    extra_context={'registered_company_list_url': registered_company_list_url, 'member': member})
    msg = EmailMessage(subject, html_content, sender, [member.email])
    bcc = ['contact@ikwen.com', 'support@ikwen.com']
    msg.bcc = list(set(bcc))
    msg.content_subtype = "html"
    Thread(target=lambda m: m.send(), args=(msg, )).start()
    logger.debug("Notice email submitted to %s" % member.email)
    return service
