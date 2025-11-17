from django.contrib import admin

from consultancy.models import ClienteConsultoria


@admin.register(ClienteConsultoria)
class ClienteConsultoriaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "email",
        "assessor_responsavel",
        "telefone",
        "criado_em",
    )
    search_fields = ("nome", "email", "telefone")
    list_filter = ("assessor_responsavel", "criado_em")
    readonly_fields = ("criado_em", "atualizado_em")
