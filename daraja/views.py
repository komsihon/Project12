import json
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.utils.translation import gettext as _

from permission_backend_nonrel.models import UserPermissionList

from ikwen.core.constants import PENDING, REJECTED
from ikwen.core.views import HybridListView, DashboardBase, ChangeObjectBase
from ikwen.core.models import Service, Application
from ikwen.core.utils import slice_watch_objects, rank_watch_objects, add_database, set_counters, get_service_instance, \
    get_model_admin_instance, clear_counters
from ikwen.accesscontrol.utils import VerifiedEmailTemplateView
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member

from ikwen_kakocase.shopping.models import Customer

from daraja.models import DaraRequest, Dara, DarajaConfig, DARAJA
from daraja.admin import DaraAdmin, DarajaConfigAdmin
from daraja.cloud_setup import deploy


class Home(TemplateView):
    template_name = 'daraja/home.html'


class HomeForBusinesses(TemplateView):
    template_name = 'daraja/home_for_businesses.html'


class RegisteredCompanyList(HybridListView):
    """
    Companies registered to ikwen Daraja program
    """
    template_name = 'daraja/registered_company_list.html'
    queryset = DarajaConfig.objects.select_related('service').filter(referrer_share_rate__gt=0, is_active=True)

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'apply':
            return self.apply(request)
        return super(RegisteredCompanyList, self).get(request, *args, **kwargs)

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
            dara_request = DaraRequest.objects.using(db).get(service=service, member=request.user)
            diff = now - dara_request.created_on
            if dara_request.status == REJECTED and diff.days > 30:  # If previous request is older than 30 days, allow to request again
                dara_request.delete()
                raise DaraRequest.DoesNotExist()
        except DaraRequest.DoesNotExist:
            DaraRequest.objects.using(db).create(service=service, member=request.user)
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
        return get_object_or_404(Service, app=app, member=self.request.user)

    def get_context_data(self, **kwargs):
        context = super(Dashboard, self).get_context_data(**kwargs)
        service = self.get_service(**kwargs)
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
        company_list = list(Service.objects.using(db).all())
        for company in company_list:
            set_counters(company)
        companies_report = {
            'today': rank_watch_objects(company_list, 'earnings_history'),
            'yesterday': rank_watch_objects(company_list, 'earnings_history', 1),
            'last_week': rank_watch_objects(company_list, 'earnings_history', 7),
            'last_28_days': rank_watch_objects(company_list, 'earnings_history', 28)
        }
        context['companies_report'] = companies_report
        return context


class CompanyList(HybridListView):
    template_name = 'daraja/company_list.html'
    html_results_template_name = 'daraja/snippets/company_list_results.html'
    # queryset = Service.objects.exclude(pk=getattr(settings, 'IKWEN_SERVICE_ID'))
    model = Service

    def get_context_data(self, **kwargs):
        app = Application.objects.get(slug=DARAJA)
        dara_service = get_object_or_404(Service, app=app, member=self.request.user)
        db = dara_service.database
        add_database(db)
        context = super(CompanyList, self).get_context_data(**kwargs)
        queryset = Service.objects.using(db).exclude(pk=dara_service.id)
        context_object_name = self.get_context_object_name(self.object_list)
        context[context_object_name] = queryset.order_by(*self.ordering)[:self.page_size]
        context['queryset'] = queryset
        return context


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
        context['dara'] = get_object_or_404(Dara, uname=dara_name)
        return context


class Configuration(ChangeObjectBase):
    template_name = 'daraja/configuration.html'
    model = DarajaConfig
    model_admin = DarajaConfigAdmin

    def get_object(self, **kwargs):
        service = get_service_instance()
        daraja_config, update = DarajaConfig.objects.get_or_create(service=service)
        return daraja_config

    def after_save(self, request, obj, *args, **kwargs):
        obj = self.get_object()
        obj.save(using=UMBRELLA)


class InviteDara(TemplateView):
    template_name = 'daraja/invite_dara.html'
    model = Dara

    def get_context_data(self, **kwargs):
        context = super(InviteDara, self).get_context_data(**kwargs)
        ikwen_name = kwargs['ikwen_name']
        member = self.request.user
        company = get_object_or_404(Service, project_name_slug=ikwen_name)
        company_db = company.database
        add_database(company_db)
        try:
            Dara.objects.using(company_db).get_or_create(member=member)
            context['invitation_already_accepted'] = True
        except Dara.DoesNotExist:
            pass
        daraja_config = DarajaConfig.objects.get(service=company)
        context['company'] = company
        context['company_name'] = company.project_name
        context['share_rate'] = daraja_config.referrer_share_rate
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
            dara_service = Service.objects.get(app=app, member=member)
        except Service.DoesNotExist:
            response = {'error': "not_yet_dara"}
            return HttpResponse(json.dumps(response), 'content-type: text/json')
        company_db = company.database
        add_database(company_db)
        member.save(using=company_db)
        try:
            member_local = Member.objects.using(company_db).get(pk=member.id)
        except Member.DoesNotExist:
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
        response = {'success': True}
        return HttpResponse(json.dumps(response), 'content-type: text/json')


class DaraRequestList(HybridListView):
    template_name = 'daraja/dara_request_list.html'
    queryset = DaraRequest.objects.using(UMBRELLA).filter(service=getattr(settings, 'IKWEN_SERVICE_ID'), status=PENDING)

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'accept':
            return self.accept_application(request)
        elif action == 'reject':
            return self.reject_application(request)
        return super(DaraRequestList, self).get(request, *args, **kwargs)

    def accept_application(self, request):
        dara_request = DaraRequest.objects.using(UMBRELLA).get(pk=request.GET['request_id'])
        member = dara_request.member
        try:
            member_local = Member.objects.get(pk=member.id)
        except Member.DoesNotExist:
            member.save(using='default')
            member_local = Member.objects.get(pk=member.id)
            UserPermissionList.objects.get_or_create(user=member_local)

        Dara.objects.get_or_create(member=member_local)
        dara_request.status = ACCEPTED
        dara_request.save()
        app = Application.objects.get(slug=DARAJA)
        dara_service = Service.objects.using(UMBRELLA).get(app=app, member=member)
        dara_service.save(using='default')
        db = dara_service.database
        add_database(db)
        service = get_service_instance()
        service.save(using=db)
        service_mirror = Service.objects.using(db).get(pk=service.id)
        clear_counters(service_mirror)
        response = {'success': True}
        return HttpResponse(json.dumps(response), 'content-type: text/json')

    def reject_application(self, request):
        dara_request = DaraRequest.objects.using(UMBRELLA).get(pk=request.GET['request_id'])
        dara_request.status = REJECTED
        dara_request.save()
        response = {'success': True}
        return HttpResponse(json.dumps(response), 'content-type: text/json')


class DaraList(HybridListView):
    template_name = 'daraja/dara_list.html'
    html_results_template_name = 'daraja/snippets/dara_list_results.html'
    model = Dara

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'remove':
            return self.remove_dara(request)
        return super(DaraList, self).get(request, *args, **kwargs)

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

    def post(self, request, *args, **kwargs):
        member = request.user
        app = Application.objects.get(slug=DARAJA)
        inviter = request.GET.get('inviter')
        try:
            Service.objects.get(app=app, member=member)
        except:
            pass
        else:
            next_url = 'http://daraja.ikwen.com' + reverse('daraja:login_router')
            return HttpResponseRedirect(next_url)
        if getattr(settings, 'DEBUG', False):
            service = deploy(member)
        else:
            try:
                service = deploy(member)
            except Exception as e:
                logger.error("Daraja deployment failed for %s" % project_name, exc_info=True)
                context = self.get_context_data(**kwargs)
                context['errors'] = e.message
                return render(request, 'daraja/cloud_setup/deploy.html', context)
        next_url = reverse('daraja:successful_deployment', args=(service.ikwen_name,))
        if inviter:
            next_url += '?inviter=' + inviter
        return HttpResponseRedirect(next_url)


class SuccessfulDeployment(VerifiedEmailTemplateView):
    template_name = 'daraja/cloud_setup/successful_deployment.html'

    def get_context_data(self, **kwargs):
        context = super(SuccessfulDeployment, self).get_context_data(**kwargs)
        app = Application.objects.get(slug=DARAJA)
        context['dara_service'] = get_object_or_404(Service, app=app, member=self.request.user)
        context['inviter'] = self.request.GET.get('inviter')
        return context
