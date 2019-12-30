# -*- coding: utf-8 -*-


class SetDaraMiddleware(object):
    """
    Sets the Dara referrer in session
    """

    def process_response(self, request, response):
        referrer = request.GET.get('referrer')
        if referrer:
            response.set_cookie('referrer', referrer)
        return response
