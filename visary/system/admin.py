from django.contrib import admin

from system.models import Modulo, Perfil, UsuarioConsultoria


@admin.register(Modulo)
class ModuloAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "ordem", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome", "slug", "descricao")
    ordering = ("ordem", "nome")


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "ativo",
        "pode_criar",
        "pode_visualizar",
        "pode_atualizar",
        "pode_excluir",
        "atualizado_em",
    )
    list_filter = ("ativo", "pode_criar", "pode_visualizar", "pode_atualizar", "pode_excluir")
    search_fields = ("nome", "descricao")
    filter_horizontal = ("modulos",)
    ordering = ("nome",)


@admin.register(UsuarioConsultoria)
class UsuarioConsultoriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "email", "perfil", "ativo", "atualizado_em")
    list_filter = ("ativo", "perfil")
    search_fields = ("nome", "email")
    autocomplete_fields = ("perfil",)
    ordering = ("nome",)
    readonly_fields = ("criado_em", "atualizado_em")
