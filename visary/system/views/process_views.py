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
from django.http import HttpResponseRedirect, JsonResponse
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
from system.views.client_views import listar_clientes, obter_consultor_usuario, usuario_pode_gerenciar_todos


@login_required
def home_processos(request):
    """Página inicial de processos com opções de navegação."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    # Buscar clientes vinculados ao usuário (para administradores retorna todos, para assessores retorna apenas os vinculados)
    from system.views.client_views import listar_clientes
    clientes_usuario = listar_clientes(request.user)
    clientes_ids = list(clientes_usuario.values_list("pk", flat=True))
    
    # Buscar processos apenas dos clientes vinculados ao usuário
    processos = Processo.objects.filter(
        cliente__pk__in=clientes_ids
    ).select_related(
        "viagem",
        "viagem__pais_destino",
        "viagem__tipo_visto",
        "cliente",
        "assessor_responsavel",
    ).prefetch_related("etapas", "etapas__status").distinct().order_by("-criado_em")
    
    # Aplicar filtros
    filtro_cliente = request.GET.get("cliente", "").strip()
    filtro_viagem = request.GET.get("viagem", "").strip()
    filtro_assessor = request.GET.get("assessor", "").strip()
    
    if filtro_cliente:
        processos = processos.filter(cliente__nome__icontains=filtro_cliente)
    if filtro_viagem:
        processos = processos.filter(
            Q(viagem__pais_destino__nome__icontains=filtro_viagem) |
            Q(viagem__tipo_visto__nome__icontains=filtro_viagem)
        )
    if filtro_assessor:
        processos = processos.filter(assessor_responsavel__nome__icontains=filtro_assessor)
    
    # Limitar a 10 processos mais recentes (após aplicar filtros)
    processos_limitados = processos[:10]
    
    # Buscar opções para os filtros
    assessores = UsuarioConsultoria.objects.filter(ativo=True).order_by("nome")

    contexto = {
        "processos": processos_limitados,
        "total_processos": processos.count(),
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "consultor": consultor,
        "filtros_aplicados": {
            "cliente": filtro_cliente,
            "viagem": filtro_viagem,
            "assessor": filtro_assessor,
        },
        "clientes": clientes_usuario.order_by("nome"),
        "assessores": assessores,
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


def _atualizar_etapas_processo(processo: Processo, request, etapa_id: int | None = None) -> int:
    """Atualiza as etapas do processo com dados do POST. Retorna número de etapas atualizadas."""
    etapas_atualizadas = 0
    
    # Se etapa_id fornecido, atualizar apenas essa etapa
    if etapa_id:
        try:
            etapa = processo.etapas.get(pk=etapa_id)
            etapa_id_str = str(etapa.pk)
            
            # Obter valores do POST
            concluida = request.POST.get(f"etapa_{etapa_id_str}_concluida") == "on"
            prazo_dias = request.POST.get(f"etapa_{etapa_id_str}_prazo", "").strip()
            data_conclusao = request.POST.get(f"etapa_{etapa_id_str}_data", "").strip() or None
            observacoes = request.POST.get(f"etapa_{etapa_id_str}_obs", "").strip()

            # Atualizar campos
            etapa.concluida = concluida
            etapa.observacoes = observacoes or ""
            
            # Atualizar prazo_dias
            if prazo_dias:
                try:
                    etapa.prazo_dias = int(prazo_dias)
                except ValueError:
                    # Manter valor atual se conversão falhar
                    pass
            else:
                etapa.prazo_dias = 0
            
            # Atualizar data_conclusao
            if data_conclusao:
                try:
                    etapa.data_conclusao = parse_date(data_conclusao)
                except (ValueError, TypeError):
                    etapa.data_conclusao = None
            else:
                # Se desmarcou a etapa, limpar data de conclusão
                if not concluida:
                    etapa.data_conclusao = None
            
            # Salvar com campos específicos
            etapa.save(update_fields=["concluida", "prazo_dias", "data_conclusao", "observacoes", "atualizado_em"])
            
            # Recarregar do banco para garantir que foi salvo
            etapa.refresh_from_db()
            etapas_atualizadas = 1
        except EtapaProcesso.DoesNotExist:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Etapa {etapa_id} não encontrada no processo {processo.pk}")
            return 0
        except Exception as e:
            # Log do erro para debug
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erro ao atualizar etapa {etapa_id}: {e}", exc_info=True)
            return 0
    else:
        # Atualizar todas as etapas
        etapas_no_processo = list(processo.etapas.all())
        import logging
        logger = logging.getLogger(__name__)
        
        print(f"📋 Processando {len(etapas_no_processo)} etapa(s) do processo {processo.pk}", flush=True)
        
        for etapa in etapas_no_processo:
            etapa_id_str = str(etapa.pk)
            
            # Obter valores do POST
            concluida_val = request.POST.get(f"etapa_{etapa_id_str}_concluida", "")
            concluida = concluida_val == "on"
            prazo_dias_str = request.POST.get(f"etapa_{etapa_id_str}_prazo", "").strip()
            data_conclusao_str = request.POST.get(f"etapa_{etapa_id_str}_data", "").strip() or None
            observacoes = request.POST.get(f"etapa_{etapa_id_str}_obs", "").strip()
            
            # Armazenar valores antigos para comparação
            concluida_antes = etapa.concluida
            prazo_antes = etapa.prazo_dias
            data_antes = etapa.data_conclusao
            obs_antes = etapa.observacoes

            # Atualizar campos
            etapa.concluida = concluida
            etapa.observacoes = observacoes or ""
            
            # Atualizar prazo_dias - sempre processar, mesmo se vazio
            try:
                if prazo_dias_str:
                    etapa.prazo_dias = int(prazo_dias_str)
                else:
                    # Se não enviado ou vazio, manter 0
                    etapa.prazo_dias = 0
            except ValueError:
                # Manter valor atual se conversão falhar
                pass
            
            # Atualizar data_conclusao
            if data_conclusao_str:
                try:
                    etapa.data_conclusao = parse_date(data_conclusao_str)
                except (ValueError, TypeError):
                    etapa.data_conclusao = None
            else:
                # Se desmarcou a etapa, limpar data de conclusão
                if not concluida:
                    etapa.data_conclusao = None
            
            # Verificar se houve mudanças
            houve_mudanca = (
                etapa.concluida != concluida_antes or
                etapa.prazo_dias != prazo_antes or
                etapa.data_conclusao != data_antes or
                etapa.observacoes != obs_antes
            )
            
            # Sempre salvar se houve mudança ou se os campos estão presentes no POST
            campos_presentes = any([
                f"etapa_{etapa_id_str}_concluida" in request.POST,
                f"etapa_{etapa_id_str}_prazo" in request.POST,
                f"etapa_{etapa_id_str}_data" in request.POST,
                f"etapa_{etapa_id_str}_obs" in request.POST,
            ])
            
            if houve_mudanca or campos_presentes:
                try:
                    etapa.save(update_fields=["concluida", "prazo_dias", "data_conclusao", "observacoes", "atualizado_em"])
                    etapa.refresh_from_db()
                    etapas_atualizadas += 1
                    print(f"  ✅ Etapa {etapa_id_str} ({etapa.status.nome}): salva - Concluída: {concluida}, Prazo: {etapa.prazo_dias}, Data: {etapa.data_conclusao}", flush=True)
                except Exception as e:
                    print(f"  ❌ Erro ao salvar etapa {etapa_id_str}: {e}", flush=True)
                    logger.error(f"Erro ao salvar etapa {etapa_id_str}: {e}", exc_info=True)
            else:
                print(f"  ⏭️  Etapa {etapa_id_str} ({etapa.status.nome}): sem mudanças, não salva", flush=True)
    
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


def _obter_proximo_cliente_mesma_viagem(viagem: Viagem, cliente_atual: ClienteConsultoria) -> dict | None:
    """
    Verifica se há outros clientes na mesma viagem que ainda precisam de processo.
    
    Considera clientes diretamente vinculados à viagem e clientes que compartilham
    o mesmo email dos clientes na viagem.
    
    Args:
        viagem: Viagem atual
        cliente_atual: ClienteConsultoria que acabou de ter processo criado
    
    Returns:
        dict com 'cliente_id' do próximo cliente que precisa de processo na mesma viagem, ou None
    """
    clientes_na_viagem = viagem.clientes.all()
    clientes_relacionados_ids = set(clientes_na_viagem.values_list('pk', flat=True))

    for cliente_viagem in clientes_na_viagem:
        if cliente_viagem.is_principal:
            clientes_relacionados_ids.update(
                ClienteConsultoria.objects.filter(cliente_principal=cliente_viagem).values_list('pk', flat=True)
            )
        elif cliente_viagem.cliente_principal_id:
            clientes_relacionados_ids.add(cliente_viagem.cliente_principal_id)
            clientes_relacionados_ids.update(
                ClienteConsultoria.objects.filter(cliente_principal_id=cliente_viagem.cliente_principal_id).values_list('pk', flat=True)
            )
    
    # Remover o cliente atual
    clientes_relacionados_ids.discard(cliente_atual.pk)
    
    if not clientes_relacionados_ids:
        return None
    
    # Verificar quais clientes relacionados ainda não têm processo nesta viagem
    for cliente_id in clientes_relacionados_ids:
        cliente_relacionado = ClienteConsultoria.objects.get(pk=cliente_id)
        processo_existente = Processo.objects.filter(
            viagem=viagem,
            cliente=cliente_relacionado
        ).exists()
        
        if not processo_existente:
            # Encontrou um cliente relacionado que precisa de processo na mesma viagem
            return {
                'cliente_id': cliente_relacionado.pk,
                'viagem_id': viagem.pk,
            }
    
    return None


def _obter_proximo_cliente_viagem_separada(cliente: ClienteConsultoria, viagem_atual: Viagem) -> dict | None:
    """
    Verifica se há membros (dependentes ou clientes com mesmo email) com viagens separadas que ainda precisam de processo.
    
    Busca TODAS as viagens separadas relacionadas ao grupo de clientes, incluindo:
    - Viagens separadas criadas automaticamente para membros com visto diferente
    - Viagens onde o cliente relacionado está sozinho
    
    Args:
        cliente: ClienteConsultoria que acabou de ter processo criado
        viagem_atual: Viagem do processo recém-criado
    
    Returns:
        dict com 'cliente_id' e 'viagem_id' do próximo membro que precisa de processo, ou None
    """
    clientes_relacionados_ids = {cliente.pk}

    if cliente.is_principal:
        clientes_relacionados_ids.update(
            ClienteConsultoria.objects.filter(cliente_principal=cliente).values_list('pk', flat=True)
        )
    elif cliente.cliente_principal:
        principal = cliente.cliente_principal
        clientes_relacionados_ids.add(principal.pk)
        clientes_relacionados_ids.update(
            ClienteConsultoria.objects.filter(cliente_principal=principal).values_list('pk', flat=True)
        )
    
    # Remover o cliente atual
    clientes_relacionados_ids.discard(cliente.pk)
    
    if not clientes_relacionados_ids:
        return None
    
    # Buscar TODAS as viagens onde qualquer cliente relacionado está vinculado
    # Isso inclui viagens separadas criadas automaticamente para membros com visto diferente
    viagens_relacionadas = Viagem.objects.filter(
        clientes__pk__in=clientes_relacionados_ids
    ).distinct().exclude(pk=viagem_atual.pk)
    
    # Para cada viagem relacionada, verificar se há clientes que precisam de processo
    for viagem_relacionada in viagens_relacionadas:
        # Buscar todos os clientes relacionados que estão nesta viagem
        clientes_na_viagem_relacionada = viagem_relacionada.clientes.filter(
            pk__in=clientes_relacionados_ids
        )
        
        # Verificar se algum cliente relacionado nesta viagem não tem processo ainda
        for cliente_relacionado in clientes_na_viagem_relacionada:
            processo_existente = Processo.objects.filter(
                viagem=viagem_relacionada,
                cliente=cliente_relacionado
            ).exists()
            
            if not processo_existente:
                # Encontrou um membro em viagem separada que precisa de processo
                return {
                    'cliente_id': cliente_relacionado.pk,
                    'viagem_id': viagem_relacionada.pk,
                }
    
    return None


def _redirecionar_para_proximo_cliente(request, processo: Processo, proximo_cliente_info: dict, mensagem_especifica: str = None) -> HttpResponseRedirect:
    """Redireciona para criar processo do próximo cliente com mensagem apropriada."""
    try:
        proximo_cliente = ClienteConsultoria.objects.get(pk=proximo_cliente_info['cliente_id'])
        mensagem = mensagem_especifica or f"Processo criado para {processo.cliente.nome}. Criando processo para {proximo_cliente.nome}..."
    except ClienteConsultoria.DoesNotExist:
        mensagem = f"Processo criado para {processo.cliente.nome}. Criando próximo processo..."
    
    messages.info(request, mensagem)
    return redirect(
        f"{reverse('system:criar_processo')}?cliente_id={proximo_cliente_info['cliente_id']}&viagem_id={proximo_cliente_info['viagem_id']}"
    )


def _processar_proximo_cliente(request, processo: Processo) -> HttpResponseRedirect | None:
    """Processa e redireciona para próximo cliente que precisa de processo."""
    if proximo_cliente_processo := _obter_proximo_cliente_mesma_viagem(processo.viagem, processo.cliente):
        return _redirecionar_para_proximo_cliente(request, processo, proximo_cliente_processo)
    
    if proximo_cliente_viagem_separada := _obter_proximo_cliente_viagem_separada(processo.cliente, processo.viagem):
        mensagem = f"Processo criado para {processo.cliente.nome}. Criando processo em viagem separada..."
        return _redirecionar_para_proximo_cliente(request, processo, proximo_cliente_viagem_separada, mensagem)
    
    return None


def _processar_post_criar_processo(request, cliente_id, viagem_id) -> HttpResponseRedirect | None:
    """Processa requisição POST para criar processo."""
    _limpar_mensagens_duplicadas_sessao(request)
    storage = messages.get_messages(request)
    storage.used = True
    
    form = ProcessoForm(request.POST, user=request.user, cliente_id=cliente_id, viagem_id=viagem_id)
    if not form.is_valid():
        messages.error(request, "Não foi possível cadastrar o processo. Verifique os campos.")
        return None
    
    processo = form.save()
    
    if redirect_response := _processar_proximo_cliente(request, processo):
        return redirect_response
    
    messages.success(request, f"Todos os processos foram criados com sucesso! Processo criado para {processo.cliente.nome}.")
    return redirect("system:home_processos")


def _determinar_cliente_pre_selecionado(cliente_id, viagem_id) -> bool:
    """Determina se o cliente foi pré-selecionado (explicitamente ou automaticamente)."""
    if cliente_id:
        return True
    
    if not viagem_id:
        return False
    
    with suppress(Viagem.DoesNotExist):
        viagem = Viagem.objects.get(pk=viagem_id)
        return viagem.clientes.count() == 1
    
    return False


def _obter_etapas_disponiveis_viagem(viagem_id) -> list:
    """Retorna os status disponíveis vinculados à viagem para seleção de etapas."""
    if not viagem_id:
        return []
    
    try:
        status_vinculados = ViagemStatusProcesso.objects.filter(
            viagem_id=viagem_id,
            ativo=True
        ).select_related('status').order_by('status__ordem', 'status__nome')
        
        return [viagem_status.status for viagem_status in status_vinculados]
    except (Viagem.DoesNotExist, ValueError):
        return []


def _preparar_contexto_criar_processo(consultor, form, cliente_id, viagem_id) -> dict:
    """Prepara contexto para renderização do template de criar processo."""
    etapas_disponiveis = _obter_etapas_disponiveis_viagem(viagem_id) if viagem_id else []
    
    return {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "cliente_pre_selecionado": _determinar_cliente_pre_selecionado(cliente_id, viagem_id),
        "viagem_pre_selecionada": bool(viagem_id),
        "etapas_disponiveis": etapas_disponiveis,
    }


@login_required
def criar_processo(request):
    """Formulário para cadastrar novo processo."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if request.method == "GET":
        _limpar_mensagens_viagem_sessao(request)

    cliente_id = request.GET.get("cliente_id")
    viagem_id = request.GET.get("viagem_id")

    if request.method == "POST":
        if redirect_response := _processar_post_criar_processo(request, cliente_id, viagem_id):
            return redirect_response
        form = ProcessoForm(request.POST, user=request.user, cliente_id=cliente_id, viagem_id=viagem_id)
    else:
        form = ProcessoForm(user=request.user, cliente_id=cliente_id, viagem_id=viagem_id)

    contexto = _preparar_contexto_criar_processo(consultor, form, cliente_id, viagem_id)
    return render(request, "process/criar_processo.html", contexto)


@login_required
def visualizar_processo(request, pk: int):
    """Visualiza todas as informações do processo."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    processo = get_object_or_404(
        Processo.objects.select_related(
            "viagem",
            "viagem__pais_destino",
            "viagem__tipo_visto",
            "cliente",
            "cliente__cliente_principal",
            "assessor_responsavel",
        ).prefetch_related("etapas", "etapas__status"),
        pk=pk
    )

    # Verificar permissão
    # Qualquer usuário autenticado pode visualizar processos
    # Apenas restringir edição/exclusão baseado em permissões
    pode_visualizar = True

    # Buscar etapas do processo
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
        "pode_editar": pode_gerenciar_todos or (consultor and processo.assessor_responsavel_id == consultor.pk),
    }

    return render(request, "process/visualizar_processo.html", contexto)


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
    if not pode_gerenciar_todos and (not consultor or processo.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para editar este processo.")

    if request.method == "POST":
        # Debug: verificar todas as chaves do POST
        import logging
        logger = logging.getLogger(__name__)
        print(f"\n{'='*80}", flush=True)
        print(f"🔍 DEBUG POST - Processo {processo.pk}", flush=True)
        print(f"   POST keys: {list(request.POST.keys())}", flush=True)
        print(f"   'salvar_tudo' in POST: {'salvar_tudo' in request.POST}", flush=True)
        print(f"   'salvar_etapa' in POST: {'salvar_etapa' in request.POST}", flush=True)
        print(f"   'alterar_assessor' in POST: {'alterar_assessor' in request.POST}", flush=True)
        if 'salvar_tudo' in request.POST:
            print(f"   Valor de salvar_tudo: {request.POST.get('salvar_tudo')}", flush=True)
        print(f"{'='*80}\n", flush=True)
        
        # Verificar se está alterando o assessor responsável
        if "alterar_assessor" in request.POST:
            if pode_gerenciar_todos:
                try:
                    novo_assessor_id = int(request.POST.get("assessor_responsavel"))
                    novo_assessor = UsuarioConsultoria.objects.get(pk=novo_assessor_id, ativo=True)
                    processo.assessor_responsavel = novo_assessor
                    processo.save(update_fields=["assessor_responsavel"])
                    messages.success(request, f"Assessor responsável alterado para {novo_assessor.nome}.")
                except (ValueError, TypeError, UsuarioConsultoria.DoesNotExist):
                    messages.error(request, "Erro ao alterar o assessor responsável. Verifique os dados.")
            else:
                messages.error(request, "Você não tem permissão para alterar o assessor responsável.")
            return redirect("system:editar_processo", pk=processo.pk)
        
        # Verificar se está salvando uma etapa específica
        if "salvar_etapa" in request.POST:
            try:
                etapa_id = int(request.POST.get("salvar_etapa"))
                # Verificar se a etapa existe
                if not processo.etapas.filter(pk=etapa_id).exists():
                    messages.error(request, f"Etapa {etapa_id} não encontrada no processo.")
                else:
                    etapas_atualizadas = _atualizar_etapas_processo(processo, request, etapa_id=etapa_id)
                    if etapas_atualizadas > 0:
                        messages.success(request, "Etapa salva com sucesso.")
                    else:
                        messages.error(request, "Erro ao salvar a etapa. Verifique se os dados foram preenchidos corretamente.")
            except (ValueError, TypeError) as e:
                messages.error(request, f"Erro ao processar a solicitação: {str(e)}")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Erro ao salvar etapa: {e}", exc_info=True)
                messages.error(request, f"Erro ao salvar a etapa: {str(e)}")
            return redirect("system:editar_processo", pk=processo.pk)
        
        # Salvar todas as etapas
        if "salvar_tudo" in request.POST:
            import logging
            logger = logging.getLogger(__name__)
            
            try:
                # Debug: verificar POST data
                post_keys = [k for k in request.POST.keys() if k.startswith('etapa_')]
                print(f"\n{'='*80}", flush=True)
                print(f"🔵 SALVANDO TODAS AS ETAPAS", flush=True)
                print(f"   Processo ID: {processo.pk}", flush=True)
                print(f"   Total de campos no POST: {len(post_keys)}", flush=True)
                print(f"   Campos: {post_keys[:30]}", flush=True)
                print(f"{'='*80}\n", flush=True)
                
                logger.info(f"Salvando todas as etapas. POST com {len(post_keys)} campos de etapa.")
                
                etapas_atualizadas = _atualizar_etapas_processo(processo, request)
                
                print(f"\n{'='*80}", flush=True)
                print(f"✅ RESULTADO: {etapas_atualizadas} etapa(s) atualizada(s)", flush=True)
                print(f"{'='*80}\n", flush=True)
                
                if etapas_atualizadas > 0:
                    messages.success(request, f"{etapas_atualizadas} etapa(s) atualizada(s) com sucesso.")
                else:
                    messages.warning(request, "Nenhuma etapa foi atualizada. Verifique se há etapas no processo e se os dados foram preenchidos.")
            except Exception as e:
                logger.error(f"Erro ao salvar todas as etapas: {e}", exc_info=True)
                print(f"\n❌ ERRO ao salvar todas as etapas: {e}", flush=True)
                messages.error(request, f"Erro ao salvar as etapas: {str(e)}")
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
    
    # Obter etapas disponíveis para adicionar (que foram removidas)
    etapas_disponiveis = _obter_etapas_disponiveis_para_adicionar(processo)

    # Buscar assessores disponíveis para alteração
    assessores_disponiveis = UsuarioConsultoria.objects.filter(ativo=True).order_by("nome")
    
    contexto = {
        "processo": processo,
        "etapas_com_datas": etapas_com_datas,
        "data_base": data_base,
        "etapas_disponiveis": etapas_disponiveis,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "assessores_disponiveis": assessores_disponiveis,
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
@require_http_methods(["POST"])
def remover_etapa_processo(request, processo_pk: int, etapa_pk: int):
    """Remove uma etapa do processo."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    processo = get_object_or_404(
        Processo.objects.select_related("assessor_responsavel"),
        pk=processo_pk
    )
    
    # Verificar permissão
    if not pode_gerenciar_todos and (not consultor or processo.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para remover etapas deste processo.")
    
    etapa = get_object_or_404(
        EtapaProcesso.objects.filter(processo=processo),
        pk=etapa_pk
    )
    
    etapa_nome = etapa.status.nome
    etapa.delete()
    
    messages.success(request, f"Etapa '{etapa_nome}' removida do processo com sucesso.")
    return redirect("system:editar_processo", pk=processo.pk)


def _obter_etapas_disponiveis_para_adicionar(processo: Processo):
    """Retorna os status disponíveis que podem ser adicionados como etapas ao processo."""
    # Obter todos os status vinculados à viagem
    status_vinculados = ViagemStatusProcesso.objects.filter(
        viagem=processo.viagem,
        ativo=True
    ).select_related('status').order_by('status__ordem', 'status__nome')
    
    # Obter IDs dos status que já têm etapa no processo
    status_ids_existentes = set(
        processo.etapas.values_list('status_id', flat=True)
    )
    
    # Filtrar apenas os que não têm etapa ainda
    return [
        viagem_status.status
        for viagem_status in status_vinculados
        if viagem_status.status.pk not in status_ids_existentes
    ]


@login_required
@require_http_methods(["POST"])
def adicionar_etapa_processo(request, processo_pk: int, status_pk: int):
    """Adiciona uma etapa ao processo baseada em um status disponível."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    processo = get_object_or_404(
        Processo.objects.select_related("assessor_responsavel", "viagem"),
        pk=processo_pk
    )
    
    # Verificar permissão
    if not pode_gerenciar_todos and (not consultor or processo.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para adicionar etapas a este processo.")
    
    # Verificar se o status está vinculado à viagem
    viagem_status = get_object_or_404(
        ViagemStatusProcesso.objects.filter(
            viagem=processo.viagem,
            status_id=status_pk,
            ativo=True
        )
    )
    
    status = viagem_status.status
    
    # Verificar se já existe etapa com este status
    if EtapaProcesso.objects.filter(processo=processo, status=status).exists():
        messages.error(request, f"Etapa '{status.nome}' já existe neste processo.")
        return redirect("system:editar_processo", pk=processo.pk)
    
    # Criar a etapa
    prazo_dias = max(status.prazo_padrao_dias or 0, 0)
    
    EtapaProcesso.objects.create(
        processo=processo,
        status=status,
        prazo_dias=prazo_dias,
        ordem=status.ordem,
    )
    
    messages.success(request, f"Etapa '{status.nome}' adicionada ao processo com sucesso.")
    return redirect("system:editar_processo", pk=processo.pk)


@login_required
def listar_processos(request):
    """Lista todos os processos."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    # Listar TODOS os processos, independente de assessor
    processos = Processo.objects.select_related(
        "viagem",
        "viagem__pais_destino",
        "viagem__tipo_visto",
        "cliente",
        "assessor_responsavel",
    ).prefetch_related("etapas", "etapas__status").order_by("-criado_em")

    # Aplicar filtros se fornecidos
    filtro_cliente = request.GET.get("cliente", "").strip()
    filtro_viagem = request.GET.get("viagem", "").strip()
    filtro_assessor = request.GET.get("assessor", "").strip()

    if filtro_cliente:
        processos = processos.filter(cliente__nome__icontains=filtro_cliente)
    if filtro_viagem:
        processos = processos.filter(
            Q(viagem__pais_destino__nome__icontains=filtro_viagem) |
            Q(viagem__tipo_visto__nome__icontains=filtro_viagem)
        )
    if filtro_assessor:
        processos = processos.filter(assessor_responsavel__nome__icontains=filtro_assessor)

    # Buscar opções para os filtros
    assessores = UsuarioConsultoria.objects.filter(ativo=True).order_by("nome")
    # Listar TODOS os clientes para os filtros
    clientes = ClienteConsultoria.objects.all().order_by("nome")

    contexto = {
        "processos": processos,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "consultor": consultor,
        "filtros_aplicados": {
            "cliente": filtro_cliente,
            "viagem": filtro_viagem,
            "assessor": filtro_assessor,
        },
        "clientes": clientes,
        "assessores": assessores,
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
        criado_em = cliente.criado_em.isoformat()
        return JsonResponse({"criado_em": criado_em})
    except ClienteConsultoria.DoesNotExist:
        return JsonResponse({"error": "Cliente não encontrado."}, status=404)


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
        # Clientes diretamente na viagem
        clientes_diretos = viagem.clientes.all()
        
        clientes_ids = set(clientes_diretos.values_list('pk', flat=True))
        for cliente_direto in clientes_diretos:
            if cliente_direto.is_principal:
                clientes_ids.update(
                    ClienteConsultoria.objects.filter(cliente_principal=cliente_direto).values_list('pk', flat=True)
                )
            elif cliente_direto.cliente_principal_id:
                clientes_ids.add(cliente_direto.cliente_principal_id)
                clientes_ids.update(
                    ClienteConsultoria.objects.filter(cliente_principal_id=cliente_direto.cliente_principal_id).values_list('pk', flat=True)
                )
        
        # Obter todos os clientes (diretos + mesmo email) ordenados
        # Ordenar: principais primeiro, depois dependentes
        clientes = ClienteConsultoria.objects.filter(pk__in=clientes_ids).select_related('cliente_principal')
        
        # Separar principais e dependentes
        principais = [c for c in clientes if c.is_principal]
        dependentes = [c for c in clientes if not c.is_principal]
        
        # Ordenar cada grupo por nome
        principais.sort(key=lambda x: x.nome)
        dependentes.sort(key=lambda x: x.nome)
        
        # Combinar: principais primeiro, depois dependentes
        clientes_ordenados = principais + dependentes
        
        clientes_list = [
            {
                "id": cliente.pk,
                "nome": cliente.nome,
                "is_principal": cliente.is_principal,
            }
            for cliente in clientes_ordenados
        ]

        return JsonResponse(clientes_list, safe=False)
    except Viagem.DoesNotExist:
        return JsonResponse({"error": "Viagem não encontrada."}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
