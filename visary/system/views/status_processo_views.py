"""
Views relacionadas a status de processos.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from consultancy.forms import StatusProcessoForm
from consultancy.models import StatusProcesso
from system.views.client_views import obter_consultor_usuario, usuario_pode_gerenciar_todos


@login_required
def listar_status_processo(request):
    """Lista todos os status de processos."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    # Apenas administradores podem gerenciar status
    if not pode_gerenciar_todos:
        raise PermissionDenied("Você não tem permissão para gerenciar status de processos.")

    status_list = StatusProcesso.objects.select_related(
        "tipo_visto", "tipo_visto__pais_destino"
    ).order_by("ordem", "nome")

    contexto = {
        "status_list": status_list,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }

    return render(request, "process/listar_status_processo.html", contexto)


@login_required
def criar_status_processo(request):
    """Formulário para cadastrar novo status de processo."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    # Apenas administradores podem criar status
    if not pode_gerenciar_todos:
        raise PermissionDenied("Você não tem permissão para criar status de processos.")

    if request.method == "POST":
        form = StatusProcessoForm(data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Status cadastrado com sucesso.")
            return redirect("system:listar_status_processo")
        messages.error(request, "Não foi possível cadastrar o status. Verifique os campos.")
    else:
        form = StatusProcessoForm()

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "process/criar_status_processo.html", contexto)


@login_required
def editar_status_processo(request, pk: int):
    """Formulário para editar status de processo existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    # Apenas administradores podem editar status
    if not pode_gerenciar_todos:
        raise PermissionDenied("Você não tem permissão para editar status de processos.")

    status = get_object_or_404(StatusProcesso, pk=pk)

    if request.method == "POST":
        form = StatusProcessoForm(data=request.POST, instance=status)
        if form.is_valid():
            form.save()
            messages.success(request, "Status atualizado com sucesso.")
            return redirect("system:listar_status_processo")
        messages.error(request, "Não foi possível atualizar o status. Verifique os campos.")
    else:
        form = StatusProcessoForm(instance=status)

    contexto = {
        "form": form,
        "status": status,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "process/editar_status_processo.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_status_processo(request, pk: int):
    """Exclui um status de processo."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    # Apenas administradores podem excluir status
    if not pode_gerenciar_todos:
        raise PermissionDenied("Você não tem permissão para excluir status de processos.")

    status = get_object_or_404(StatusProcesso, pk=pk)

    # Verificar se há processos usando este status
    if status.processos.exists():
        messages.error(
            request,
            f"Não é possível excluir o status '{status.nome}' pois existem processos vinculados a ele.",
        )
        return redirect("system:listar_status_processo")

    nome_status = status.nome
    status.delete()

    messages.success(request, f"Status '{nome_status}' excluído com sucesso.")
    return redirect("system:listar_status_processo")

