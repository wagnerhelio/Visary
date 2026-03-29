   
                                        
   

import logging
from contextlib import suppress
from datetime import timedelta

from django.contrib import messages
from django.utils.dateparse import parse_date
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from system.forms import ProcessoForm
from system.models import (
    ClienteConsultoria,
    ClienteViagem,
    EtapaProcesso,
    Processo,
    StatusProcesso,
    Viagem,
    ViagemStatusProcesso,
)
from system.models import UsuarioConsultoria
from system.views.client_views import listar_clientes, obter_consultor_usuario, usuario_pode_gerenciar_todos


logger = logging.getLogger(__name__)


def _aplicar_filtros_processos(processos, request, incluir_assessor=True):
    filtros = {
        "cliente": request.GET.get("cliente", "").strip(),
        "viagem": request.GET.get("viagem", "").strip(),
    }
    if incluir_assessor:
        filtros["assessor"] = request.GET.get("assessor", "").strip()

    if filtros["cliente"]:
        processos = processos.filter(cliente__nome__icontains=filtros["cliente"])
    if filtros["viagem"]:
        processos = processos.filter(
            Q(viagem__pais_destino__nome__icontains=filtros["viagem"])
            | Q(viagem__tipo_visto__nome__icontains=filtros["viagem"])
        )
    if incluir_assessor and filtros.get("assessor"):
        with suppress(ValueError, TypeError):
            processos = processos.filter(assessor_responsavel_id=int(filtros["assessor"]))

    return processos, filtros


def _ordenar_processos_por_grupo_familiar(processos, viagem=None):
    if viagem:
        cv_map = {
            cv.cliente_id: cv.papel
            for cv in ClienteViagem.objects.filter(viagem=viagem)
        }
        return sorted(
            processos,
            key=lambda p: (0 if cv_map.get(p.cliente_id) == "principal" else 1, p.cliente.nome_completo, p.pk),
        )
    return sorted(processos, key=lambda p: (p.cliente.nome_completo, p.pk))


@login_required
def home_processos(request):
                                                              
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

                                                                                                                              
    from system.views.client_views import listar_clientes
    clientes_usuario = listar_clientes(request.user)
    clientes_ids = list(clientes_usuario.values_list("pk", flat=True))
    
                                                                
    processos = Processo.objects.filter(
        cliente__pk__in=clientes_ids
    ).select_related(
        "viagem",
        "viagem__pais_destino",
        "viagem__tipo_visto",
        "cliente",
        "assessor_responsavel",
    ).prefetch_related("etapas", "etapas__status").distinct()

    processos, filtros_aplicados = _aplicar_filtros_processos(processos, request, incluir_assessor=False)
    
    processos_ordenados = _ordenar_processos_por_grupo_familiar(processos)
    
    processos_limitados = processos_ordenados[:10]
    total_processos_concluidos = sum(1 for processo in processos_ordenados if processo.progresso_percentual >= 100)
    total_processos_pendentes = sum(1 for processo in processos_ordenados if processo.progresso_percentual < 100)
    
                                   
    contexto = {
        "processos": processos_limitados,
        "total_processos": processos.count(),
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "consultor": consultor,
        "clientes": clientes_usuario.order_by("nome"),
        "filtros_aplicados": filtros_aplicados,
        "total_processos_concluidos": total_processos_concluidos,
        "total_processos_pendentes": total_processos_pendentes,
    }

    return render(request, "process/home_processos.html", contexto)


def _limpar_mensagens_duplicadas_sessao(request):
                                                
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
                                                                                                 
    etapas_atualizadas = 0
    
                                                        
    if etapa_id:
        try:
            etapa = processo.etapas.get(pk=etapa_id)
            prazo_antes = etapa.prazo_dias
            etapa_id_str = str(etapa.pk)
            
                                   
            concluida = request.POST.get(f"etapa_{etapa_id_str}_concluida") == "on"
            prazo_dias = request.POST.get(f"etapa_{etapa_id_str}_prazo", "").strip()
            data_conclusao = request.POST.get(f"etapa_{etapa_id_str}_data", "").strip() or None
            observacoes = request.POST.get(f"etapa_{etapa_id_str}_obs", "").strip()

                              
            etapa.concluida = concluida
            etapa.observacoes = observacoes or ""
            
                                  
            if prazo_dias:
                try:
                    etapa.prazo_dias = int(prazo_dias)
                except ValueError:
                    messages.error(request, "Prazo (dias) inválido. Informe um número inteiro >= 0.")
                    etapa.prazo_dias = prazo_antes
                    return 0
            else:
                etapa.prazo_dias = 0
            
                                      
            if data_conclusao:
                try:
                    etapa.data_conclusao = parse_date(data_conclusao)
                except (ValueError, TypeError):
                    etapa.data_conclusao = None
            else:
                                                                
                if not concluida:
                    etapa.data_conclusao = None
            
                                           
            etapa.save(update_fields=["concluida", "prazo_dias", "data_conclusao", "observacoes", "atualizado_em"])
            
                                                             
            etapa.refresh_from_db()
            etapas_atualizadas = 1
        except EtapaProcesso.DoesNotExist:
            logger.warning(f"Etapa {etapa_id} não encontrada no processo {processo.pk}")
            return 0
        except Exception as e:
            logger.error(f"Erro ao atualizar etapa {etapa_id}: {e}", exc_info=True)
            return 0
    else:
                                   
        etapas_no_processo = list(processo.etapas.all())
        logger.debug("Processando %s etapa(s) do processo %s", len(etapas_no_processo), processo.pk)
        
        for etapa in etapas_no_processo:
            etapa_id_str = str(etapa.pk)
            
                                   
            concluida_val = request.POST.get(f"etapa_{etapa_id_str}_concluida", "")
            concluida = concluida_val == "on"
            prazo_dias_str = request.POST.get(f"etapa_{etapa_id_str}_prazo", "").strip()
            data_conclusao_str = request.POST.get(f"etapa_{etapa_id_str}_data", "").strip() or None
            observacoes = request.POST.get(f"etapa_{etapa_id_str}_obs", "").strip()
            
                                                       
            concluida_antes = etapa.concluida
            prazo_antes = etapa.prazo_dias
            data_antes = etapa.data_conclusao
            obs_antes = etapa.observacoes

                              
            etapa.concluida = concluida
            etapa.observacoes = observacoes or ""
            
                                                                     
            try:
                if prazo_dias_str:
                    etapa.prazo_dias = int(prazo_dias_str)
                else:
                                                       
                    etapa.prazo_dias = 0
            except ValueError:
                messages.error(request, "Prazo (dias) inválido. Informe um número inteiro >= 0.")
                etapa.prazo_dias = prazo_antes
                                                               
                continue
            
                                      
            if data_conclusao_str:
                try:
                    etapa.data_conclusao = parse_date(data_conclusao_str)
                except (ValueError, TypeError):
                    etapa.data_conclusao = None
            else:
                                                                
                if not concluida:
                    etapa.data_conclusao = None
            
                                         
            houve_mudanca = (
                etapa.concluida != concluida_antes or
                etapa.prazo_dias != prazo_antes or
                etapa.data_conclusao != data_antes or
                etapa.observacoes != obs_antes
            )
            
                                                                                    
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
                    logger.debug(
                        "Etapa %s (%s) salva - concluida=%s prazo=%s data=%s",
                        etapa_id_str,
                        etapa.status.nome,
                        concluida,
                        etapa.prazo_dias,
                        etapa.data_conclusao,
                    )
                except Exception as e:
                    logger.error(f"Erro ao salvar etapa {etapa_id_str}: {e}", exc_info=True)

    return etapas_atualizadas


def _criar_etapas_se_necessario(processo: Processo):
                                                                                            
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
       
                                                                                  
    
                                                                                  
                                         
    
         
                            
                                                                           
    
            
                                                                                                 
       
    clientes_na_viagem = viagem.clientes.all()
    clientes_relacionados_ids = set(clientes_na_viagem.values_list('pk', flat=True))
    viagens_com_clientes = ClienteViagem.objects.filter(
        cliente_id__in=clientes_relacionados_ids
    ).values_list("viagem_id", flat=True).distinct()
    clientes_relacionados_ids.update(
        ClienteViagem.objects.filter(viagem_id__in=viagens_com_clientes).values_list("cliente_id", flat=True)
    )
    
                             
    clientes_relacionados_ids.discard(cliente_atual.pk)
    
    if not clientes_relacionados_ids:
        return None
    
                                                                               
    for cliente_id in clientes_relacionados_ids:
        cliente_relacionado = ClienteConsultoria.objects.get(pk=cliente_id)
        processo_existente = Processo.objects.filter(
            viagem=viagem,
            cliente=cliente_relacionado
        ).exists()
        
        if not processo_existente:
                                                                                      
            return {
                'cliente_id': cliente_relacionado.pk,
                'viagem_id': viagem.pk,
            }
    
    return None


def _obter_proximo_cliente_viagem_separada(cliente: ClienteConsultoria, viagem_atual: Viagem) -> dict | None:
       
                                                                                                                          
    
                                                                                  
                                                                                
                                                     
    
         
                                                                     
                                                     
    
            
                                                                                              
       
    clientes_relacionados_ids = {cliente.pk}
    viagens_do_cliente = ClienteViagem.objects.filter(
        cliente=cliente
    ).values_list("viagem_id", flat=True).distinct()
    clientes_relacionados_ids.update(
        ClienteViagem.objects.filter(viagem_id__in=viagens_do_cliente).values_list("cliente_id", flat=True)
    )
    
                             
    clientes_relacionados_ids.discard(cliente.pk)
    
    if not clientes_relacionados_ids:
        return None
    
                                                                              
                                                                                            
    viagens_relacionadas = Viagem.objects.filter(
        clientes__pk__in=clientes_relacionados_ids
    ).distinct().exclude(pk=viagem_atual.pk)
    
                                                                                     
    for viagem_relacionada in viagens_relacionadas:
                                                                      
        clientes_na_viagem_relacionada = viagem_relacionada.clientes.filter(
            pk__in=clientes_relacionados_ids
        )
        
                                                                                    
        for cliente_relacionado in clientes_na_viagem_relacionada:
            processo_existente = Processo.objects.filter(
                viagem=viagem_relacionada,
                cliente=cliente_relacionado
            ).exists()
            
            if not processo_existente:
                                                                                
                return {
                    'cliente_id': cliente_relacionado.pk,
                    'viagem_id': viagem_relacionada.pk,
                }
    
    return None


def _redirecionar_para_proximo_cliente(request, processo: Processo, proximo_cliente_info: dict, mensagem_especifica: str = None) -> HttpResponseRedirect:
                                                                                     
    try:
        proximo_cliente = ClienteConsultoria.objects.get(pk=proximo_cliente_info['cliente_id'])
        mensagem = mensagem_especifica or f"Processo criado para {processo.cliente.nome_completo}. Criando processo para {proximo_cliente.nome_completo}..."
    except ClienteConsultoria.DoesNotExist:
        mensagem = f"Processo criado para {processo.cliente.nome_completo}. Criando próximo processo..."
    
    messages.info(request, mensagem)
    return redirect(
        f"{reverse('system:criar_processo')}?cliente_id={proximo_cliente_info['cliente_id']}&viagem_id={proximo_cliente_info['viagem_id']}"
    )


def _processar_proximo_cliente(request, processo: Processo) -> HttpResponseRedirect | None:
                                                                              
    if proximo_cliente_processo := _obter_proximo_cliente_mesma_viagem(processo.viagem, processo.cliente):
        return _redirecionar_para_proximo_cliente(request, processo, proximo_cliente_processo)
    
    if proximo_cliente_viagem_separada := _obter_proximo_cliente_viagem_separada(processo.cliente, processo.viagem):
        mensagem = f"Processo criado para {processo.cliente.nome_completo}. Criando processo em viagem separada..."
        return _redirecionar_para_proximo_cliente(request, processo, proximo_cliente_viagem_separada, mensagem)
    
    return None


def _processar_post_criar_processo(request, cliente_id, viagem_id) -> HttpResponseRedirect | None:
                                                       
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
    
    messages.success(request, f"Todos os processos foram criados com sucesso! Processo criado para {processo.cliente.nome_completo}.")
    return redirect("system:home_processos")


def _determinar_cliente_pre_selecionado(cliente_id, viagem_id) -> bool:
                                                                                         
    if cliente_id:
        return True
    
    if not viagem_id:
        return False
    
    with suppress(Viagem.DoesNotExist):
        viagem = Viagem.objects.get(pk=viagem_id)
        return viagem.clientes.count() == 1
    
    return False


def _obter_etapas_disponiveis_viagem(viagem_id) -> list:
                                                                                   
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

                         
                                                            
                                                             
    pode_visualizar = True

                               
    etapas = processo.etapas.select_related("status").order_by("ordem", "status__nome").all()

                                                   
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

                         
    if not pode_gerenciar_todos and (not consultor or processo.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para editar este processo.")

    if request.method == "POST":
        logger.debug("POST editar_processo %s com campos: %s", processo.pk, list(request.POST.keys()))
        
                                                            
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
        
                                                         
        if "salvar_etapa" in request.POST:
            try:
                etapa_id = int(request.POST.get("salvar_etapa"))
                                             
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
                logger.error(f"Erro ao salvar etapa: {e}", exc_info=True)
                messages.error(request, f"Erro ao salvar a etapa: {str(e)}")
            return redirect("system:editar_processo", pk=processo.pk)
        
                                
        if "salvar_tudo" in request.POST:
            try:
                post_keys = [k for k in request.POST.keys() if k.startswith('etapa_')]
                logger.info(f"Salvando todas as etapas. POST com {len(post_keys)} campos de etapa.")
                etapas_atualizadas = _atualizar_etapas_processo(processo, request)

                if etapas_atualizadas > 0:
                    messages.success(request, f"{etapas_atualizadas} etapa(s) atualizada(s) com sucesso.")
                else:
                    messages.warning(request, "Nenhuma etapa foi atualizada. Verifique se há etapas no processo e se os dados foram preenchidos.")
            except Exception as e:
                logger.error(f"Erro ao salvar todas as etapas: {e}", exc_info=True)
                messages.error(request, f"Erro ao salvar as etapas: {str(e)}")
            return redirect("system:editar_processo", pk=processo.pk)

                               
    etapas = processo.etapas.select_related("status").order_by("ordem", "status__nome").all()

                                
    _criar_etapas_se_necessario(processo)
    
                                             
    etapas = processo.etapas.select_related("status").order_by("ordem", "status__nome").all()

                                                   
    etapas_com_datas = _calcular_datas_finalizacao_etapas(processo, etapas)
    data_base = processo.cliente.criado_em.date()
    
                                                                   
    etapas_disponiveis = _obter_etapas_disponiveis_para_adicionar(processo)

                                                  
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
                              
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied("Você não tem permissão para excluir processos.")

    processo = get_object_or_404(Processo, pk=pk)
    cliente_nome = processo.cliente.nome_completo
    processo.delete()

    messages.success(request, f"Processo de {cliente_nome} excluído com sucesso.")
    return redirect("system:listar_processos")


@login_required
@require_http_methods(["POST"])
def remover_etapa_processo(request, processo_pk: int, etapa_pk: int):
                                       
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    processo = get_object_or_404(
        Processo.objects.select_related("assessor_responsavel"),
        pk=processo_pk
    )
    
                         
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
                                                                                          
                                               
    status_vinculados = ViagemStatusProcesso.objects.filter(
        viagem=processo.viagem,
        ativo=True
    ).select_related('status').order_by('status__ordem', 'status__nome')
    
                                                       
    status_ids_existentes = set(
        processo.etapas.values_list('status_id', flat=True)
    )
    
                                               
    return [
        viagem_status.status
        for viagem_status in status_vinculados
        if viagem_status.status.pk not in status_ids_existentes
    ]


@login_required
@require_http_methods(["POST"])
def adicionar_etapa_processo(request, processo_pk: int, status_pk: int):
                                                                         
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    processo = get_object_or_404(
        Processo.objects.select_related("assessor_responsavel", "viagem"),
        pk=processo_pk
    )
    
                         
    if not pode_gerenciar_todos and (not consultor or processo.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para adicionar etapas a este processo.")
    
                                                   
    viagem_status = get_object_or_404(
        ViagemStatusProcesso.objects.filter(
            viagem=processo.viagem,
            status_id=status_pk,
            ativo=True
        )
    )
    
    status = viagem_status.status
    
                                                  
    if EtapaProcesso.objects.filter(processo=processo, status=status).exists():
        messages.error(request, f"Etapa '{status.nome}' já existe neste processo.")
        return redirect("system:editar_processo", pk=processo.pk)
    
                   
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
                                    
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

                                                          
    processos = Processo.objects.select_related(
        "viagem",
        "viagem__pais_destino",
        "viagem__tipo_visto",
        "cliente",
        "assessor_responsavel",
    ).prefetch_related("etapas", "etapas__status").distinct()

    processos, filtros_aplicados = _aplicar_filtros_processos(processos, request, incluir_assessor=True)

    processos_ordenados = _ordenar_processos_por_grupo_familiar(processos)
    total_processos_concluidos = sum(1 for processo in processos_ordenados if processo.progresso_percentual >= 100)
    total_processos_pendentes = sum(1 for processo in processos_ordenados if processo.progresso_percentual < 100)

    assessores = UsuarioConsultoria.objects.filter(ativo=True).order_by("nome")
    clientes = ClienteConsultoria.objects.order_by("nome")

    contexto = {
        "processos": processos_ordenados,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "consultor": consultor,
        "filtros_aplicados": filtros_aplicados,
        "clientes": clientes,
        "assessores": assessores,
        "total_processos": len(processos_ordenados),
        "total_processos_concluidos": total_processos_concluidos,
        "total_processos_pendentes": total_processos_pendentes,
    }

    return render(request, "process/listar_processos.html", contexto)


@login_required
@require_GET
def api_status_processo(request):
                                                                    
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
                                                             
    viagem_id = request.GET.get("viagem_id")

    if not viagem_id:
        return JsonResponse({"error": "ID da viagem não fornecido."}, status=400)

    try:
        viagem = Viagem.objects.get(pk=viagem_id)
                                        
        clientes_viagem_qs = ClienteViagem.objects.filter(
            viagem=viagem
        ).select_related("cliente")

        # Expandir grupo familiar via viagens compartilhadas
        clientes_ids = set(clientes_viagem_qs.values_list("cliente_id", flat=True))
        viagens_relacionadas = ClienteViagem.objects.filter(
            cliente_id__in=clientes_ids
        ).values_list("viagem_id", flat=True).distinct()
        clientes_ids.update(
            ClienteViagem.objects.filter(viagem_id__in=viagens_relacionadas).values_list("cliente_id", flat=True)
        )

        cv_map = {cv.cliente_id: cv.papel for cv in clientes_viagem_qs}
        clientes = ClienteConsultoria.objects.filter(pk__in=clientes_ids).order_by("nome")

        clientes_ordenados = sorted(
            clientes,
            key=lambda c: (0 if cv_map.get(c.pk) == "principal" else 1, c.nome),
        )

        clientes_list = [
            {
                "id": cliente.pk,
                "nome": cliente.nome_completo,
                "is_principal": cv_map.get(cliente.pk) == "principal",
            }
            for cliente in clientes_ordenados
        ]

        return JsonResponse(clientes_list, safe=False)
    except Viagem.DoesNotExist:
        return JsonResponse({"error": "Viagem não encontrada."}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
