from datetime import datetime

from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from djangotoolbox.fields import ListField

from ikwen.core.constants import PENDING
from ikwen.core.utils import get_service_instance, add_database
from ikwen.core.models import Model, Service, AbstractWatchModel
from ikwen.accesscontrol.models import Member
from ikwen.accesscontrol.backends import UMBRELLA


DARAJA = "daraja"
DARA_CASH = "dara-cash"
DARAJA_IKWEN_SHARE_RATE = 10
DARA_REQUESTED_ACCESS = "DaraRequestAccess"
REFEREE_JOINED_EVENT = "RefereeJoined"


class DarajaConfig(Model):
    service = models.ForeignKey(Service, unique=True, default=get_service_instance, related_name='+')
    invitation_is_unique = models.BooleanField(_("Unique invitations ?"), default=True,
                                               help_text=_("If checked, generated invitation link is usable once "
                                                           "within 30mn. Else, the link is public and can be used "
                                                           "without limitation."))
    products = models.TextField(_("Description and products"), blank=True, null=True,
                                help_text=_("Tell Daras about your business and your products are the "
                                            "most easy and profitable to sell."))
    strategy = models.TextField(_("Strategy"), blank=True, null=True,
                                help_text=_("Give Daras an idea of marketing strategy they might use including "
                                            "market to target and how to attract customers."))
    simulation = models.TextField(_("Simulation"), blank=True, null=True,
                                  help_text=_("Help Daras by giving a realistic, yet optmistic simulation of what "
                                              "they might earn in a month if they work well."))
    annual_turnover = models.IntegerField(default=0)
    number_of_employees = models.IntegerField(default=1)
    location = models.CharField(max_length=255, blank=True, null=True,
                                help_text=_("City where HQ of company is located."))
    referrer_share_rate = models.FloatField(default=0)
    is_active = models.BooleanField(default=True)
    avg_purchase = models.IntegerField(default=0,
                                       help_text=_("Average amount a customer generally buys from you. This helps the "
                                                   "Dara do a simulation of what he might earn."))
    daily_sales = models.IntegerField(default=10000, help_text=_('Estimated daily sales of a dara'))

    def __unicode__(self):
        return self.service.project_name

    def save(self, **kwargs):
        super(DarajaConfig, self).save(**kwargs)
        using = kwargs.pop('using', None)
        if using is None or using == 'default':
            super(DarajaConfig, self).save(using=UMBRELLA, **kwargs)

    def _get_share_rate_bound(self):
        if self.referrer_share_rate < 5:
            return 0
        elif self.referrer_share_rate < 10:
            return 5
        elif self.referrer_share_rate < 20:
            return 10
        return 20
    share_rate_bound = property(_get_share_rate_bound)


class DaraRequest(Model):
    service = models.ForeignKey(Service, related_name='+')
    member = models.ForeignKey(Member)
    status = models.CharField(max_length=15, default=PENDING, db_index=True)

    class Meta:
        unique_together = ('service', 'member')

    def _get_dara(self):
        if getattr(settings, 'DEBUG', False):
            _umbrella_db = 'ikwen_umbrella'
        else:
            _umbrella_db = 'ikwen_umbrella_prod'
        add_database(_umbrella_db)
        try:
            return Dara.objects.using(_umbrella_db).get(member=self.member)
        except:
            pass
    dara = property(_get_dara)


class Dara(AbstractWatchModel):
    member = models.ForeignKey(Member, unique=True)
    uname = models.CharField(max_length=100, unique=True)
    facebook_link = models.URLField(blank=True, null=True)
    instagram_link = models.URLField(blank=True, null=True)
    youtube_link = models.URLField(blank=True, null=True)
    twitter_link = models.URLField(blank=True, null=True)
    linkedin_link = models.URLField(blank=True, null=True)
    description = models.TextField(_("Say something about you"), blank=True)
    share_rate = models.FloatField(default=0)

    xp = models.IntegerField(default=0)
    level = models.IntegerField(default=1)

    orders_count_history = ListField(editable=False)
    items_traded_history = ListField(editable=False)
    turnover_history = ListField(editable=False)
    earnings_history = ListField(editable=False)

    total_orders_count = models.IntegerField(default=0)
    total_items_traded = models.IntegerField(default=0)
    total_turnover = models.IntegerField(default=0)
    total_earnings = models.IntegerField(default=0)

    last_transaction_on = models.DateTimeField(blank=True, null=True, db_index=True)

    def _get_bonus_wallet(self):
        wallet, update = BonusWallet.objects.using('wallets').get_or_create(dara_id=self.id)
        return wallet

    def _get_bonus_cash(self):
        wallet = self._get_bonus_wallet()
        return wallet.cash
    bonus_cash = property(_get_bonus_cash)

    def raise_bonus_cash(self, amount):
        wallet = self._get_bonus_wallet()
        with transaction.atomic():
            wallet.cash += amount
            wallet.top_up_on = datetime.now()
            wallet.save(using='wallets')

    def lower_bonus_cash(self, amount):
        wallet = self._get_bonus_wallet()
        if wallet.cash < amount:
            raise ValueError("Amount larger than current balance.")
        with transaction.atomic():
            wallet.cash -= amount
            wallet.save(using='wallets')


class BonusWallet(Model):
    VALIDITY = 14  # Bonus cash gets reset to 0 14 days after the last top up

    dara_id = models.CharField(max_length=24, unique=True)
    cash = models.IntegerField(default=0)
    top_up_on = models.DateTimeField(db_index=True)


class Invitation(Model):
    status = models.CharField(max_length=30, default=PENDING)


class Follower(AbstractWatchModel):
    """
    Profile information for a Buyer on whatever retail website
    """
    member = models.OneToOneField(Member)
    referrer = models.ForeignKey(Service, blank=True, null=True, related_name='+')
    last_payment_on = models.DateTimeField(blank=True, null=True, db_index=True)

    orders_count_history = ListField()
    items_purchased_history = ListField()
    turnover_history = ListField()
    earnings_history = ListField()

    total_orders_count = models.IntegerField(default=0)
    total_items_purchased = models.IntegerField(default=0)
    total_turnover = models.IntegerField(default=0)
    total_earnings = models.IntegerField(default=0)


class AbuseReport(Model):
    service = models.ForeignKey(Service, related_name='+')
    member = models.ForeignKey(Member)
    details = models.TextField()
