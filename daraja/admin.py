from django.contrib import admin
from django.utils.translation import gettext_lazy as _


class DaraAdmin(admin.ModelAdmin):
    fields = ('description', )


class DarajaConfigAdmin(admin.ModelAdmin):
    fields = ('referrer_share_rate', 'location', 'avg_purchase', 'products', 'strategy', 'simulation', 'daily_sales')
    fieldsets = (
        (None, {'fields': ('referrer_share_rate', )}),
        (_('General'), {'fields': ('avg_purchase', 'location')}),
        (_('How to make money with you ?'), {'fields': ('products', 'strategy', 'simulation', 'daily_sales')}),
    )
