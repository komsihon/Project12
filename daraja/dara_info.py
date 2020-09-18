import sys
import os
import logging
import csv
# import pyexcel
from datetime import datetime

reload(sys)
sys.setdefaultencoding('utf8')

from smartevent.models import Participant

os.environ.setdefault("DJANGO_SETTINGS_MODULE", 'ikwen.conf.settings')

from django.core.mail import EmailMessage
from django.utils.translation import ugettext as _, activate

from ikwen.core.models import Application, Service
from ikwen.core.utils import add_database, send_push
from ikwen.core.log import CRONS_LOGGING
from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_mail_content

from daraja.models import Dara


logging.config.dictConfig(CRONS_LOGGING)
logger = logging.getLogger('ikwen.crons')


DEBUG = False


def render_dara_info():
    # app = Application.objects.get(slug='daraja')
    # service = Service.objects.get(app=app)
    out_put_file = open('dara_list.csv', 'w')
    data = [['First Name', 'Last Name', 'Email', 'Phone', 'Birthday', 'Date of join']]

    for dara in Dara.objects.all():
        member = dara.member
        data.append([member.first_name, member.last_name, member.email, member.phone, member.birthday,
                     dara.created_on.ctime()])
    writer = csv.writer(out_put_file, delimiter=';', quotechar='"')
    writer.writerows(data)
    out_put_file.close()

    out_put_file2 = open('conference_participants.csv', 'w')
    data = [['First Name', 'Last Name', 'Email', 'Phone', 'Opinion', 'Occupation']]
    for participant in Participant.objects.all():
        data.append([participant.first_name, participant.last_name, participant.email,
                     participant.phone, participant.opinion, participant.occupation])
    writer = csv.writer(out_put_file2, delimiter=';', quotechar='"')
    writer.writerows(data)
    out_put_file2.close()


if __name__ == '__main__':
    try:
        DEBUG = sys.argv[1] == 'debug'
    except IndexError:
        DEBUG = False
    if DEBUG:
        render_dara_info()
    else:
        try:
            render_dara_info()
        except:
            logger.error(u"Fatal error occured", exc_info=True)


