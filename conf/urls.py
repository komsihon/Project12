from django.conf.urls import patterns, include, url
from django.contrib.auth.decorators import login_required

from django.contrib import admin

from ikwen.accesscontrol.views import SignIn
from daraja.views import Dashboard

admin.autodiscover()

urlpatterns = patterns(
    '',
    url(r'^i18n/', include('django.conf.urls.i18n')),

    # URLs to make library internals to work properly
    url(r'^signIn/$', SignIn.as_view(), name='home'),
    url(r'^daraja/dashboard/$', login_required(Dashboard.as_view()), name='admin_home'),
    url(r'^daraja/dashboard/$', login_required(Dashboard.as_view()), name='sudo_home'),

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
)
