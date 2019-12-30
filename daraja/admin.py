from django.contrib import admin
from django.utils.translation import gettext_lazy as _


class DaraAdmin(admin.ModelAdmin):
    fields = ('facebook_link', 'instagram_link', 'youtube_link', 'twitter_link', 'linkedin_link', 'description', )
    fieldsets = (
        (_('Your social media'), {'fields': ('facebook_link', 'instagram_link', 'youtube_link',
                                             'twitter_link', 'linkedin_link')}),
        (_('Market yourself'), {'fields': ('description', )}),
    )


class DarajaConfigAdmin(admin.ModelAdmin):
    fields = ('referrer_share_rate', 'invitation_is_unique', 'location', 'avg_purchase', 'products', 'strategy', 'daily_sales')
    fieldsets = (
        (None, {'fields': ('referrer_share_rate', 'invitation_is_unique', )}),
        (_('General'), {'fields': ('avg_purchase', 'location')}),
        (_('How to make money with you ?'), {'fields': ('products', 'strategy', 'daily_sales')}),
    )
