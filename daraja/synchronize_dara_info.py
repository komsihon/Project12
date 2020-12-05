import sys
import os
import logging
import csv
# import pyexcel
from datetime import datetime

from django.template.defaultfilters import slugify

from ikwen.accesscontrol.models import Member
from ikwen.core.utils import add_database
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.models import Application, Service
from ikwen.core.log import CRONS_LOGGING


from daraja.models import Dara, DarajaConfig
from daraja.views import _sync_member

reload(sys)
sys.setdefaultencoding('utf8')

os.environ.setdefault("DJANGO_SETTINGS_MODULE", 'ikwen.conf.settings')


logging.config.dictConfig(CRONS_LOGGING)
logger = logging.getLogger('ikwen.crons')


def synchronize():
    app_slug = 'kakocase'
    app = Application.objects.using(UMBRELLA).get(slug=app_slug)
    service_list = Service.objects.using(UMBRELLA).filter(app=app)

    for weblet in service_list:
        db = weblet.database
        add_database(db)
        print "Weblet %s\n" % weblet.project_name
        try:
            share_rate = DarajaConfig.objects.using(db).get(service=weblet).referrer_share_rate
            # Recover all dara of a given service]
            # And check whether each of them has the same member_id in ikwen_umbrella db
            for dara_weblet in Dara.objects.using(db).all():
                member_weblet = dara_weblet.member
                try:
                    Member.objects.using(UMBRELLA).get(pk=member_weblet.pk)
                    dara_umbrella = Dara.objects.using(UMBRELLA).get(member=member_weblet)
                    print "Member %s exist in UMBRELLA\n" % member_weblet.full_name
                    print "Dara's %s uname is %s and Dara's umbrella uname is %s \n\n\n" % \
                          (weblet.project_name, dara_weblet.uname, dara_umbrella.uname)
                    dara_weblet.uname = dara_umbrella.uname
                except:
                    daraja_app = Application.objects.using(UMBRELLA).get(slug='daraja')
                    print "Member %s doesn't exist in UMBRELLA\n" % member_weblet.full_name
                    try:
                        member_umbrella = Member.objects.using(UMBRELLA).get(email=member_weblet.email)
                        service_dara = Service.objects.using(UMBRELLA).get(app=daraja_app, member=member_umbrella)
                        _sync_member(member_umbrella, member_weblet, weblet, service_dara)
                        uname = slugify(member_weblet.username.split('@')[0]).replace('-', '')
                        dara_weblet.uname = uname
                    except:
                        print "Member %s can't be recovered" % member_weblet.email
                        pass
                print "New uname of this %s Dara %s is %s" % \
                      (weblet.project_name, dara_weblet.member.full_name, dara_weblet.uname)
                dara_weblet.share_rate = share_rate
                dara_weblet.save(using=db)
        except:
            pass


if __name__ == '__main__':
    try:
        DEBUG = sys.argv[1] == 'debug'
    except IndexError:
        DEBUG = False
    if DEBUG:
        synchronize()
    else:
        try:
            synchronize()
        except:
            logger.error(u"Fatal error occured", exc_info=True)
