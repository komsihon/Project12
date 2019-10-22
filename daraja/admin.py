from django.contrib import admin


class DaraAdmin(admin.ModelAdmin):
    fields = ('description', )


class DarajaConfigAdmin(admin.ModelAdmin):
    fields = ('description', 'annual_turnover', 'number_of_employees', 'location', 'referrer_share_rate')
