# -*- coding: utf-8 -*-


class SetDaraMiddleware(object):
    """
    Sets the Dara referrer in session
    """

    def process_request(self, request):
        referrer = request.GET.get('referrer')
        if referrer:
            request.session['referrer'] = referrer
