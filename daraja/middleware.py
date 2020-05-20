# -*- coding: utf-8 -*-
from datetime import datetime, timedelta


class SetDaraMiddleware(object):
    """
    Sets the Dara referrer in session
    """

    def process_response(self, request, response):
        referrer = request.GET.get('referrer')
        if referrer:
            expires = datetime.now() + timedelta(days=30)
            response.set_cookie('referrer', referrer, expires=expires)
        return response
