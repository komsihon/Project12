import json
import logging
from datetime import datetime
from threading import Thread

from django.conf import settings
from django.contrib.auth import logout, authenticate, login
from django.core.mail import EmailMessage
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.contrib import messages
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import slugify
from django.utils.http import urlunquote
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.utils.translation import gettext as _

from permission_backend_nonrel.models import UserPermissionList

from ikwen.core.constants import PENDING, REJECTED, ACCEPTED
from ikwen.core.views import HybridListView, DashboardBase, ChangeObjectBase
from ikwen.core.models import Service, Application, Config
from ikwen.core.utils import slice_watch_objects, rank_watch_objects, add_database, set_counters, get_service_instance, \
    get_model_admin_instance, clear_counters, get_mail_content, XEmailMessage
from ikwen.accesscontrol.utils import VerifiedEmailTemplateView
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member

from ikwen_kakocase.shopping.models import Customer

from daraja.models import DaraRequest, Dara, DarajaConfig, DARAJA, Invitation
from daraja.admin import DaraAdmin, DarajaConfigAdmin
from daraja.cloud_setup import deploy

logger = logging.getLogger('ikwen')

if getattr(settings, 'DEBUG', False):
    _umbrella_db = 'ikwen_umbrella'
else:
    _umbrella_db = 'ikwen_umbrella_prod'


def _get_member(username, email, phone, using):
    try:
        member = Member.objects.using(using).get(username=username)
        return member
    except:
        try:
            member = Member.objects.using(using).get(email=email)
            return member
        except:
            try:
                member = Member.objects.using(using).get(phone=phone)
                return member
            except:
                pass


class Home(TemplateView):
    template_name = 'daraja/home.html'


class HomeForBusinesses(TemplateView):
    template_name = 'daraja/home_for_businesses.html'


class HomePlayground(TemplateView):
    template_name = 'daraja/home_playground.html'


def not_yet_dara(request, *args, **kwargs):
    return render(request, 'daraja/not_yet_dara.html')


class RegisteredCompanyList(HybridListView):
    """
    Companies registered to ikwen Daraja program
    """
    template_name = 'daraja/registered_company_list.html'
    try:
        playground = Service.objects.get(project_name_slug='playground')
        queryset = DarajaConfig.objects.select_related('service').exclude(service=playground)\
            .filter(referrer_share_rate__gt=0, is_active=True)
    except Service.DoesNotExist:
        queryset = DarajaConfig.objects.select_related('service').filter(referrer_share_rate__gt=0, is_active=True)

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'apply':
            return self.apply(request)
        return super(RegisteredCompanyList, self).get(request, *args, **kwargs)

    def get_search_results(self, queryset, max_chars=None):
        search_term = self.request.GET.get('q')
        if search_term and len(search_term) >= 2:
            search_term = search_term.lower()
            word = slugify(search_term).replace('-', ' ')
            try:
                word = word[:int(max_chars)]
            except:
                pass
            service_list = list(Service.objects.filter(project_name__icontains=word)[:50])
            if word:
                queryset = queryset.filter(service__in=service_list)
        return queryset

    def apply(self, request):
        if request.user.is_anonymous():
            response = {'error': 'anonymous_user'}
            return HttpResponse(json.dumps(response), 'content-type: text/json')
        try:
            app = Application.objects.get(slug=DARAJA)
            Service.objects.get(member=request.user, app=app)
        except Service.DoesNotExist:
            response = {'error': 'not_yet_dara'}
            return HttpResponse(json.dumps(response), 'content-type: text/json')
        now = datetime.now()
        service = Service.objects.get(pk=request.GET['service_id'])
        db = service.database
        add_database(db)

        try:
            Dara.objects.using(db).get(member=request.user)
            return HttpResponse(json.dumps({'success': True}), 'content-type: text/json')
        except Dara.DoesNotExist:
            pass

        try:
            dara_request = DaraRequest.objects.using(db).get(service=service, member=request.user)
            diff = now - dara_request.created_on
            if dara_request.status == REJECTED and diff.days > 30:  # If previous request is older than 30 days, allow to request again
                dara_request.delete()
                raise DaraRequest.DoesNotExist()
        except DaraRequest.DoesNotExist:
            member = request.user
            member.save(using=db)
            service = Service.objects.using(db).get(pk=request.GET['service_id'])
            dara_request = DaraRequest.objects.using(db).create(service=service, member=member)

            try:
                sender = 'ikwen Daraja <no-reply@ikwen.com>'
                member = request.user
                dara_uname = dara_request.dara.uname
                cta_url = "https://ikwen.com" + reverse('daraja:view_profile', args=(dara_uname,))\
                          + "?target=" + dara_request.service.project_name_slug
                subject = _("New Dara request")
                recipient_list = [service.config.contact_email, service.member.email]
                recipient_list = list(set(recipient_list))
                html_content = get_mail_content(subject, template_name='daraja/mails/dara_request.html',
                                                extra_context={'dara_name': member.first_name, 'member': member,
                                                               'cta_url': cta_url, 'project_name': service.project_name})
                msg = XEmailMessage(subject, html_content, sender, recipient_list)
                msg.content_subtype = "html"
                if getattr(settings, 'UNIT_TESTING', False):
                    msg.send()
                else:
                    Thread(target=lambda m: m.send(), args=(msg,)).start()
            except:
                pass

        response = {'success': True}
        return HttpResponse(json.dumps(response), 'content-type: text/json')


@login_required
def login_router(request, *args, **kwargs):
    member = request.user
    app = Application.objects.get(slug=DARAJA)
    try:
        Service.objects.get(app=app, member=member)
        next_url = reverse('daraja:dashboard')
    except Service.DoesNotExist:
        next_url = reverse('daraja:home')
    return HttpResponseRedirect(next_url)


class Dashboard(DashboardBase):
    template_name = 'daraja/dashboard.html'

    def get_service(self, **kwargs):
        app = Application.objects.get(slug=DARAJA)
        try:
            service_umbrella = Service.objects.get(app=app, member=self.request.user)
            db = service_umbrella.database
            add_database(db)
            return Service.objects.using(db).get(pk=service_umbrella.id)
        except Service.DoesNotExist:
            pass

    def get_context_data(self, **kwargs):
        service = self.get_service(**kwargs)
        if not service:
            context = {'not_yet_dara': True}
            return context
        context = super(Dashboard, self).get_context_data(**kwargs)
        db = service.database
        add_database(db)
        customer_list = slice_watch_objects(Customer, 28, using=db)
        customers_report = {
            'today': rank_watch_objects(customer_list, 'turnover_history'),
            'yesterday': rank_watch_objects(customer_list, 'turnover_history', 1),
            'last_week': rank_watch_objects(customer_list, 'turnover_history', 7),
            'last_28_days': rank_watch_objects(customer_list, 'turnover_history', 28)
        }
        context['customers_report'] = customers_report
        company_list = list(Service.objects.using(db).exclude(pk=service.id))
        for company in company_list:
            set_counters(company)
        companies_report = {
            'today': rank_watch_objects(company_list, 'earnings_history'),
            'yesterday': rank_watch_objects(company_list, 'earnings_history', 1),
            'last_week': rank_watch_objects(company_list, 'earnings_history', 7),
            'last_28_days': rank_watch_objects(company_list, 'earnings_history', 28)
        }
        context['companies_report'] = companies_report
        context['transaction_count_history'] = service.transaction_count_history[-30:]

        dara = get_object_or_404(Dara, member=service.member)
        if dara.level == 1 and dara.xp == 0:
            context['is_beginner'] = True
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        user = request.user
        if action == 'get_in':
            challenge = request.GET.get('challenge')
            try:
                app = Application.objects.get(slug=DARAJA)
                service = Service.objects.get(app=app, api_signature=challenge)
            except:
                next_url = reverse('home')
                messages.info(request, "You are not yet on Daraja.")
                return HttpResponseRedirect(next_url)
            if user.is_authenticated():
                logout(request)
            member = authenticate(service=service, api_signature=challenge)
            if member.is_authenticated():
                login(request, member)
                next_url = reverse('daraja:dashboard') + '?first_setup=yes'
            else:
                next_url = reverse('home')
            return HttpResponseRedirect(next_url)
        if user.is_anonymous():
            next_url = reverse('home')
            return HttpResponseRedirect(next_url)

        if not self.get_service():
            logout(request)
            next_url = reverse('home')
            messages.info(request, "You are not yet on Daraja.")
            return HttpResponseRedirect(next_url)
        return super(Dashboard, self).get(request, *args, **kwargs)


class CompanyList(HybridListView):
    template_name = 'daraja/company_list.html'
    html_results_template_name = 'daraja/snippets/company_list_results.html'
    model = Service
    context_object_name = 'company_list'

    def get_context_data(self, **kwargs):
        app = Application.objects.get(slug=DARAJA)
        dara_service = get_object_or_404(Service, app=app, member=self.request.user)
        db = dara_service.database
        add_database(db)
        context = super(CompanyList, self).get_context_data(**kwargs)
        queryset = Service.objects.using(db).exclude(pk=dara_service.id)
        context_object_name = self.get_context_object_name(self.object_list)
        add_database(_umbrella_db)
        company_list = []
        for service in queryset.order_by(*self.ordering):
            try:
                service.share_rate = DarajaConfig.objects.using(_umbrella_db).get(service=service).referrer_share_rate
                config = Config.objects.get(service=service)  # This has should be done this way due to database routing
                service.logo = config.logo
                service.is_standalone = config.is_standalone
            except:
                pass
            company_list.append(service)
        context[context_object_name] = company_list
        return context


class NotYetDara(TemplateView):
    """
    Page where user is redirected if user logs in to Daraja
    application without being a Dara.
    """
    template_name = 'daraja/not_yet_dara.html'


class FollowerList(HybridListView):
    template_name = 'daraja/company_list.html'
    html_results_template_name = 'daraja/snippets/company_list_results.html'
    # queryset = Service.objects.exclude(pk=getattr(settings, 'IKWEN_SERVICE_ID'))
    model = Service

    def get_context_data(self, **kwargs):
        app = Application.objects.get(slug=DARAJA)
        dara_service = get_object_or_404(Service, app=app, member=self.request.user)
        db = dara_service.database
        add_database(db)
        context = super(FollowerList, self).get_context_data(**kwargs)
        queryset = Service.objects.using(db).exclude(pk=dara_service.id)
        context_object_name = self.get_context_object_name(self.object_list)
        context[context_object_name] = queryset.order_by(*self.ordering)[:self.page_size]
        context['queryset'] = queryset
        return context


class ChangeProfile(ChangeObjectBase):
    """
    Profile page of the Dara. Run from ikwen website
    """
    template_name = 'daraja/change_profile.html'
    model = Dara
    model_admin = DaraAdmin

    def get_object(self, **kwargs):
        app = Application.objects.get(slug=DARAJA)
        dara_service = get_object_or_404(Service, app=app, member=self.request.user)
        dara, update = Dara.objects.using(UMBRELLA).get_or_create(member=self.request.user, uname=dara_service.ikwen_name)
        return dara

    def post(self, request, *args, **kwargs):
        model = self.get_model()
        model_admin = self.get_model_admin()
        object_admin = get_model_admin_instance(model, model_admin)
        obj = self.get_object(**kwargs)
        model_form = object_admin.get_form(request)
        form = model_form(request.POST, request.FILES, instance=obj)
        if form.is_valid():
            obj = form.save()
            next_url = self.get_change_object_url(request, obj, *args, **kwargs)
            messages.success(request, _('Your profile was successfully updated.'))
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)


class ViewProfile(TemplateView):
    template_name = 'daraja/view_profile.html'

    def get_context_data(self, **kwargs):
        context = super(ViewProfile, self).get_context_data(**kwargs)
        dara_name = kwargs['dara_name']
        dara = get_object_or_404(Dara, uname=dara_name)
        try:
            target_service = Service.objects.get(project_name_slug=self.request.GET['target'])
            db = target_service.database
            add_database(db)
            context['dara_request'] = DaraRequest.objects.using(db).get(member=dara.member, status=PENDING)
        except:
            pass
        context['dara'] = dara
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'accept':
            return self.accept_application(request)
        elif action == 'decline':
            return self.decline_application(request)
        return super(ViewProfile, self).get(request, *args, **kwargs)

    def accept_application(self, request):
        target_service = Service.objects.get(project_name_slug=self.request.GET['target'])
        db = target_service.database
        add_database(db)
        dara_request = DaraRequest.objects.using(db).get(pk=request.GET['request_id'])
        member = dara_request.member
        member.is_ghost = False
        UserPermissionList.objects.using(db).get_or_create(user=member)
        Dara.objects.using(db).get_or_create(member=member)
        dara_request.status = ACCEPTED
        dara_request.save()
        app = Application.objects.get(slug=DARAJA)
        dara_service = Service.objects.get(app=app, member=member)
        dara_service.save(using=db)
        dara_db = dara_service.database
        add_database(dara_db)
        target_service.save(using=dara_db)
        service_mirror = Service.objects.using(dara_db).get(pk=target_service.id)
        clear_counters(service_mirror)

        if target_service.id not in member.customer_on_fk_list:
            member.customer_on_fk_list.append(target_service.id)
        member.save(using=db)
        member.save(using=UMBRELLA)

        try:
            sender = 'ikwen Daraja <no-reply@ikwen.com>'
            member = dara_request.member
            company_name = target_service.config.company_name
            cta_url = target_service.url + '/ikwen/signIn/'
            subject = _("Your Dara request was accepted")
            html_content = get_mail_content(subject, template_name='daraja/mails/accept_dara_request.html',
                                            extra_context={'dara_name': member.first_name, 'member': member,
                                                           'company_name': company_name, 'cta_url': cta_url})
            msg = XEmailMessage(subject, html_content, sender, [member.email])
            msg.content_subtype = "html"
            Thread(target=lambda m: m.send(), args=(msg,)).start()
        except:
            pass
        response = {'success': True}
        return HttpResponse(json.dumps(response), 'content-type: text/json')

    def decline_application(self, request):
        target_service = Service.objects.get(project_name_slug=self.request.GET['target'])
        db = target_service.database
        add_database(db)
        dara_request = DaraRequest.objects.using(db).get(pk=request.GET['request_id'])
        dara_request.status = REJECTED
        dara_request.save()
        response = {'success': True}
        return HttpResponse(json.dumps(response), 'content-type: text/json')


class Configuration(ChangeObjectBase):
    template_name = 'daraja/configuration.html'
    model = DarajaConfig
    model_admin = DarajaConfigAdmin

    def get_object(self, **kwargs):
        service = get_service_instance()
        daraja_config, update = DarajaConfig.objects.get_or_create(service=service)
        return daraja_config

    def after_save(self, request, obj, *args, **kwargs):
        add_database(_umbrella_db)
        try:
            Application.objects.get(slug=DARAJA)
        except Application.DoesNotExist:
            app = Application.objects.using(_umbrella_db).get(slug=DARAJA)
            app.save(using='default')
        obj = self.get_object()
        obj.save(using=_umbrella_db)


class InviteDara(TemplateView):
    template_name = 'daraja/invite_dara.html'
    model = Dara

    def get_context_data(self, **kwargs):
        context = super(InviteDara, self).get_context_data(**kwargs)
        ikwen_name = kwargs['ikwen_name']
        invitation_id = self.request.GET.get('invitation_id')
        member = self.request.user
        company = get_object_or_404(Service, project_name_slug=ikwen_name)
        daraja_config = get_object_or_404(DarajaConfig, service=company)
        company_db = company.database
        add_database(company_db)
        invitation_already_accepted = False
        try:
            Dara.objects.using(company_db).get(member=member)
            invitation_already_accepted = True
        except:
            pass
        if not invitation_already_accepted:
            if daraja_config.invitation_is_unique:
                try:
                    invitation = Invitation.objects.using(company_db).get(pk=invitation_id, status=PENDING)
                    diff = datetime.now() - invitation.created_on
                    if diff.total_seconds() > getattr(settings, 'DARAJA_INVITATION_TIMEOUT', 30) * 60:
                        raise Http404('Invitation is expired')
                except:
                    raise Http404('Unexisting invitation')
        context['company'] = company
        context['company_name'] = company.project_name
        share_rate = daraja_config.referrer_share_rate
        context['share_rate'] = int(share_rate) if share_rate == int(share_rate) else share_rate
        context['invitation_already_accepted'] = invitation_already_accepted
        return context

    def get(self, request, *args, **kwargs):
        ikwen_name = kwargs['ikwen_name']
        action = request.GET.get('action')
        if action == 'accept':
            return self.accept_invitation(request, ikwen_name)
        return super(InviteDara, self).get(request, *args, **kwargs)

    def accept_invitation(self, request, ikwen_name):
        member = request.user
        company = get_object_or_404(Service, project_name_slug=ikwen_name)
        app = Application.objects.get(slug=DARAJA)
        if member.is_anonymous():
            response = {'error': "anonymous_user"}
            return HttpResponse(json.dumps(response), 'content-type: text/json')
        try:
            dara_service = Service.objects.using(UMBRELLA).get(app=app, member=member)
        except Service.DoesNotExist:
            response = {'error': "not_yet_dara"}
            return HttpResponse(json.dumps(response), 'content-type: text/json')
        company_db = company.database
        add_database(company_db)
        invitation_id = self.request.GET['invitation_id']
        invitation = Invitation.objects.using(company_db).get(pk=invitation_id)
        invitation.status = ACCEPTED
        invitation.save()
        # Check Member in company_db with either the same username, email or password
        username, email, phone = member.username, member.email, member.phone
        member_local = _get_member(username, email, phone, using=company_db)
        if member_local and member_local.id != member.id:
            # If found and different from the one in umbrella. Simulate deletion of the one in umbrella then replace
            # with the local one to make sure than local and umbrella Member have the same ID
            member.username = '__deleted__' + username
            member.email = '__deleted__' + email
            member.phone = '__deleted__' + phone
            member.save()
            if company.id not in member_local.customer_on_fk_list:
                member_local.customer_on_fk_list.append(company.id)
            member_local.is_staff = False
            member_local.is_superuser = False
            member_local.save(using=UMBRELLA)
            dara_service.member = member_local
            dara_service.save()
            dara = Dara.objects.using(UMBRELLA).get(member=member_local)
            dara.member = member_local
            dara.save()
            member_local = _get_member(username, email, phone, using=company_db)  # Reload local member to prevent DB routing error
            logout(request)
        else:
            if company.id not in member.customer_on_fk_list:
                member.customer_on_fk_list.append(company.id)
            member.save()
            member.save(using=company_db)
            member_local = Member.objects.using(company_db).get(pk=member.id)
            UserPermissionList.objects.using(company_db).get_or_create(user=member_local)
        dara_service.save(using=company_db)
        daraja_config = DarajaConfig.objects.get(service=company)
        dara, change = Dara.objects.using(company_db).get_or_create(member=member_local)
        dara.share_rate = daraja_config.referrer_share_rate
        dara.save()
        db = dara_service.database
        add_database(db)
        company.save(using=db)
        company_mirror = Service.objects.using(db).get(pk=company.id)
        clear_counters(company_mirror)
        response = {'success': True, 'user_id': member_local.id}
        return HttpResponse(json.dumps(response), 'content-type: text/json')


class DaraRequestList(HybridListView):
    """
    Shows the list of Dara requests sent by registered Daras
    This view is supposed to be shown in the Admin Panel of a weblet.
    """
    template_name = 'daraja/dara_request_list.html'
    queryset = DaraRequest.objects.filter(status=PENDING)

    def get_context_data(self, **kwargs):
        context = super(DaraRequestList, self).get_context_data(**kwargs)
        service = get_service_instance()
        try:
            daraja_config = DarajaConfig.objects.get(service=service)
            context['daraja_config'] = daraja_config
            context['project_name'] = service.project_name
            context['share_rate'] = int(daraja_config.referrer_share_rate)
        except:
            pass
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'accept':
            return self.accept_application(request)
        elif action == 'reject':
            return self.reject_application(request)
        return super(DaraRequestList, self).get(request, *args, **kwargs)


class DaraList(HybridListView):
    """
    Shows the list of accepted Daras on a weblet
    """
    template_name = 'daraja/dara_list.html'
    html_results_template_name = 'daraja/snippets/dara_list_results.html'
    model = Dara

    def get_context_data(self, **kwargs):
        context = super(DaraList, self).get_context_data(**kwargs)
        service = get_service_instance()
        try:
            daraja_config = DarajaConfig.objects.get(service=service)
            context['daraja_config'] = daraja_config
            context['project_name'] = service.project_name
            context['share_rate'] = int(daraja_config.referrer_share_rate)
        except:
            pass
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'generate_invitation_link':
            return self.generate_invitation_link(request)
        elif action == 'remove':
            return self.remove_dara(request)
        return super(DaraList, self).get(request, *args, **kwargs)

    def generate_invitation_link(self, request):
        invitation = Invitation.objects.create()
        service = get_service_instance()
        link = 'https://ikwen.com/daraja/invitation/%s?invitation_id=%s' % (service.project_name_slug, invitation.id)
        response = {'link': link}
        return HttpResponse(json.dumps(response), 'content-type: text/json')

    def remove_dara(self, request):
        dara_id = request.GET['dara_id']
        Dara.objects.filter(pk=dara_id).delete()
        response = {'success': True}
        return HttpResponse(json.dumps(response), 'content-type: text/json')

    def update_share_rate(self, request):
        dara_id = request.GET['dara_id']
        share_rate = request.GET['share_rate']
        Dara.objects.filter(pk=dara_id).update(share_rate=share_rate)
        response = {'success': True}
        return HttpResponse(json.dumps(response), 'content-type: text/json')


class DeployCloud(VerifiedEmailTemplateView):
    template_name = 'daraja/cloud_setup/deploy.html'

    def get_context_data(self, **kwargs):
        context = super(DeployCloud, self).get_context_data(**kwargs)
        app = Application.objects.get(slug=DARAJA)
        try:
            dara_service = Service.objects.get(app=app, member=self.request.user)
            next_url = 'http://daraja.ikwen.com/daraja/dashboard/?action=get_in&challenge=' + dara_service.api_signature
            context['next_url'] = next_url
            context['is_dara'] = True
        except:
            pass
        return context

    def post(self, request, *args, **kwargs):
        member = request.user
        app = Application.objects.get(slug=DARAJA)
        tokens = request.GET.get('tokens')
        inviter, invitation_id = None, None
        if tokens:
            tokens = tokens.split('-')
            inviter = tokens[0]
            invitation_id = tokens[1]
        try:
            Service.objects.get(app=app, member=member)
        except:
            pass
        else:
            if inviter:
                next_url = reverse('daraja:invite_dara', args=(inviter, )) + '?invitation_id=' + invitation_id
            else:
                next_url = 'http://daraja.ikwen.com' + reverse('daraja:login_router')
            return HttpResponseRedirect(next_url)
        if getattr(settings, 'DEBUG', False):
            service = deploy(member)
        else:
            try:
                service = deploy(member)
            except Exception as e:
                logger.error("Daraja deployment failed for %s" % member.username, exc_info=True)
                context = self.get_context_data(**kwargs)
                context['errors'] = e.message
                return render(request, 'daraja/cloud_setup/deploy.html', context)
        next_url = reverse('daraja:successful_deployment', args=(service.ikwen_name,))
        if inviter:
            next_url += '?inviter=' + inviter + '&invitation_id=' + invitation_id
        return HttpResponseRedirect(next_url)


class SuccessfulDeployment(VerifiedEmailTemplateView):
    template_name = 'daraja/cloud_setup/successful_deployment.html'

    def get_context_data(self, **kwargs):
        context = super(SuccessfulDeployment, self).get_context_data(**kwargs)
        app = Application.objects.get(slug=DARAJA)
        dara_service = get_object_or_404(Service, app=app, member=self.request.user)
        context['dara_service'] = dara_service
        inviter = self.request.GET.get('inviter')
        invitation_id = self.request.GET.get('invitation_id')
        if inviter:
            next_url = reverse('daraja:invite_dara', args=(inviter, )) + '?invitation_id=' + invitation_id
        else:
            next_url = 'http://daraja.ikwen.com/daraja/dashboard/?action=get_in&challenge=' + dara_service.api_signature
        context['next_url'] = next_url
        return context
