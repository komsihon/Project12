#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import logging
from datetime import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ikwen.conf.settings")

from django.core import mail
from daraja.models import BonusWallet

logger = logging.getLogger('ikwen.crons')


DEBUG = False


def reset_bonus_wallets():
    """
    Sets the BonusWallet.cash to 0 when the last
    time top up was more than 2 weeks ago.
    """
    now = datetime.now()
    connection = mail.get_connection()
    try:
        connection.open()
    except:
        logger.error(u"Connexion error", exc_info=True)

    queryset = BonusWallet.objects.using('wallets').filter(cash__gt=0)
    total = queryset.count()
    chunks = total / 500 + 1
    for i in range(chunks):
        start = i * 500
        finish = (i + 1) * 500
        for bonus_wallet in queryset[start:finish]:
            diff = now - bonus_wallet.top_up_on
            if diff.days >= BonusWallet.VALIDITY:
                bonus_wallet.cash = 0
                bonus_wallet.save()
            if diff.days >= (BonusWallet.VALIDITY / 2) or diff.days == 3 or diff.days == 1:
                # Notify that you have diff.days left to use your bonus
                pass

    try:
        connection.close()
    except:
        pass


if __name__ == "__main__":
    try:
        try:
            DEBUG = sys.argv[1] == 'debug'
        except IndexError:
            DEBUG = False
        reset_bonus_wallets()
    except:
        logger.error(u"Fatal error occured", exc_info=True)
