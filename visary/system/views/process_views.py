"""
Views relacionadas a processos de visto.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from consultancy.forms import ProcessoForm
from consultancy.models import Processo, StatusProcesso
from system.views.client_views import obter_consultor_usuario, usuario_pode_gerenciar_todos


@login_required
def home_processos(request):
    """Página inicial de processos com opções de navegação."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    processos = Processo.objects.select_related(
        "viagem",
        "viagem__pais_destino",
        "viagem__tipo_visto",
        "cliente",
        "assessor_responsavel",
    ).order_by("-criado_em")[:10]

    total_processos = Processo.objects.count()

    contexto = {
        "processos": processos,
        "total_processos": total_processos,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }

    return render(request, "process/home_processos.html", contexto)


@login_required
def criar_processo(request):
    """Formulário para cadastrar novo processo."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if request.method == "POST":
        form = ProcessoForm(data=request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Processo cadastrado com sucesso.")
            return redirect("system:listar_processos")
        # Exibir erros específicos do formulário
        for field, errors in form.errors.items():
            for error in errors:
                if field == "__all__":
                    messages.error(request, error)
                else:
                    field_label = form.fields[field].label if field in form.fields else field
                    messages.error(request, f"{field_label}: {error}")
    else:
        form = ProcessoForm(user=request.user)

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "process/criar_processo.html", contexto)


@login_required
def listar_processos(request):
    """Lista todos os processos."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    # Filtrar processos: admin vê todos, assessor vê apenas os seus
    if pode_gerenciar_todos:
        processos = Processo.objects.select_related(
            "viagem",
            "viagem__pais_destino",
            "viagem__tipo_visto",
            "cliente",
            "assessor_responsavel",
        ).order_by("-criado_em")
    elif consultor:
        # Assessor vê apenas seus próprios processos
        processos = Processo.objects.select_related(
            "viagem",
            "viagem__pais_destino",
            "viagem__tipo_visto",
            "cliente",
            "assessor_responsavel",
        ).filter(assessor_responsavel=consultor).order_by("-criado_em")
    else:
        processos = Processo.objects.none()

    contexto = {
        "processos": processos,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "consultor": consultor,
    }

    return render(request, "process/listar_processos.html", contexto)


@login_required
def editar_processo(request, pk: int):
    """Formulário para editar processo existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    processo = get_object_or_404(
        Processo.objects.select_related(
            "viagem",
            "viagem__pais_destino",
            "viagem__tipo_visto",
            "cliente",
            "assessor_responsavel",
        ),
        pk=pk,
    )

    # Verificar se o usuário tem permissão: admin pode editar todas, assessor apenas as suas
    if not pode_gerenciar_todos and (not consultor or processo.assessor_responsavel != consultor):
        raise PermissionDenied("Você não tem permissão para editar este processo.")

    if request.method == "POST":
        form = ProcessoForm(data=request.POST, user=request.user, instance=processo)
        if form.is_valid():
            form.save()
            messages.success(request, "Processo atualizado com sucesso.")
            return redirect("system:listar_processos")
        messages.error(request, "Não foi possível atualizar o processo. Verifique os campos.")
    else:
        form = ProcessoForm(user=request.user, instance=processo)

    contexto = {
        "form": form,
        "processo": processo,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "process/editar_processo.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_processo(request, pk: int):
    """Exclui um processo."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    processo = get_object_or_404(
        Processo.objects.select_related("assessor_responsavel", "cliente", "viagem"),
        pk=pk,
    )

    # Verificar se o usuário tem permissão: admin pode excluir todas, assessor apenas as suas
    if not pode_gerenciar_todos and (not consultor or processo.assessor_responsavel != consultor):
        raise PermissionDenied("Você não tem permissão para excluir este processo.")

    cliente_nome = processo.cliente.nome
    status_nome = processo.status.nome
    processo.delete()

    messages.success(request, f"Processo de {cliente_nome} ({status_nome}) excluído com sucesso.")
    return redirect("system:listar_processos")


@login_required
@require_GET
def api_status_processo(request):
    """API para obter os status de processo disponíveis para a viagem."""
    viagem_id = request.GET.get("viagem_id")
    
    if not viagem_id:
        return JsonResponse({"error": "ID da viagem não fornecido."}, status=400)
    
    try:
        from consultancy.models import Viagem
        viagem = Viagem.objects.select_related("tipo_visto").get(pk=viagem_id)
        # Buscar todos os status ativos (gerais e específicos)
        status_list = StatusProcesso.objects.filter(
            ativo=True
        ).order_by("ordem", "nome").values("id", "nome", "prazo_padrao_dias", "ordem")
        
        return JsonResponse(list(status_list), safe=False)
    except Viagem.DoesNotExist:
        return JsonResponse({"error": "Viagem não encontrada."}, status=404)


@login_required
@require_GET
def api_prazo_status_processo(request):
    """API para obter o prazo padrão de um status de processo."""
    status_id = request.GET.get("status_id")
    
    if not status_id:
        return JsonResponse({"error": "ID do status não fornecido."}, status=400)
    
    try:
        status = StatusProcesso.objects.get(pk=status_id, ativo=True)
        return JsonResponse({
            "prazo_padrao_dias": status.prazo_padrao_dias,
        })
    except StatusProcesso.DoesNotExist:
        return JsonResponse({"error": "Status não encontrado."}, status=404)

