from django.conf.urls import patterns, include, url

from django.contrib import admin

from ikwen.core.views import Offline
from ikwen.accesscontrol.views import SignIn
from daraja.views import Dashboard
# from website.views import About

admin.autodiscover()

urlpatterns = patterns(
    '',
    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^offline.html$', Offline.as_view(), name='offline'),

    # URLs to make library internals to work properly
    url(r'^$', SignIn.as_view(), name='home'),
    url(r'^daraja/dashboard/$', Dashboard.as_view(), name='admin_home'),
    url(r'^daraja/dashboard/$', Dashboard.as_view(), name='sudo_home'),

    url(r'^laakam/', include(admin.site.urls)),
    url(r'^billing/', include('ikwen.billing.urls', namespace='billing')),
    url(r'^theming/', include('ikwen.theming.urls', namespace='theming')),
    url(r'^kakocase/', include('ikwen_kakocase.kakocase.urls', namespace='kakocase')),
    url(r'^kako/', include('ikwen_kakocase.kako.urls', namespace='kako')),
    url(r'^rewarding/', include('ikwen.rewarding.urls', namespace='rewarding')),
    url(r'^webnode/', include('ikwen_webnode.webnode.urls', namespace='webnode')),
    url(r'^rewarding/', include('ikwen.rewarding.urls', namespace='rewarding')),
    # url(r'^about/', About.as_view(), name='about'),

    # Daraja URLs
    url(r'^daraja/', include('daraja.urls', namespace='daraja')),

    url(r'^', include('ikwen.core.urls', namespace='ikwen')),
)
