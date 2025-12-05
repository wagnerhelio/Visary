"""
Views relacionadas a processos de visto.
"""

from contextlib import suppress
from datetime import timedelta

from django.contrib import messages
from django.utils.dateparse import parse_date
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from consultancy.forms import ProcessoForm
from consultancy.models import (
    ClienteConsultoria,
    EtapaProcesso,
    Processo,
    StatusProcesso,
    Viagem,
    ViagemStatusProcesso,
)
from system.models import UsuarioConsultoria
from system.views.client_views import obter_consultor_usuario, usuario_pode_gerenciar_todos


@login_required
def home_processos(request):
    """Página inicial de processos com opções de navegação."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if pode_gerenciar_todos:
        processos = Processo.objects.select_related(
            "viagem",
            "viagem__pais_destino",
            "viagem__tipo_visto",
            "cliente",
            "assessor_responsavel",
        ).prefetch_related("etapas", "etapas__status").order_by("-criado_em")[:10]
    elif consultor:
        processos = Processo.objects.select_related(
            "viagem",
            "viagem__pais_destino",
            "viagem__tipo_visto",
            "cliente",
            "assessor_responsavel",
        ).prefetch_related("etapas", "etapas__status").filter(
            assessor_responsavel=consultor
        ).order_by("-criado_em")[:10]
    else:
        processos = Processo.objects.none()

    total_processos = Processo.objects.count() if pode_gerenciar_todos else processos.count()

    contexto = {
        "processos": processos,
        "total_processos": total_processos,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }

    return render(request, "process/home_processos.html", contexto)


def _limpar_mensagens_duplicadas_sessao(request):
    """Remove mensagens duplicadas da sessão."""
    if not (stored_messages := request.session.get('_messages')):
        return
    
    filtered = []
    seen_texts = set()
    for msg in stored_messages:
        message_text = str(msg.get('message', '') if isinstance(msg, dict) else msg)
        if message_text not in seen_texts:
            seen_texts.add(message_text)
            filtered.append(msg)
    
    if filtered:
        request.session['_messages'] = filtered
    else:
        request.session.pop('_messages', None)
    request.session.modified = True


def _limpar_mensagens_viagem_sessao(request):
    """Remove mensagens de viagem cadastrada da sessão."""
    if stored_messages := request.session.get('_messages'):
        filtered = [
            msg for msg in stored_messages 
            if "viagens cadastradas" not in str(msg.get('message', '') if isinstance(msg, dict) else msg).lower()
            and "viagem cadastrada" not in str(msg.get('message', '') if isinstance(msg, dict) else msg).lower()
        ]
        if filtered:
            request.session['_messages'] = filtered
        else:
            request.session.pop('_messages', None)
        request.session.modified = True
    
    storage = messages.get_messages(request)
    storage.used = True


def _atualizar_etapas_processo(processo: Processo, request) -> int:
    """Atualiza as etapas do processo com dados do POST. Retorna número de etapas atualizadas."""
    etapas_atualizadas = 0
    for etapa in processo.etapas.all():
        etapa_id = str(etapa.pk)
        concluida = request.POST.get(f"etapa_{etapa_id}_concluida") == "on"
        prazo_dias = request.POST.get(f"etapa_{etapa_id}_prazo", "")
        data_conclusao = request.POST.get(f"etapa_{etapa_id}_data", "") or None
        observacoes = request.POST.get(f"etapa_{etapa_id}_obs", "")

        etapa.concluida = concluida
        if prazo_dias:
            with suppress(ValueError):
                etapa.prazo_dias = int(prazo_dias)
        if data_conclusao:
            with suppress(ValueError, TypeError):
                etapa.data_conclusao = parse_date(data_conclusao)
        etapa.observacoes = observacoes
        etapa.save()
        etapas_atualizadas += 1
    return etapas_atualizadas


def _criar_etapas_se_necessario(processo: Processo):
    """Cria etapas do processo se não existirem, baseadas nos status vinculados à viagem."""
    if processo.etapas.exists():
        return
    
    status_vinculados = ViagemStatusProcesso.objects.filter(
        viagem=processo.viagem,
        ativo=True
    ).select_related('status').order_by('status__ordem', 'status__nome')

    for viagem_status in status_vinculados:
        status = viagem_status.status
        prazo_dias = max(status.prazo_padrao_dias, 0)

        EtapaProcesso.objects.get_or_create(
            processo=processo,
            status=status,
            defaults={
                'prazo_dias': prazo_dias,
                'ordem': status.ordem,
            }
        )


def _calcular_datas_finalizacao_etapas(processo: Processo, etapas):
    """Calcula datas de finalização para cada etapa baseado na data de criação do cliente."""
    data_base = processo.cliente.criado_em.date()
    etapas_com_datas = []
    for etapa in etapas:
        data_finalizacao = None
        if etapa.prazo_dias and etapa.prazo_dias > 0:
            data_finalizacao = data_base + timedelta(days=etapa.prazo_dias)

        etapas_com_datas.append({
            'etapa': etapa,
            'data_finalizacao': data_finalizacao,
        })
    return etapas_com_datas


def _obter_proximo_membro_sem_processo(cliente: ClienteConsultoria, viagem_atual: Viagem) -> dict | None:
    """
    Verifica se há membros (dependentes) com viagens separadas que ainda precisam de processo.
    
    Args:
        cliente: ClienteConsultoria que acabou de ter processo criado
        viagem_atual: Viagem do processo recém-criado
    
    Returns:
        dict com 'cliente_id' e 'viagem_id' do próximo membro que precisa de processo, ou None
    """
    # Se o cliente não é principal, não há dependentes para verificar
    if not cliente.is_principal:
        return None
    
    # Buscar dependentes do cliente principal
    dependentes = ClienteConsultoria.objects.filter(cliente_principal=cliente)
    
    # Para cada dependente, verificar se há viagem separada sem processo
    for dependente in dependentes:
        # Buscar viagens onde o dependente está sozinho (viagem separada)
        viagens_dependente = Viagem.objects.filter(
            clientes=dependente
        ).annotate(
            total_clientes=Count('clientes')
        ).filter(total_clientes=1)
        
        # Verificar se alguma dessas viagens não tem processo ainda
        for viagem_separada in viagens_dependente:
            processo_existente = Processo.objects.filter(
                viagem=viagem_separada,
                cliente=dependente
            ).exists()
            
            if not processo_existente:
                # Encontrou um membro que precisa de processo
                return {
                    'cliente_id': dependente.pk,
                    'viagem_id': viagem_separada.pk,
                }
    
    return None


@login_required
def criar_processo(request):
    """Formulário para cadastrar novo processo."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    # Limpar mensagens de viagem se vier de redirect de criar viagem
    if request.method == "GET":
        _limpar_mensagens_viagem_sessao(request)

    # Obter parâmetros de pré-seleção da URL
    cliente_id = request.GET.get("cliente_id")
    viagem_id = request.GET.get("viagem_id")

    if request.method == "POST":
        _limpar_mensagens_duplicadas_sessao(request)
        storage = messages.get_messages(request)
        storage.used = True
        
        form = ProcessoForm(request.POST, user=request.user, cliente_id=cliente_id, viagem_id=viagem_id)
        if form.is_valid():
            processo = form.save()
            
            # Verificar se há membros com viagens separadas que ainda precisam de processo
            if proximo_membro_processo := _obter_proximo_membro_sem_processo(processo.cliente, processo.viagem):
                # Não adicionar mensagem aqui, será adicionada quando o último processo for criado
                # Redirecionar para criar processo do próximo membro
                return redirect(
                    f"{reverse('system:criar_processo')}?cliente_id={proximo_membro_processo['cliente_id']}&viagem_id={proximo_membro_processo['viagem_id']}"
                )
            
            # Adicionar mensagem apenas quando não há mais processos para criar
            messages.success(request, f"Processo criado com sucesso para {processo.cliente.nome}.")
            return redirect("system:listar_processos")
        else:
            messages.error(request, "Não foi possível cadastrar o processo. Verifique os campos.")
    else:
        form = ProcessoForm(user=request.user, cliente_id=cliente_id, viagem_id=viagem_id)

    # Verificar se cliente foi pré-selecionado (explicitamente ou automaticamente)
    cliente_pre_selecionado = bool(cliente_id)
    if not cliente_pre_selecionado and viagem_id:
        # Verificar se há apenas um cliente na viagem (foi pré-selecionado automaticamente)
        with suppress(Viagem.DoesNotExist):
            viagem = Viagem.objects.get(pk=viagem_id)
            if viagem.clientes.count() == 1:
                cliente_pre_selecionado = True
    
    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "cliente_pre_selecionado": cliente_pre_selecionado,
        "viagem_pre_selecionada": bool(viagem_id),
    }

    return render(request, "process/criar_processo.html", contexto)


@login_required
def editar_processo(request, pk: int):
    """Editar um processo e suas etapas (checklist)."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    processo = get_object_or_404(
        Processo.objects.select_related(
            "viagem",
            "viagem__pais_destino",
            "viagem__tipo_visto",
            "cliente",
            "assessor_responsavel",
        ).prefetch_related("etapas", "etapas__status"),
        pk=pk
    )

    # Verificar permissão
    if not pode_gerenciar_todos and processo.assessor_responsavel != consultor:
        raise PermissionDenied("Você não tem permissão para editar este processo.")

    if request.method == "POST":
        etapas_atualizadas = _atualizar_etapas_processo(processo, request)
        if etapas_atualizadas > 0:
            messages.success(request, f"{etapas_atualizadas} etapa(s) atualizada(s).")
        return redirect("system:editar_processo", pk=processo.pk)

    # Buscar etapas do processo
    etapas = processo.etapas.select_related("status").order_by("ordem", "status__nome").all()

    # Criar etapas se necessário
    _criar_etapas_se_necessario(processo)
    
    # Recarregar etapas após possível criação
    etapas = processo.etapas.select_related("status").order_by("ordem", "status__nome").all()

    # Calcular datas de finalização para cada etapa
    etapas_com_datas = _calcular_datas_finalizacao_etapas(processo, etapas)
    data_base = processo.cliente.criado_em.date()

    contexto = {
        "processo": processo,
        "etapas_com_datas": etapas_com_datas,
        "data_base": data_base,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }

    return render(request, "process/editar_processo.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_processo(request, pk: int):
    """Excluir um processo."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied("Você não tem permissão para excluir processos.")

    processo = get_object_or_404(Processo, pk=pk)
    cliente_nome = processo.cliente.nome
    processo.delete()

    messages.success(request, f"Processo de {cliente_nome} excluído com sucesso.")
    return redirect("system:listar_processos")


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
        ).prefetch_related("etapas", "etapas__status").order_by("-criado_em")
    elif consultor:
        processos = Processo.objects.select_related(
            "viagem",
            "viagem__pais_destino",
            "viagem__tipo_visto",
            "cliente",
            "assessor_responsavel",
        ).prefetch_related("etapas", "etapas__status").filter(
            assessor_responsavel=consultor
        ).order_by("-criado_em")
    else:
        processos = Processo.objects.none()

    # Aplicar filtros se fornecidos
    filtro_cliente = request.GET.get("cliente", "")
    filtro_viagem = request.GET.get("viagem", "")
    filtro_assessor = request.GET.get("assessor", "")

    if filtro_cliente:
        processos = processos.filter(cliente__nome__icontains=filtro_cliente)
    if filtro_viagem:
        processos = processos.filter(
            Q(viagem__pais_destino__nome__icontains=filtro_viagem) |
            Q(viagem__tipo_visto__nome__icontains=filtro_viagem)
        )
    if filtro_assessor:
        processos = processos.filter(assessor_responsavel__nome__icontains=filtro_assessor)

    contexto = {
        "processos": processos,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "consultor": consultor,
        "filtro_cliente": filtro_cliente,
        "filtro_viagem": filtro_viagem,
        "filtro_assessor": filtro_assessor,
    }

    return render(request, "process/listar_processos.html", contexto)


@login_required
@require_GET
def api_status_processo(request):
    """API para obter os status (etapas) vinculados a uma viagem."""
    viagem_id = request.GET.get("viagem_id")

    if not viagem_id:
        return JsonResponse({"error": "ID da viagem não fornecido."}, status=400)

    try:
        status_vinculados = ViagemStatusProcesso.objects.filter(
            viagem_id=viagem_id,
            ativo=True
        ).select_related('status').order_by('status__ordem', 'status__nome')

        status_list = [
            {
                "id": vs.status.pk,
                "nome": vs.status.nome,
                "prazo_padrao_dias": vs.status.prazo_padrao_dias,
                "ordem": vs.status.ordem,
            }
            for vs in status_vinculados
        ]

        return JsonResponse(status_list, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_GET
def api_cliente_info(request):
    """Retorna informações complementares do cliente."""
    cliente_id = request.GET.get("cliente_id")

    if not cliente_id:
        return JsonResponse({"error": "ID do cliente não fornecido."}, status=400)

    try:
        cliente = ClienteConsultoria.objects.get(pk=cliente_id)
    except ClienteConsultoria.DoesNotExist:
        return JsonResponse({"error": "Cliente não encontrado."}, status=404)

    return JsonResponse({"criado_em": cliente.criado_em.isoformat()})


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


@login_required
@require_GET
def api_clientes_viagem(request):
    """API para obter os clientes vinculados a uma viagem."""
    viagem_id = request.GET.get("viagem_id")

    if not viagem_id:
        return JsonResponse({"error": "ID da viagem não fornecido."}, status=400)

    try:
        viagem = Viagem.objects.get(pk=viagem_id)
        clientes = viagem.clientes.all().order_by("nome")
        
        clientes_list = [
            {
                "id": cliente.pk,
                "nome": cliente.nome,
            }
            for cliente in clientes
        ]

        return JsonResponse(clientes_list, safe=False)
    except Viagem.DoesNotExist:
        return JsonResponse({"error": "Viagem não encontrada."}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
