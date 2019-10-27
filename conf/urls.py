from django.conf.urls import patterns, include, url
from django.contrib.auth.decorators import login_required

from django.contrib import admin
admin.autodiscover()

from daraja.views import Home

urlpatterns = patterns(
    '',

    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^$', Home.as_view(), name='home'),
    url(r'^laakam/', include(admin.site.urls)),
    url(r'^billing/', include('ikwen.billing.urls', namespace='billing')),
    url(r'^theming/', include('ikwen.theming.urls', namespace='theming')),
    url(r'^theming/', include('ikwen.theming.urls', namespace='theming')),
    url(r'^kakocase/', include('ikwen_kakocase.kakocase.urls', namespace='kakocase')),
    url(r'^kako/', include('ikwen_kakocase.kako.urls', namespace='kako')),
    url(r'^rewarding/', include('ikwen.rewarding.urls', namespace='rewarding')),
    url(r'^webnode/', include('ikwen_webnode.webnode.urls', namespace='webnode')),
    url(r'^rewarding/', include('ikwen.rewarding.urls', namespace='rewarding')),

    # Daraja URLs
    url(r'^daraja/', include('daraja.urls', namespace='daraja')),

    url(r'^', include('ikwen.core.urls', namespace='ikwen')),
    # url(r'^page/(?P<url>[-\w]+)/$', FlatPageView.as_view(), name='flatpage'),
)
