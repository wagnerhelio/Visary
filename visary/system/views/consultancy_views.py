from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from system.forms import ModuloForm, PerfilForm, UsuarioConsultoriaForm
from system.models import Modulo, Perfil, UsuarioConsultoria


def gerenciar_colaboradores(request):
    contexto = {
        "modulo_form": ModuloForm(prefix="modulo"),
        "perfil_form": PerfilForm(prefix="perfil"),
        "usuario_form": UsuarioConsultoriaForm(prefix="usuario"),
        "modulos": Modulo.objects.prefetch_related("perfis").order_by("ordem", "nome"),
        "perfis": Perfil.objects.prefetch_related(
            "modulos", "usuarios"
        ),
        "usuarios": UsuarioConsultoria.objects.select_related("perfil").order_by("nome"),
    }

    if request.method != "POST":
        return render(request, "system/colaboradores/gerenciar.html", contexto)

    acao = request.POST.get("action")

    formularios = {
        "modulo": ModuloForm,
        "perfil": PerfilForm,
        "usuario": UsuarioConsultoriaForm,
    }

    form_class = formularios.get(acao)

    if form_class is None:
        messages.error(request, "Ação inválida informada.")
        return redirect("system:gerenciar_colaboradores")

    prefixo = acao
    formulario = form_class(request.POST, prefix=prefixo)

    if not formulario.is_valid():
        contexto[f"{acao}_form"] = formulario
        messages.error(request, "Não foi possível salvar. Verifique os campos.")
        return render(request, "system/colaboradores/gerenciar.html", contexto)

    with transaction.atomic():
        registro = formulario.save()

    messages.success(request, f"{registro} cadastrado com sucesso.")
    return redirect("system:gerenciar_colaboradores")

