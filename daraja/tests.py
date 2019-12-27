import json
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

from ikwen.core.models import OperatorWallet
from ikwen.core.utils import add_database
from ikwen.billing.models import MoMoTransaction
from ikwen.accesscontrol.models import Member
from ikwen.accesscontrol.backends import UMBRELLA

from echo.models import Balance
from daraja.models import DaraRequest


def wipe_test_data(db=None):
    """
    This test was originally built with django-nonrel 1.6 which had an error when flushing the database after
    each test. So the flush is performed manually with this custom tearDown()
    """
    import permission_backend_nonrel.models
    import ikwen.core.models
    import ikwen.accesscontrol.models
    import daraja.models
    OperatorWallet.objects.using('wallets').all().delete()
    MoMoTransaction.objects.using('wallets').all().delete()
    Balance.objects.using('wallets').all().delete()
    if db:
        aliases = [db]
        add_database(db)
    else:
        aliases = getattr(settings, 'DATABASES').keys()
    for alias in aliases:
        if alias == 'wallets':
            continue
        if not alias.startswith('test_'):
            continue
        Group.objects.using(alias).all().delete()
        for name in ('UserPermissionList',):
            model = getattr(permission_backend_nonrel.models, name)
            model.objects.using(db).all().delete()
        for name in ('Member',):
            model = getattr(ikwen.accesscontrol.models, name)
            model.objects.using(db).all().delete()
        for name in ('Application', 'Service', 'Config', 'ConsoleEventType', 'ConsoleEvent', 'Country', ):
            model = getattr(ikwen.core.models, name)
            model.objects.using(alias).all().delete()
        for name in ('DarajaConfig', 'DaraRequest', 'Dara', 'Invitation', ):
            model = getattr(daraja.models, name)
            model.objects.using(alias).all().delete()


class DarajaViewsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['ikwen_members.yaml', 'setup_data.yaml', 'drj_setup_data.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            call_command('loaddata', fixture)
            call_command('loaddata', fixture, database=UMBRELLA)

    def tearDown(self):
        wipe_test_data()
        wipe_test_data('test_ikwen_service_2')
        OperatorWallet.objects.using('wallets').all().update(balance=0)
        cache.clear()

    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True)
    # def test_Home(self):
    #     """
    #     Home page must be reachable.
    #     """
    #     response = self.client.get(reverse('daraja:home'))
    #     self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101')
    def test_RegisteredCompanyList(self):
        """
        The list of companies registered to the Daraja program
        Page must return HTTP 200 status.
        """
        response = self.client.get(reverse('daraja:registered_company_list'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101')
    def test_RegisteredCompanyList_request_with_anonymous_user(self):
        """
        Request to become Dara of a company fails if anonymous user
        """
        response = self.client.get(reverse('daraja:registered_company_list'),
                                   {'action': 'apply', 'service_id': '56eb6d04b37b3379b531b102'})
        self.assertEqual(response.status_code, 200)
        json_resp = json.loads(response.content)
        self.assertEqual(json_resp['error'], 'anonymous_user')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', DEBUG=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/daraja/', UNIT_TESTING=True)
    def test_RegisteredCompanyList_request(self):
        """
        Request to become Dara of a company. Must create a DaraRequest in umbrella DB
        """
        db = 'test_ikwen_service_2'
        call_command('loaddata', 'setup_data.yaml', database=db)
        self.client.login(username='armelsikati', password='admin')
        response = self.client.get(reverse('daraja:registered_company_list'),
                                   {'action': 'apply', 'service_id': '56eb6d04b37b3379b531b102'})
        self.assertEqual(response.status_code, 200)
        json_resp = json.loads(response.content)
        self.assertTrue(json_resp['success'])
        DaraRequest.objects.using(db).get(service='56eb6d04b37b3379b531b102', member='56eb6d04b37b3379b531e014')  # Test if exists

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True)
    def test_Deploy_with_get_access_and_email_not_verified(self):
        """
        Deploy page must be reachable when user access through GET
        """
        self.client.login(username='member4', password='admin')
        response = self.client.get(reverse('daraja:deploy_cloud'))
        self.assertEqual(response.status_code, 302)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True)
    def test_Deploy_with_get_access_and_email_verified(self):
        """
        Deploy page must be reachable when user access through GET
        """
        Member.objects.using(UMBRELLA).filter(username='member4').update(email_verified=True)
        self.client.login(username='member4', password='admin')
        response = self.client.get(reverse('daraja:deploy_cloud'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True)
    def test_Deploy_with_post_request(self):
        """
        POST request to Deploy page should actually Deploy platform for the Dara
        """
        Member.objects.using(UMBRELLA).filter(username='member4').update(email_verified=True)
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('daraja:deploy_cloud'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101')
    def test_CompanyList(self):
        """
        The list of companies the Dara is actually working with. This page
        is accessible from within his account.
        Page must return HTTP 200 status.
        """
        Member.objects.using(UMBRELLA).filter(username='armelsikati').update(email_verified=True)
        self.client.login(username='armelsikati', password='admin')
        response = self.client.get(reverse('daraja:company_list'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101')
    def test_Dashboard(self):
        """
        Page must return HTTP 200 status.
        """
        Member.objects.using(UMBRELLA).filter(username='armelsikati').update(email_verified=True)
        self.client.login(username='armelsikati', password='admin')
        response = self.client.get(reverse('daraja:dashboard'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101')
    def test_ChangeProfile(self):
        """
        Profile page of a Dara. Page must return HTTP 200 status.
        """
        Member.objects.using(UMBRELLA).filter(username='armelsikati').update(email_verified=True)
        self.client.login(username='armelsikati', password='admin')
        response = self.client.get(reverse('daraja:change_profile'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101')
    def test_ViewProfile(self):
        """
        Profile page of a Dara. Page must return HTTP 200 status.
        """
        Member.objects.using(UMBRELLA).filter(username='member4').update(email_verified=True)
        self.client.login(username='member4', password='admin')
        ikwen_name = 'armelsikati'
        response = self.client.get(reverse('daraja:view_profile', args=(ikwen_name, )))
        self.assertEqual(response.status_code, 200)

    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101',
    #                    EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
    #                    EMAIL_FILE_PATH='test_emails/daraja/')
    # def test_ViewProfile_accept_application(self):
    #     """
    #     Accepting Dara request from the view profile page adds the Dara to the Weblet Dara list
    #     """
    #     Member.objects.using(UMBRELLA).filter(username='member4').update(email_verified=True)
    #     self.client.login(username='member4', password='admin')
    #     ikwen_name = 'armelsikati'
    #     url = reverse('daraja:view_profile', args=(ikwen_name, )
    #     response = self.client.get(reverse('daraja:view_profile', args=(ikwen_name, )))
    #     self.assertEqual(response.status_code, 200)
