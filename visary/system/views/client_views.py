   
                                           
   

import json
import logging
import re
from contextlib import suppress
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.db.models import Count, Q, QuerySet
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from consultancy.forms import ClienteConsultoriaForm
from consultancy.models import (
    CampoEtapaCliente,
    ClienteConsultoria,
    ClienteViagem,
    EtapaCadastroCliente,
    FormularioVisto,
    Processo,
    RespostaFormulario,
    Viagem,
)
from consultancy.models.financial_models import Financeiro, StatusFinanceiro
from consultancy.services.cep import buscar_endereco_por_cep
from system.models import UsuarioConsultoria

User = get_user_model()

                                                      
logger = logging.getLogger(__name__)


class DependentesNaoValidosError(Exception):
    pass                                                                                      


def _aplicar_filtros_clientes(clientes, request, incluir_assessor=False):
                                                                                                   
    filtros = {
        "nome": request.GET.get("nome", "").strip(),
        "email": request.GET.get("email", "").strip(),
        "status_financeiro": request.GET.get("status_financeiro", "").strip(),
    }
    
    if incluir_assessor:
        filtros["assessor"] = request.GET.get("assessor", "").strip()
    
    if filtros["nome"]:
        clientes = clientes.filter(nome__icontains=filtros["nome"])
    if incluir_assessor and filtros.get("assessor"):
        with suppress(ValueError, TypeError):
            clientes = clientes.filter(assessor_responsavel_id=int(filtros["assessor"]))
    if filtros["email"]:
        clientes = clientes.filter(email__icontains=filtros["email"])
    if filtros["status_financeiro"]:
        if filtros["status_financeiro"] == "pendente":
            clientes = clientes.filter(registros_financeiros__status=StatusFinanceiro.PENDENTE).distinct()
        elif filtros["status_financeiro"] == "pago":
            clientes = clientes.filter(registros_financeiros__status=StatusFinanceiro.PAGO).distinct()
        elif filtros["status_financeiro"] == "cancelado":
            clientes = clientes.filter(registros_financeiros__status=StatusFinanceiro.CANCELADO).distinct()
        elif filtros["status_financeiro"] == "sem_registros":
            clientes = clientes.annotate(
                total_registros=Count("registros_financeiros")
            ).filter(total_registros=0)
    
    return clientes, filtros


def _obter_status_financeiro_cliente(cliente: ClienteConsultoria) -> str:
    registros = Financeiro.objects.filter(cliente=cliente)
    if not registros.exists():
        principal = getattr(cliente, "cliente_principal", None)
        if principal is not None:
            return _obter_status_financeiro_cliente(principal)
        return "Sem registros"
    tem_pendente = registros.filter(status=StatusFinanceiro.PENDENTE).exists()
    tem_pago = registros.filter(status=StatusFinanceiro.PAGO).exists()
    tem_cancelado = registros.filter(status=StatusFinanceiro.CANCELADO).exists()
    return "Pendente" if tem_pendente else "Pago" if tem_pago else "Cancelado" if tem_cancelado else "Sem registros"


def _obter_tipo_visto_cliente(viagem, cliente):
                                                                                                            
    with suppress(ClienteViagem.DoesNotExist):
        cliente_viagem = ClienteViagem.objects.select_related('tipo_visto__formulario').get(
            viagem=viagem, cliente=cliente
        )
        if cliente_viagem.tipo_visto:
            return cliente_viagem.tipo_visto
    return viagem.tipo_visto


def _obter_formulario_por_tipo_visto(tipo_visto, apenas_ativo=True):
                                                                               
    if not tipo_visto or not hasattr(tipo_visto, 'pk') or not tipo_visto.pk:
        return None
    try:
        if apenas_ativo:
            return FormularioVisto.objects.select_related('tipo_visto').get(
                tipo_visto_id=tipo_visto.pk,
                ativo=True
            )
        return FormularioVisto.objects.select_related('tipo_visto').get(
            tipo_visto_id=tipo_visto.pk
        )
    except FormularioVisto.DoesNotExist:
        return None


def _obter_status_formulario_cliente(cliente: ClienteConsultoria) -> dict:
       
                                                                                 
    
                              
                                                                            
                                           
                                           
                                                    
       
                                                                    
                                                   
    viagens = cliente.viagens.select_related(
        'tipo_visto__formulario'
    ).prefetch_related(
        'tipo_visto__formulario__perguntas'
    ).order_by('-data_prevista_viagem')
    
    if not viagens.exists():
        return {
            "status": "Sem formulário",
            "total_perguntas": 0,
            "total_respostas": 0,
            "completo": False,
        }
    
                                                                    
    melhor_status = None
    melhor_info = None
    
    for viagem in viagens:
                                                  
        tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)
        
        if not tipo_visto_cliente:
            continue
        
                                                         
        formulario = _obter_formulario_por_tipo_visto(tipo_visto_cliente, apenas_ativo=True)
        
        if not formulario:
            continue
        
                                                              
        total_perguntas = formulario.perguntas.filter(ativo=True).count()
        total_respostas = RespostaFormulario.objects.filter(
            viagem=viagem,
            cliente=cliente
        ).count()
        
        completo = total_respostas == total_perguntas if total_perguntas > 0 else False
        
        info = {
            "total_perguntas": total_perguntas,
            "total_respostas": total_respostas,
            "completo": completo,
        }
        
                                                        
        if completo:
            status = "Completo"
        elif total_respostas > 0:
            status = "Parcial"
        else:
            status = "Não preenchido"
        
        info["status"] = status
        
                                                                                   
        if not melhor_info:
            melhor_info = info
            melhor_status = status
        elif status == "Completo" and melhor_status != "Completo":
            melhor_info = info
            melhor_status = status
        elif status == "Parcial" and melhor_status == "Não preenchido":
            melhor_info = info
            melhor_status = status
    
    if melhor_info:
        return melhor_info
    
                                              
    return {
        "status": "Sem formulário",
        "total_perguntas": 0,
        "total_respostas": 0,
        "completo": False,
    }


def listar_clientes(user: User) -> QuerySet[ClienteConsultoria]:
       
                                                                 
                                                                        
       

    queryset = ClienteConsultoria.objects.select_related(
        "assessor_responsavel",
        "criado_por",
        "assessor_responsavel__perfil",
        "cliente_principal",
        "cliente_principal__assessor_responsavel",
        "parceiro_indicador",
    ).order_by("-criado_em")

    if user.is_superuser or user.is_staff:
        return queryset

    consultor = obter_consultor_usuario(user)
    if not consultor:
        return queryset.none()

                                                          
                                                                                          
                                                                                                           
                                                                                                                                
    consultor_id = consultor.pk
    return queryset.filter(
                                                 
        Q(assessor_responsavel_id=consultor_id) |
                                                                         
        Q(cliente_principal__assessor_responsavel_id=consultor_id)
    ).distinct()


def usuario_pode_gerenciar_todos(user: User, consultor: UsuarioConsultoria | None) -> bool:
    return (
        user.is_superuser
        or user.is_staff
        or (consultor and consultor.perfil.nome.lower() == "administrador")
    )


def usuario_tem_acesso_modulo(user: User, consultor: UsuarioConsultoria | None, nome_modulo: str) -> bool:
    if user.is_superuser or user.is_staff:
        return True
    if not consultor:
        return False
    return consultor.perfil.modulos.filter(nome=nome_modulo).exists()


def usuario_pode_editar_cliente(user: User, consultor: UsuarioConsultoria | None, cliente) -> bool:
    if usuario_pode_gerenciar_todos(user, consultor):
        return True
    if consultor and getattr(cliente, "assessor_responsavel_id", None) == consultor.pk:
        return True
    criado_por_id = getattr(cliente, "criado_por_id", None)
    return criado_por_id is not None and criado_por_id == getattr(user, "id", None)


def obter_consultor_usuario(user: User) -> UsuarioConsultoria | None:
                                                                                              
    if not user or not user.username:
        return None
    
                                                                                          
    consultor = (
        UsuarioConsultoria.objects.select_related("perfil")
        .filter(email__iexact=user.username.strip(), ativo=True)
        .first()
    )
    
                                                                             
    if not consultor and user.email:
        consultor = (
            UsuarioConsultoria.objects.select_related("perfil")
            .filter(email__iexact=user.email.strip(), ativo=True)
            .first()
        )
    
    return consultor


@login_required
def excluir_cliente(request, pk: int):
    if request.method != "POST":
        raise PermissionDenied

    cliente = get_object_or_404(
        ClienteConsultoria.objects.select_related("assessor_responsavel"),
        pk=pk,
    )

    consultor = obter_consultor_usuario(request.user)

    if not usuario_pode_gerenciar_todos(request.user, consultor):
        raise PermissionDenied

    cliente.delete()
    messages.success(request, f"{cliente.nome} excluído com sucesso.")
    return redirect("system:listar_clientes_view")


@login_required
def home_clientes(request):
                                                             
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    perfil_usuario = consultor.perfil.nome if consultor and consultor.perfil else ("Administrador" if request.user.is_superuser else None)
    
    base_qs = ClienteConsultoria.objects.select_related(
        "assessor_responsavel",
        "criado_por",
        "assessor_responsavel__perfil",
        "cliente_principal",
        "cliente_principal__assessor_responsavel",
        "parceiro_indicador",
    ).prefetch_related("dependentes", "viagens").order_by("-criado_em")

    _, filtros = _aplicar_filtros_clientes(base_qs, request, incluir_assessor=True)

    if pode_gerenciar_todos:
        meus_clientes = listar_clientes(request.user)
    elif consultor:
        meus_clientes = base_qs.filter(
            Q(assessor_responsavel=consultor) |
            Q(cliente_principal__assessor_responsavel=consultor)
        ).distinct()
    else:
        meus_clientes = base_qs.none()

    meus_clientes, _ = _aplicar_filtros_clientes(meus_clientes, request, incluir_assessor=True)

    def _build_item(cliente):
        status_financeiro = _obter_status_financeiro_cliente(cliente)
        status_formulario = _obter_status_formulario_cliente(cliente)
        return {
            "cliente": cliente,
            "status_financeiro": status_financeiro,
            "status_formulario": status_formulario["status"],
            "total_perguntas": status_formulario["total_perguntas"],
            "total_respostas": status_formulario["total_respostas"],
            "completo": status_formulario["completo"],
            "pode_editar": usuario_pode_editar_cliente(request.user, consultor, cliente),
        }

    principais = [c for c in meus_clientes if not c.cliente_principal_id]
    dependentes = [c for c in meus_clientes if c.cliente_principal_id]
    principais.sort(key=lambda c: c.pk)
    dependentes.sort(key=lambda c: c.pk)

    clientes_com_status = []
    for principal in principais:
        clientes_com_status.append(_build_item(principal))
        for dep in dependentes:
            if dep.cliente_principal_id == principal.pk:
                clientes_com_status.append(_build_item(dep))

    processos_display = []
    for c in meus_clientes:
        for proc in Processo.objects.filter(cliente=c).select_related(
            "viagem", "viagem__pais_destino", "viagem__tipo_visto", "assessor_responsavel"
        ).prefetch_related("etapas", "etapas__status"):
            processos_display.append({
                "cliente_pk": c.pk,
                "processo_pk": proc.pk,
                "cliente_nome": c.nome,
                "viagem_str": str(proc.viagem),
                "pais_destino": proc.viagem.pais_destino.nome if proc.viagem and proc.viagem.pais_destino else "",
                "progresso": proc.progresso_percentual,
                "assessor": proc.assessor_responsavel.nome if proc.assessor_responsavel else "",
                "pode_editar": pode_gerenciar_todos,
            })

    assessores = UsuarioConsultoria.objects.filter(ativo=True).order_by("nome")

    return render(request, "client/home_clientes.html", {
        "total_clientes": meus_clientes.count(),
        "clientes_com_status": clientes_com_status,
        "perfil_usuario": perfil_usuario,
        "pode_excluir_clientes": pode_gerenciar_todos,
        "filtros": filtros,
        "assessores": assessores,
        "processos": processos_display,
    })


@login_required
def listar_clientes_view(request):
                                                          
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
                                                        
    clientes = ClienteConsultoria.objects.select_related(
        "assessor_responsavel",
        "criado_por",
        "assessor_responsavel__perfil",
        "cliente_principal",
        "cliente_principal__assessor_responsavel",
        "parceiro_indicador",
    ).prefetch_related("dependentes", "viagens").order_by("-criado_em")
    
                                                    
    clientes, filtros = _aplicar_filtros_clientes(clientes, request, incluir_assessor=True)
    
    def _build_item(cliente):
        status_financeiro = _obter_status_financeiro_cliente(cliente)
        status_formulario = _obter_status_formulario_cliente(cliente)
        return {
            "cliente": cliente,
            "status_financeiro": status_financeiro,
            "status_formulario": status_formulario["status"],
            "total_perguntas": status_formulario["total_perguntas"],
            "total_respostas": status_formulario["total_respostas"],
            "completo": status_formulario["completo"],
            "pode_editar": usuario_pode_editar_cliente(request.user, consultor, cliente),
        }

    principais = [c for c in clientes if not c.cliente_principal_id]
    dependentes = [c for c in clientes if c.cliente_principal_id]
    principais.sort(key=lambda c: c.pk)
    dependentes.sort(key=lambda c: c.pk)

    clientes_com_status = []
    for principal in principais:
        clientes_com_status.append(_build_item(principal))
        for dep in dependentes:
            if dep.cliente_principal_id == principal.pk:
                clientes_com_status.append(_build_item(dep))

    progressos = []
    for c in clientes:
        for proc in Processo.objects.filter(cliente=c):
            progressos.append({
                'cliente_pk': c.pk,
                'processo_pk': proc.pk,
                'progresso': proc.progresso_percentual,
            })
    
    return render(request, "client/listar_clientes.html", {
        "clientes_com_status": clientes_com_status,
        "assessores": UsuarioConsultoria.objects.filter(ativo=True).order_by("nome"),
        "perfil_usuario": consultor.perfil.nome if consultor and consultor.perfil else None,
        "pode_excluir_clientes": pode_gerenciar_todos,
        "filtros": filtros,
        "progressos": progressos,
    })


                                                                              
                                                                   
                                                                              

def _obter_etapa_atual(etapas, etapa_id: str | None) -> EtapaCadastroCliente:
       
                                                                            
    
         
                                                
                                                 
    
            
                                                                                   
       
    etapa_atual = etapas.first()
    if etapa_id:
        with suppress(ValueError, EtapaCadastroCliente.DoesNotExist):
            etapa_atual = etapas.get(pk=int(etapa_id))
    return etapa_atual


def _obter_dados_temporarios_sessao(request) -> dict:
       
                                                                
    
                                                                                    
                                                                             
    
         
                                         
    
            
                                                                
       
    return request.session.get("cliente_dados_temporarios", {})


def _serializar_dados_para_sessao(dados: dict, preservar_confirmar_senha: bool = False) -> dict:
       
                                                 
    
                                                                                 
                         
    
         
                                                           
                                                                                            
    
            
                                               
       
    dados_serializados = {}
    for campo, valor in dados.items():
                                                                              
        if campo == 'confirmar_senha' and not preservar_confirmar_senha:
            continue
        elif hasattr(valor, 'pk'):
            dados_serializados[campo] = valor.pk
        elif hasattr(valor, 'id'):
            dados_serializados[campo] = valor.id
        elif isinstance(valor, (date, datetime)):
            dados_serializados[campo] = valor.isoformat()
        else:
            dados_serializados[campo] = valor
    
    return dados_serializados


def _salvar_dados_temporarios_sessao(request, dados: dict):
       
                                                 
    
                                                                                 
                                                      
    
         
                                         
                                                     
       
    dados_serializados = _serializar_dados_para_sessao(dados)
    request.session["cliente_dados_temporarios"] = dados_serializados
    request.session.modified = True


def _limpar_dados_temporarios_sessao(request):
       
                                          
    
                                                
    
         
                                         
       
    if "cliente_dados_temporarios" in request.session:
        request.session.pop("cliente_dados_temporarios", None)
                                                                                  
                                                           
    request.session.modified = True


def _converter_valor_campo(instancia, campo_nome: str, valor):
       
                                                                                 
    
                                                                                 
    
         
                                                                  
                                           
                                                 
    
            
                                                                      
       
    if not hasattr(instancia, campo_nome):
        return valor
    
    with suppress(AttributeError, TypeError):
        field = instancia._meta.get_field(campo_nome)
                                                  
        if hasattr(field, 'remote_field') and field.remote_field and valor:
                                            
            if valor == '' or valor is None:
                return None
            related_model = field.remote_field.model
            with suppress(related_model.DoesNotExist, ValueError):
                                                         
                pk_value = int(valor) if isinstance(valor, str) and valor.isdigit() else valor
                return related_model.objects.get(pk=pk_value)
                                                  
        elif isinstance(field, (models.DateField, models.DateTimeField)) and isinstance(valor, str):
            with suppress(ValueError, AttributeError):
                if isinstance(field, models.DateTimeField):
                    if 'T' in valor or ' ' in valor:
                        return datetime.fromisoformat(valor.replace('Z', '+00:00'))
                    return datetime.combine(date.fromisoformat(valor), datetime.min.time())
                return date.fromisoformat(valor)
    
    return valor


def _aplicar_dados_ao_cliente(cliente, dados: dict, campos_excluidos: set = None):
       
                                                                        
    
         
                                                
                                                        
                                                                   
       
    if campos_excluidos is None:
        campos_excluidos = {'confirmar_senha'}
    
    for campo_nome, valor in dados.items():
        if campo_nome in campos_excluidos or not hasattr(cliente, campo_nome):
            continue
        
                                                                              
        if campo_nome == 'cliente_principal' and hasattr(cliente, 'cliente_principal_id') and cliente.cliente_principal_id:
            continue
        
                                                                                     
        with suppress(AttributeError, TypeError):
            field = cliente._meta.get_field(campo_nome)
            if hasattr(field, 'remote_field') and field.remote_field and (valor == '' or valor is None):
                                                                                                  
                continue
        
        valor_convertido = _converter_valor_campo(cliente, campo_nome, valor)
        setattr(cliente, campo_nome, valor_convertido)


def _adicionar_log_debug(request, mensagem: str, nivel: str = "info"):
       
                                            
    
                                                                                    
                                                           
    
         
                                         
                                       
                                                                 
       
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_msg = f"[{timestamp}] {mensagem}"
    
                              
    log_level = getattr(logging, nivel.upper(), logging.INFO)
    logger.log(log_level, log_msg)
    
                                                            
    if 'debug_logs_json' not in request.session:
        request.session['debug_logs_json'] = []
    request.session['debug_logs_json'].append({
        'timestamp': timestamp,
        'message': mensagem,
        'level': nivel
    })
                                      
    if len(request.session['debug_logs_json']) > 20:
        request.session['debug_logs_json'] = request.session['debug_logs_json'][-20:]
    request.session.modified = True


def _mask_value_for_log(field_name: str, value) -> str:
       
                                                       
       
    if value is None:
        return ""

    raw = str(value).strip()
    if raw == "":
        return ""

    if field_name in ("senha", "confirmar_senha"):
        return "***"

    if field_name == "cpf":
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 11:
            return f"***.***.***-{digits[-2:]}"
        if len(digits) >= 4:
            return f"***{digits[-4:]}"
        return "***"

    if field_name in ("telefone", "telefone_secundario"):
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 4:
            return f"***{digits[-4:]}"
        return "***"

    if field_name == "email":
        if "@" in raw:
            local, domain = raw.split("@", 1)
            local_mask = (local[:1] + "***") if local else "***"
            return f"{local_mask}@{domain}"
        return "***"

    if field_name == "cep":
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 8:
            return f"{digits[:5]}-***"
        return "***"

    if field_name == "bairro":
        if len(raw) <= 12:
            return raw
        return f"{raw[:7]}...{raw[-3:]}"

    if field_name == "numero":
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 3:
            return f"***{digits[-3:]}"
        return "***"

    if field_name == "complemento":
        if len(raw) <= 10:
            return raw
        return f"{raw[:6]}..."

    if field_name in ("numero_passaporte", "passaporte_numero"):
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 3:
            return f"***{digits[-3:]}"
        return "***"

    if field_name == "data_nascimento":
                                                                          
                                      
        parts = raw.split("-")
        if len(parts) == 3 and parts[0].isdigit():
            return parts[0]
        return "***"

    if field_name == "logradouro":
        if len(raw) <= 14:
            return raw
        return f"{raw[:10]}...{raw[-4:]}"

    return raw


def _resumo_campos_para_log(cleaned_data: dict, max_items: int = 10) -> str:
       
                                                         
       
    if not cleaned_data:
        return "sem_campos"

    parts: list[str] = []
    for field_name, value in cleaned_data.items():
        if field_name == "confirmar_senha":
            continue

        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue

                                                  
        if hasattr(value, "pk"):
            value = getattr(value, "pk")
        elif hasattr(value, "id") and not hasattr(value, "pk"):
            value = getattr(value, "id")

        masked = _mask_value_for_log(field_name, value)
        if masked == "":
            continue

        parts.append(f"{field_name}={masked}")
        if len(parts) >= max_items:
            break

    return ", ".join(parts) if parts else "sem_campos"


def _validar_resumo_etapa(etapa_atual, dados_atualizados: dict, form_cleaned_data: dict) -> list[str]:
       
                                                                          
                                        
       
    warnings: list[str] = []

    if getattr(etapa_atual, "campo_booleano", None):
        flag = etapa_atual.campo_booleano
        if dados_atualizados.get(flag) is not True:
            warnings.append(f"flag_sessao_nao_setada({flag})")

    cep = dados_atualizados.get("cep")
    cep_str = str(cep).strip() if cep is not None else ""
    if cep_str:
        addr_fields = ["logradouro", "bairro", "cidade", "uf"]
                                                                                  
        addr_fields_enviados = [f for f in addr_fields if f in (form_cleaned_data or {})]
        if addr_fields_enviados:
            missing = [f for f in addr_fields_enviados if not str(dados_atualizados.get(f, "")).strip()]
            if missing:
                warnings.append(f"cep_sem_endereco({','.join(missing)})")

    tipo_passaporte = dados_atualizados.get("tipo_passaporte")
    if str(tipo_passaporte).strip().lower() == "outro":
        if not str(dados_atualizados.get("tipo_passaporte_outro", "")).strip():
            warnings.append("tipo_passaporte_outro_ausente")

    return warnings


def _log_resumo_etapa_finalizada(request, etapa_atual, form_cleaned_data: dict, dados_atualizados: dict) -> None:
       
                                                                                    
       
    resumo_campos = _resumo_campos_para_log(form_cleaned_data)
    warnings = _validar_resumo_etapa(etapa_atual, dados_atualizados, form_cleaned_data)

    concluida_flag = None
    if getattr(etapa_atual, "campo_booleano", None):
        concluida_flag = dados_atualizados.get(etapa_atual.campo_booleano) is True

    mensagem = (
        f"✅ Etapa finalizada (sessao) etapa='{etapa_atual.nome}' "
        f"id={etapa_atual.pk} campo_booleano_concluido={concluida_flag} campos={resumo_campos}"
    )

    if warnings:
        logger.warning(mensagem + f" | avisos={';'.join(warnings)}")
    else:
        logger.info(mensagem)

                                                      
    _adicionar_log_debug(request, f"Etapa finalizada: {etapa_atual.nome}")


def _criar_cliente_da_sessao(request) -> ClienteConsultoria | None:
       
                                                                                     
    
                                                                                 
    
         
                                         
    
            
                                                                                   
       
    dados_temporarios = _obter_dados_temporarios_sessao(request)
    if not dados_temporarios:
        return None
    
    try:
        cliente = ClienteConsultoria()
        _aplicar_dados_ao_cliente(cliente, dados_temporarios)
        return cliente
    except Exception:
        return None


def _configurar_campos_formulario(form, etapa_atual):
                                                                                 
    campos_etapa_dict = {
        campo.nome_campo: campo
        for campo in CampoEtapaCliente.objects.filter(
            etapa=etapa_atual, ativo=True
        ).order_by("ordem", "nome_campo")
    }
    for field_name, field in form.fields.items():
        campo_config = campos_etapa_dict.get(field_name)
                                                                           
                                                                                     
        field.required = campo_config.obrigatorio if campo_config else False


def _salvar_etapa_na_sessao(form, etapa_atual, request):
       
                                                       
    
                                                                       
                                                                       
    
         
                                             
                                               
                                         
    
          
                                                              
       
                                      
    dados_existentes = _obter_dados_temporarios_sessao(request)
    
                                           
    dados_atualizados = dados_existentes.copy()
    dados_atualizados.update(form.cleaned_data)
    
                                        
                                       
                                                                          
                                                                                  
    assessor_existente = dados_existentes.get('assessor_responsavel')
    assessor_cleaned = form.cleaned_data.get('assessor_responsavel')
    
                                                         
    assessor_cleaned_id = None
    if assessor_cleaned:
        if hasattr(assessor_cleaned, 'pk'):
            assessor_cleaned_id = assessor_cleaned.pk
        elif isinstance(assessor_cleaned, (int, str)) and str(assessor_cleaned).strip():
            try:
                assessor_cleaned_id = int(assessor_cleaned)
            except (ValueError, TypeError):
                assessor_cleaned_id = None
    
                                                          
    if assessor_existente and not assessor_cleaned_id:
        dados_atualizados['assessor_responsavel'] = assessor_existente
        logger.debug(f"🔒 Preservando assessor_responsavel da sessão: {assessor_existente}")
    
                                 
    if etapa_atual.campo_booleano:
        dados_atualizados[etapa_atual.campo_booleano] = True

                                                    
    _salvar_dados_temporarios_sessao(request, dados_atualizados)

                                                         
    _log_resumo_etapa_finalizada(request, etapa_atual, form.cleaned_data, dados_atualizados)


def _avancar_para_proxima_etapa(etapa_atual, etapas, request_path, request):
       
                                                                
    
         
                                               
                                           
                                                 
                                           
    
            
                                                                           
       
    if proxima_etapa := etapas.filter(ordem__gt=etapa_atual.ordem).first():
        messages.success(request, f"Etapa '{etapa_atual.nome}' concluída!")
        return redirect(f"{request_path}?etapa_id={proxima_etapa.pk}")
    
                                                         
    if etapa_atual.campo_booleano == 'etapa_membros':
        messages.success(request, f"Etapa '{etapa_atual.nome}' concluída! Você pode adicionar dependentes abaixo.")
        return redirect(f"{request_path}?etapa_id={etapa_atual.pk}")
    
    return None


def _criar_dependente_do_banco(
    dados_dependente: dict,
    cliente_principal: ClienteConsultoria,
    user,
) -> tuple[ClienteConsultoria | None, str | None]:
       
                                                                               
    
         
                                                            
                                                       
                                      
    
            
                                                                   
       
    nome_dependente = dados_dependente.get('nome', 'Desconhecido')
    cpf_dependente = dados_dependente.get('cpf', '')

    try:
        logger.info(f"📝 Criando dependente: {nome_dependente} (cpf: {cpf_dependente}) para cliente principal: {cliente_principal.nome}")

        if cpf_dependente:
            cpf_digits = "".join(c for c in cpf_dependente if c.isdigit())
            cpf_fmt = f"{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}" if len(cpf_digits) == 11 else cpf_dependente
            digits_only = cpf_digits
            if cliente_existente := ClienteConsultoria.objects.filter(cpf__in=[digits_only, cpf_fmt]).first():
                if cliente_existente.pk != cliente_principal.pk and cliente_existente.cliente_principal_id != cliente_principal.pk:
                    logger.error(f"❌ CPF {cpf_dependente} já está em uso por outro cliente: {cliente_existente.nome}")
                    return None, "Este CPF já está cadastrado."

                                                                                                             
        usar_dados_principal = dados_dependente.get('usar_dados_cliente_principal', False)
        
                                                                              
        if 'senha' in dados_dependente and dados_dependente.get('senha') and 'confirmar_senha' not in dados_dependente:
            dados_dependente['confirmar_senha'] = dados_dependente['senha']
            logger.info("🔧 Adicionando confirmar_senha aos dados do dependente (usando valor da senha)")
        
        form_dependente = ClienteConsultoriaForm(data=dados_dependente, instance=None, user=user, cliente_principal=cliente_principal, usar_dados_principal=usar_dados_principal)
        if not form_dependente.is_valid():
                                                                        
            erro_msg = None
            if "cpf" in form_dependente.errors and form_dependente.errors["cpf"]:
                erro_msg = form_dependente.errors["cpf"][0]
            elif form_dependente.errors:
                _, erros = next(iter(form_dependente.errors.items()))
                erro_msg = erros[0] if erros else None

            logger.error(f"❌ Formulário de dependente inválido para {nome_dependente}: {form_dependente.errors}")
            return None, erro_msg or "Falha ao validar os dados do dependente."
        
        dependente = form_dependente.save(commit=False)
        
                                                                       
                                                        
        dependente.cliente_principal_id = cliente_principal.pk
        dependente.assessor_responsavel = cliente_principal.assessor_responsavel
        dependente.parceiro_indicador = cliente_principal.parceiro_indicador
        dependente.criado_por = user
        
        logger.info(f"🔗 Vinculando dependente {nome_dependente} ao cliente principal {cliente_principal.nome} (ID: {cliente_principal.pk})")
        
                                                                                          
        dados_dependente_sem_principal = {k: v for k, v in dados_dependente.items() if k != 'cliente_principal'}
        _aplicar_dados_ao_cliente(dependente, dados_dependente_sem_principal)
        
                                                                                      
        if dados_dependente.get('usar_dados_endereco_cliente_principal', False):
            dependente.cep = cliente_principal.cep
            dependente.logradouro = cliente_principal.logradouro
            dependente.numero = cliente_principal.numero
            dependente.complemento = cliente_principal.complemento
            dependente.bairro = cliente_principal.bairro
            dependente.cidade = cliente_principal.cidade
            dependente.uf = cliente_principal.uf

                                                                                
        if dependente.cliente_principal_id != cliente_principal.pk:
            logger.error("❌ ERRO CRÍTICO: cliente_principal foi sobrescrito! Corrigindo...")
            dependente.cliente_principal_id = cliente_principal.pk
        
                                                                                         
        if usar_dados_principal:
                                                                                           
            dependente.email = ""
            dependente.senha = ""
        else:
                                                                               
                                                                     
            dependente.email = dados_dependente.get("email", "") or ""
            if senha_raw := dados_dependente.get("senha"):
                dependente.set_password(senha_raw)
        
                                                       
        primeira_etapa = EtapaCadastroCliente.objects.filter(ativo=True).order_by("ordem").first()
        if primeira_etapa and primeira_etapa.campo_booleano:
            setattr(dependente, primeira_etapa.campo_booleano, True)
        
                         
        dependente.save()
        
                                             
        dependente_refreshed = ClienteConsultoria.objects.get(pk=dependente.pk)
        if dependente_refreshed.cliente_principal_id != cliente_principal.pk:
            logger.error(f"❌ ERRO CRÍTICO: Dependente {nome_dependente} não está vinculado após salvar! cliente_principal_id={dependente_refreshed.cliente_principal_id}")
            return None, "Erro interno ao vincular dependente ao principal."
        
        logger.info(f"✅ Dependente {nome_dependente} salvo com sucesso (ID: {dependente.pk}, cliente_principal_id: {dependente.cliente_principal_id})")
        return dependente, None
    except Exception as e:
        logger.error(f"❌ Erro ao salvar dependente {nome_dependente}: {str(e)}", exc_info=True)
        return None, str(e)


def _marcar_etapas_concluidas(cliente: ClienteConsultoria, dados_temporarios: dict):
                                                                                   
    etapas_booleanas = ['etapa_dados_pessoais', 'etapa_endereco', 'etapa_passaporte', 'etapa_membros']
    for campo_booleano in etapas_booleanas:
        if dados_temporarios.get(campo_booleano):
            setattr(cliente, campo_booleano, True)


def _processar_dependentes_temporarios(request, cliente: ClienteConsultoria) -> int:
       
                                                       
    
         
                                         
                                             
    
            
                                                     
       
    dependentes_temporarios = request.session.get("dependentes_temporarios", [])
    if not dependentes_temporarios:
        logger.info(f"ℹ️ Nenhum dependente temporário encontrado na sessão para cliente {cliente.nome}")
        return 0
    
    logger.info(f"📦 Processando {len(dependentes_temporarios)} dependente(s) temporário(s) para cliente {cliente.nome}")
    dependentes_salvos = 0
    dependentes_com_erro: list[str] = []
    
    for idx, dados_dependente in enumerate(dependentes_temporarios):
        nome = dados_dependente.get('nome', 'Desconhecido')
        cpf = dados_dependente.get('cpf', '')

        logger.info(f"🔄 Processando dependente {idx + 1}/{len(dependentes_temporarios)}: {nome} (cpf: {cpf})")
        logger.info(f"📋 Dados do dependente: {dados_dependente}")

        if not nome:
            logger.error(f"❌ Dependente {idx + 1} não tem nome - pulando")
            dependentes_com_erro.append(f"Dependente {idx + 1} (sem nome)")
            continue

        if not cpf:
            logger.error(f"❌ Dependente {nome} não tem CPF - pulando (CPF é obrigatório e único)")
            dependentes_com_erro.append(f"{nome} (sem CPF)")
            continue
        
                                    
        try:
            dependente, erro_msg = _criar_dependente_do_banco(dados_dependente, cliente, request.user)
            if dependente:
                dependentes_salvos += 1
                                                                       
                dependente.refresh_from_db()
                if dependente.cliente_principal_id == cliente.pk:
                    logger.info(f"✅ Dependente {nome} salvo com sucesso (ID: {dependente.pk}, cliente_principal_id: {dependente.cliente_principal_id})")
                else:
                    logger.error(f"❌ ERRO CRÍTICO: Dependente {nome} não está vinculado corretamente! cliente_principal_id={dependente.cliente_principal_id}, esperado={cliente.pk}")
                                     
                    dependente.cliente_principal_id = cliente.pk
                    dependente.save(update_fields=['cliente_principal'])
                    logger.info(f"✅ Relacionamento corrigido para dependente {nome}")
            else:
                dependentes_com_erro.append(nome)
                logger.error(f"❌ Falha ao salvar dependente: {nome}")
                if erro_msg:
                    messages.error(request, f"Dependente '{nome}': {erro_msg}")
                else:
                    messages.error(request, f"Dependente '{nome}': Falha ao salvar.")
                _adicionar_log_debug(request, f"Erro ao salvar dependente: {nome} ({erro_msg})")
        except Exception as e:
            dependentes_com_erro.append(nome)
            logger.error(f"❌ Exceção ao salvar dependente {nome}: {str(e)}", exc_info=True)
            _adicionar_log_debug(request, f"Exceção ao salvar dependente {nome}: {str(e)}")
    
                                              
                                                                           
                                                               
    if dependentes_com_erro:
        logger.warning(f"⚠️ {len(dependentes_com_erro)} dependente(s) não foram salvos: {', '.join(dependentes_com_erro)}")
        raise DependentesNaoValidosError("Falha ao salvar dependentes. Verifique os erros e tente novamente.")

    request.session.pop("dependentes_temporarios", None)

    logger.info(f"📊 Total de dependentes salvos: {dependentes_salvos}/{len(dependentes_temporarios)}")
    return dependentes_salvos


def _recuperar_assessor_dos_dados_temporarios(dados_temporarios: dict) -> UsuarioConsultoria | None:
                                                                                 
    if not (assessor_id_temp := dados_temporarios.get('assessor_responsavel')):
        return None
    
    try:
        if isinstance(assessor_id_temp, str) and assessor_id_temp.strip():
            assessor_id_temp = int(assessor_id_temp)
        elif not isinstance(assessor_id_temp, int):
            return None
        
        return UsuarioConsultoria.objects.filter(pk=assessor_id_temp, ativo=True).first()
    except (ValueError, TypeError) as e:
        logger.warning(f"⚠️ Erro ao converter assessor_responsavel dos dados temporários: {e}")
        return None


def _definir_assessor_com_log(cliente: ClienteConsultoria, assessor: UsuarioConsultoria, origem: str) -> None:
                                                      
    cliente.assessor_responsavel = assessor
    logger.info(f"✅ Assessor {origem}: {assessor.nome} (ID: {assessor.pk})")


def _garantir_assessor_responsavel(cliente: ClienteConsultoria, dados_temporarios: dict, user) -> None:
                                                                       
    if cliente.assessor_responsavel_id:
        return
    
    if assessor := _recuperar_assessor_dos_dados_temporarios(dados_temporarios):
        _definir_assessor_com_log(cliente, assessor, "recuperado dos dados temporários")
        return
    
    if consultor := obter_consultor_usuario(user):
        _definir_assessor_com_log(cliente, consultor, "definido a partir do usuário logado")
        return
    
    logger.error(f"❌ Não foi possível determinar o assessor. Dados temporários: assessor_responsavel={dados_temporarios.get('assessor_responsavel')}")
    raise ValueError("Não foi possível determinar o assessor responsável. Por favor, selecione um assessor na primeira etapa.")


def _processar_e_logar_dependentes(request, cliente: ClienteConsultoria) -> int:
                                                                       
    logger.info("🔍 Verificando dependentes temporários na sessão antes de processar...")
    dependentes_temporarios_antes = request.session.get("dependentes_temporarios", [])
    logger.info(f"📋 Dependentes temporários encontrados na sessão: {len(dependentes_temporarios_antes)}")
    if dependentes_temporarios_antes:
        logger.info(f"📋 Conteúdo dos dependentes temporários: {dependentes_temporarios_antes}")
    
    dependentes_salvos = _processar_dependentes_temporarios(request, cliente)
    
    if dependentes_salvos > 0:
        logger.info(f"✅ {dependentes_salvos} dependente(s) vinculado(s) ao cliente {cliente.nome}")
        _adicionar_log_debug(request, f"{dependentes_salvos} dependente(s) vinculado(s) ao cliente")
    else:
        logger.warning(f"⚠️ Nenhum dependente foi salvo para o cliente {cliente.nome}")
        if dependentes_temporarios_antes:
            logger.error(f"❌ Havia {len(dependentes_temporarios_antes)} dependente(s) na sessão, mas nenhum foi salvo!")
    
    return dependentes_salvos


def _validar_dados_temporarios(dados_temporarios: dict | None) -> None:
                                                   
    if not dados_temporarios:
        raise ValueError("Dados não encontrados na sessão. Por favor, inicie o cadastro novamente.")


def _criar_e_configurar_cliente(dados_temporarios: dict, user) -> ClienteConsultoria:
                                                                      
    cliente = ClienteConsultoria()
    _aplicar_dados_ao_cliente(cliente, dados_temporarios)
    cliente.criado_por = user
    _garantir_assessor_responsavel(cliente, dados_temporarios, user)
    return cliente


def _configurar_senha_e_etapas(cliente: ClienteConsultoria, dados_temporarios: dict) -> None:
                                                         
    if senha := dados_temporarios.get('senha'):
        cliente.set_password(senha)
    _marcar_etapas_concluidas(cliente, dados_temporarios)


def _salvar_e_logar_cliente(request, cliente: ClienteConsultoria) -> None:
                                                              
    with transaction.atomic():
        cliente.save()
        dependentes_salvos = _processar_e_logar_dependentes(request, cliente)

    etapas_confirmadas = {}
    for campo_booleano in ("etapa_dados_pessoais", "etapa_endereco", "etapa_passaporte", "etapa_membros"):
        if hasattr(cliente, campo_booleano):
            etapas_confirmadas[campo_booleano] = bool(getattr(cliente, campo_booleano))

    logger.info(
        f"✅ Cliente '{cliente.nome}' salvo no banco (ID: {cliente.pk}) "
        f"dependentes_salvos={dependentes_salvos} etapas_confirmadas={etapas_confirmadas}"
    )
    _adicionar_log_debug(request, f"Cliente '{cliente.nome}' salvo no banco (ID: {cliente.pk})")
    request.session.modified = True


def _criar_cliente_do_banco(request) -> ClienteConsultoria:
       
                                                                          
    
                                                                                
                                                                                     
                              
    
         
                                                                       
    
            
                                                  
    
           
                                                             
    
          
                                                                         
       
    dados_temporarios = _obter_dados_temporarios_sessao(request)
    _validar_dados_temporarios(dados_temporarios)
    
    cliente = _criar_e_configurar_cliente(dados_temporarios, request.user)
    _configurar_senha_e_etapas(cliente, dados_temporarios)
    _salvar_e_logar_cliente(request, cliente)
    
    return cliente


def _obter_ids_clientes_com_dependentes(cliente: ClienteConsultoria) -> list:
                                                             
    clientes_ids = [cliente.pk]
    dependentes = ClienteConsultoria.objects.filter(cliente_principal=cliente)
    clientes_ids.extend(dependentes.values_list('pk', flat=True))
    return clientes_ids


def _criar_redirect_viagem_com_clientes(request, cliente: ClienteConsultoria):
                                                                        
    logger.info(f"🚀 Redirecionando para criar viagem com cliente {cliente.nome} (ID: {cliente.pk})")
                                                         
    clientes_ids = _obter_ids_clientes_com_dependentes(cliente)
    redirect_url = f"{reverse('system:criar_viagem')}?clientes={','.join(map(str, clientes_ids))}"
    logger.info(f"✅ Redirect para criar viagem: {redirect_url}")
    _adicionar_log_debug(request, f"Redirecionando para criar viagem com {len(clientes_ids)} cliente(s)")
    return redirect(redirect_url)


def _finalizar_cadastro_cliente(request, cliente: ClienteConsultoria, criar_viagem: bool = False):
       
                                                                                         
    
                
                                                 
                                
                                                                                        
    
         
                                         
                                                  
                                                                                          
    
            
                                                         
    
          
                                                                      
       
                                                                        
                                                                  
    flag_key = f'cadastro_finalizado_{cliente.pk}'
    if request.session.get(flag_key, False):
                                                                                                      
        logger.info(f"⚠️ Tentativa de finalizar cadastro duplicada para cliente {cliente.pk} - redirecionando sem mensagem")
        if criar_viagem:
                                                                 
            clientes_ids = _obter_ids_clientes_com_dependentes(cliente)
            return redirect(f"{reverse('system:criar_viagem')}?clientes={','.join(map(str, clientes_ids))}")
        return redirect("system:home_clientes")
    
                                                                                                                  
    request.session[flag_key] = True
    request.session.modified = True
    
                                                                
    num_dependentes = ClienteConsultoria.objects.filter(cliente_principal=cliente).count()
    
                            
    _adicionar_log_debug(request, f"Cadastro finalizado com sucesso! Cliente: {cliente.nome}, Dependentes: {num_dependentes}")
    
                                                                           
    if "cliente_dados_temporarios" in request.session:
        request.session.pop("cliente_dados_temporarios", None)
    if "dependentes_temporarios" in request.session:
        request.session.pop("dependentes_temporarios", None)
                                                         
    request.session.modified = True
    
                                                           
    if num_dependentes > 0:
        messages.success(
            request, 
            f"✅ Cadastro finalizado com sucesso! Cliente '{cliente.nome}' e {num_dependentes} dependente(s) foram cadastrados. O cliente foi salvo no sistema e está disponível na lista de clientes."
        )
    else:
        messages.success(
            request, 
            f"✅ Cadastro finalizado com sucesso! Cliente '{cliente.nome}' foi cadastrado. O cliente foi salvo no sistema e está disponível na lista de clientes."
        )
    
                                                              
    request.session.modified = True
    
                                                                                            
    if criar_viagem:
        return _criar_redirect_viagem_com_clientes(request, cliente)
    
                                        
    redirect_url_name = "system:home_clientes"
    _adicionar_log_debug(request, f"Redirecionando para: {redirect_url_name}")
    logger.info(f"Finalizando cadastro - criando redirect para: {redirect_url_name}")
    
                                         
    redirect_response = redirect(redirect_url_name)
    
                                                     
    if hasattr(redirect_response, 'url'):
        logger.info(f"✅ Redirect criado com sucesso - URL: {redirect_response.url}")
        _adicionar_log_debug(request, f"Redirect criado - URL: {redirect_response.url}")
    else:
        logger.warning(f"⚠️ Redirect criado mas sem atributo 'url' - Tipo: {type(redirect_response)}")
        _adicionar_log_debug(request, f"Redirect criado - Tipo: {type(redirect_response)}", "warning")
    
    return redirect_response


def _preparar_contexto(etapas, etapa_atual, campos_etapa, form, cliente, consultor):
                                                           
    etapas_lista = list(etapas)
    etapa_index = next(
        (i for i, e in enumerate(etapas_lista) if e.pk == etapa_atual.pk), 0
    )
    etapa_anterior = etapas_lista[etapa_index - 1] if etapa_index > 0 else None
    proxima_etapa = (
        etapas_lista[etapa_index + 1]
        if etapa_index < len(etapas_lista) - 1
        else None
    )
    
    return {
        "form": form,
        "etapa_atual": etapa_atual,
        "etapas": etapas_lista,
        "etapa_anterior": etapa_anterior,
        "proxima_etapa": proxima_etapa,
        "campos_etapa": campos_etapa,
        "cliente": cliente,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }


def _exibir_erros_formulario(request, form, campos_etapa_nomes, prefixo="", etapa_nome: str | None = None):
                                                                         
    if "senha" in campos_etapa_nomes:
        campos_etapa_nomes.add("confirmar_senha")

                                                                    
    if etapa_nome:
        erros_resumidos: list[str] = []
        for field_name, errors in form.errors.items():
            if field_name in campos_etapa_nomes and errors:
                erros_resumidos.append(f"{field_name}={str(errors[0])[:120]}")
        if erros_resumidos:
            logger.warning(f"❌ Form invalido (etapa='{etapa_nome}') erros={', '.join(erros_resumidos)}")
    
    for field_name, errors in form.errors.items():
        if field_name in campos_etapa_nomes:
            field_label = form.fields[field_name].label if field_name in form.fields else field_name
            for error in errors:
                messages.error(request, f"{prefixo}{field_label}: {error}")

def _obter_assessor_id_dependente(request, cliente, dados_temporarios):
                                                                 
    assessor_id = None
    
                                                    
    if hasattr(cliente, 'assessor_responsavel_id') and cliente.assessor_responsavel_id:
        assessor_id = cliente.assessor_responsavel_id
                                                 
    elif dados_temporarios and (assessor_valor := dados_temporarios.get('assessor_responsavel')):
                                          
        try:
            assessor_id = int(assessor_valor) if isinstance(assessor_valor, str) else assessor_valor
        except (ValueError, TypeError):
            assessor_id = None
    
                                                       
    if not assessor_id:
        if consultor := obter_consultor_usuario(request.user):
            assessor_id = consultor.pk
    
    return assessor_id


def _preparar_dados_iniciais_dependente(request, assessor_id):
                                                                 
    dependente_editando_dados = request.session.get('dependente_editando_dados')
    dados_iniciais = None
    usar_dados_principal_edit = False
    
    if dependente_editando_dados:
                                                    
        dados_iniciais = dependente_editando_dados.copy()
        usar_dados_principal_edit = dependente_editando_dados.get('usar_dados_cliente_principal', False)
        logger.info(f"📝 Carregando dados do dependente para edição: {dados_iniciais.get('nome', 'Desconhecido')}")
                                                                                    
        if assessor_id and ('assessor_responsavel' not in dados_iniciais or not dados_iniciais.get('assessor_responsavel')):
            dados_iniciais['assessor_responsavel'] = assessor_id
    elif assessor_id:
                                                                      
        dados_iniciais = {'assessor_responsavel': assessor_id}
    
    return dados_iniciais, usar_dados_principal_edit


def _preencher_campos_endereco_dependente(form_dependente, cliente, dados_temporarios):
                                                                  
    campos_endereco = ['cep', 'logradouro', 'numero', 'complemento', 'bairro', 'cidade', 'uf']
    for campo in campos_endereco:
        if campo in form_dependente.fields:
                                                            
            if hasattr(cliente, campo) and (valor := getattr(cliente, campo)):
                form_dependente.fields[campo].initial = valor
                                                         
            elif dados_temporarios and (valor := dados_temporarios.get(campo)):
                form_dependente.fields[campo].initial = valor


def _configurar_campos_formulario_dependente(form_dependente, primeira_etapa, etapas):
                                                                          
    if not etapas:
                                              
        _configurar_campos_formulario(form_dependente, primeira_etapa)
        return
    
                                                                  
    etapas_dependente = etapas.filter(ativo=True).exclude(campo_booleano='etapa_membros').order_by("ordem")
    campos_dependente = set()
    for etapa in etapas_dependente:
        campos_etapa = CampoEtapaCliente.objects.filter(etapa=etapa, ativo=True).exclude(nome_campo="parceiro_indicador")
        campos_dependente.update(campos_etapa.values_list("nome_campo", flat=True))
    
                                                                     
    campos_primeira_etapa_dict = {
        campo.nome_campo: campo
        for campo in CampoEtapaCliente.objects.filter(etapa=primeira_etapa, ativo=True)
    }

    for field_name, field in form_dependente.fields.items():
                                                     
                                                                
        if campo_config := campos_primeira_etapa_dict.get(field_name):
            field.required = campo_config.obrigatorio
        elif field_name in campos_dependente:
                                                        
            field.required = False


def _criar_formulario_dependente(request, cliente, primeira_etapa, etapas=None):
       
                                                            
    
                     
                                     
                                                                
                                         
       
                                                                           
    cliente_principal = cliente if isinstance(cliente, ClienteConsultoria) and cliente.is_principal else None
    
                                           
    dados_temporarios = _obter_dados_temporarios_sessao(request)
    assessor_id = _obter_assessor_id_dependente(request, cliente, dados_temporarios)
    
                             
    dados_iniciais, usar_dados_principal_edit = _preparar_dados_iniciais_dependente(request, assessor_id)
    
                      
    form_dependente = ClienteConsultoriaForm(
        data=None,
        initial=dados_iniciais,
        user=request.user,
        cliente_principal=cliente_principal,
        usar_dados_principal=usar_dados_principal_edit
    )
    
                                                                     
    if assessor_id:
        form_dependente.fields["assessor_responsavel"].initial = assessor_id
    
                                                            
    if "parceiro_indicador" in form_dependente.fields:
        del form_dependente.fields["parceiro_indicador"]
    
                                  
    _preencher_campos_endereco_dependente(form_dependente, cliente, dados_temporarios)
    
                                     
    _configurar_campos_formulario_dependente(form_dependente, primeira_etapa, etapas)
    
    return form_dependente

def _remover_parceiro_indicador(form):
                                                                
    if "parceiro_indicador" in form.fields:
        del form.fields["parceiro_indicador"]


def _tornar_senha_opcional(form):
                                                        
    if 'senha' in form.fields:
        form.fields['senha'].required = False
    if 'confirmar_senha' in form.fields:
        form.fields['confirmar_senha'].required = False


def _preparar_formulario_dependente_post(request, primeira_etapa, etapas=None, cliente_principal=None):
                                                                  
    usar_dados_principal = request.POST.get('usar_dados_cliente_principal') == 'on'
    
                                                                     
    form = ClienteConsultoriaForm(
        data=request.POST,
        user=request.user,
        cliente_principal=cliente_principal,
        usar_dados_principal=usar_dados_principal
    )
    _remover_parceiro_indicador(form)

                                                                   
    if usar_dados_principal:
        _tornar_senha_opcional(form)
    
                                     
    _configurar_campos_formulario_dependente(form, primeira_etapa, etapas)
    
                                                                                                
    if usar_dados_principal:
        _tornar_senha_opcional(form)
    
    return form


def _salvar_dependente(form, cliente_principal, primeira_etapa, user, usar_dados_principal=False):
                                                             
    dependente = form.save(commit=False)
    dependente.cliente_principal = cliente_principal
    dependente.assessor_responsavel = cliente_principal.assessor_responsavel
                                                                  
    dependente.parceiro_indicador = cliente_principal.parceiro_indicador
    if not dependente.criado_por_id:
        dependente.criado_por = user

                                                                                   
    if usar_dados_principal:
        dependente.email = ""
        dependente.senha = ""
    
    dependente.save()
    
                                                   
    if primeira_etapa.campo_booleano:
        setattr(dependente, primeira_etapa.campo_booleano, True)
        dependente.save(update_fields=[primeira_etapa.campo_booleano])


def _armazenar_dependente_temporario_na_sessao(request, dados_dependente: dict):
       
                                                
    
                                                                            
                                                       
    
         
                                         
                                                                                      
    
          
                                                             
       
    nome_dependente = dados_dependente.get('nome', 'Desconhecido')
    logger.info(f"💾 Armazenando dependente temporário na sessão: {nome_dependente}")
    logger.info(f"📋 Dados do dependente antes de serializar: {dados_dependente}")
    
    dependentes_temporarios = request.session.get("dependentes_temporarios", [])
    logger.info(f"📋 Dependentes temporários existentes na sessão: {len(dependentes_temporarios)}")
    
                                                                                      
    dados_serializados = _serializar_dados_para_sessao(dados_dependente, preservar_confirmar_senha=True)
    logger.info(f"📋 Dados serializados: {dados_serializados}")
    
    dependentes_temporarios.append(dados_serializados)
    request.session["dependentes_temporarios"] = dependentes_temporarios
    request.session.modified = True
    
    logger.info(f"✅ Dependente {nome_dependente} armazenado na sessão. Total na sessão: {len(dependentes_temporarios)}")
    
    if 'debug_logs' not in request.session:
        request.session['debug_logs'] = []
    request.session['debug_logs'].append(
        f"[{datetime.now().strftime('%H:%M:%S')}] Dependente '{dados_serializados.get('nome')}' adicionado temporariamente (será salvo ao finalizar)"
    )
    request.session.modified = True


def _processar_dependente_valido(request, form_dependente_post, etapa_atual):
                                                             
    logger.info("✅ Formulário de dependente válido. Armazenando na sessão...")
    
    dados_dependente = form_dependente_post.cleaned_data.copy()
    
                                                                             
    usar_dados_principal = request.POST.get('usar_dados_cliente_principal') == 'on'
    dados_dependente['usar_dados_cliente_principal'] = usar_dados_principal
    logger.info(
        "ℹ️ Dependente configurado para %s a conta do cliente principal",
        "usar" if usar_dados_principal else "não usar",
    )

                                                                                    
    usar_dados_endereco_principal = request.POST.get('usar_dados_endereco_cliente_principal') == 'on'
    if usar_dados_endereco_principal:
        dados_dependente['usar_dados_endereco_cliente_principal'] = True
        logger.info("ℹ️ Dependente configurado para usar endereço do cliente principal")
    
                                                        
    dependente_editando_index = request.session.get('dependente_editando_index')
    if dependente_editando_index is not None:
                                        
        dependentes_temporarios = request.session.get("dependentes_temporarios", [])
        if 0 <= dependente_editando_index < len(dependentes_temporarios):
            dados_serializados = _serializar_dados_para_sessao(dados_dependente, preservar_confirmar_senha=True)
            dependentes_temporarios[dependente_editando_index] = dados_serializados
            request.session["dependentes_temporarios"] = dependentes_temporarios
                                    
            request.session.pop('dependente_editando_index', None)
            request.session.pop('dependente_editando_dados', None)
            request.session.modified = True
            nome_dependente = dados_dependente.get('nome', 'Desconhecido')
            messages.success(request, f"{nome_dependente} atualizado. Será salvo ao finalizar o cadastro.")
            logger.info(f"✅ Dependente {nome_dependente} atualizado com sucesso. Redirecionando...")
            return redirect(f"{request.path}?etapa_id={etapa_atual.pk}")
    
                               
    _armazenar_dependente_temporario_na_sessao(request, dados_dependente)
    nome_dependente = dados_dependente.get('nome', 'Desconhecido')
    messages.success(request, f"{nome_dependente} adicionado. Será salvo ao finalizar o cadastro.")
    logger.info(f"✅ Dependente {nome_dependente} adicionado com sucesso. Redirecionando...")
    return redirect(f"{request.path}?etapa_id={etapa_atual.pk}")

def _obter_cliente_principal_dependente(dados_temporarios, cliente_temporario, usar_dados_principal):
                                                                    
    cliente_principal = None
    
    if dados_temporarios and 'cliente_principal_id' in dados_temporarios:
        cliente_principal_id = dados_temporarios['cliente_principal_id']
        with suppress(ClienteConsultoria.DoesNotExist):
            cliente_principal = ClienteConsultoria.objects.get(pk=cliente_principal_id)
    elif cliente_temporario and isinstance(cliente_temporario, ClienteConsultoria) and cliente_temporario.is_principal:
        cliente_principal = cliente_temporario
    
                                                                                
    if usar_dados_principal and not cliente_principal and cliente_temporario:
        cliente_principal = cliente_temporario
    
    return cliente_principal


def _garantir_assessor_no_formulario(form_dependente_post, cliente_temporario, dados_temporarios, cliente_principal, request, primeira_etapa):
                                                                         
    if form_dependente_post.data.get('assessor_responsavel'):
        return form_dependente_post
    
                                                               
    assessor_id = _obter_assessor_id_dependente(request, cliente_temporario, dados_temporarios)
    
    if not assessor_id:
        return form_dependente_post
    
                                                
    from django.http import QueryDict
    if isinstance(form_dependente_post.data, QueryDict):
        form_data = form_dependente_post.data.copy()
        form_data['assessor_responsavel'] = str(assessor_id)
        usar_dados_principal = request.POST.get('usar_dados_cliente_principal') == 'on'
        form_dependente_post = ClienteConsultoriaForm(
            data=form_data,
            user=request.user,
            cliente_principal=cliente_principal,
            usar_dados_principal=usar_dados_principal
        )
        _remover_parceiro_indicador(form_dependente_post)
        _configurar_campos_formulario(form_dependente_post, primeira_etapa)
    
    return form_dependente_post


def _processar_cadastro_dependente(request, etapa_atual, cliente_temporario, etapas):
       
                                                             
    
                                                                            
                                                                           
                                                   
    
         
                                           
                                                                        
                                                                   
                                           
    
            
                                                                           
                                         
                                                 
       
    if not (primeira_etapa := etapas.filter(ativo=True).order_by("ordem").first()):
        return None, None
    
                                                 
    dados_temporarios = _obter_dados_temporarios_sessao(request)
    usar_dados_principal = request.POST.get('usar_dados_cliente_principal') == 'on'
    cliente_principal = _obter_cliente_principal_dependente(dados_temporarios, cliente_temporario, usar_dados_principal)
    
                         
    form_dependente_post = _preparar_formulario_dependente_post(
        request, primeira_etapa, etapas, cliente_principal=cliente_principal
    )
    
                                                       
    form_dependente_post = _garantir_assessor_no_formulario(
        form_dependente_post, cliente_temporario, dados_temporarios, cliente_principal, request, primeira_etapa
    )
    
                         
    campos_primeira_etapa = CampoEtapaCliente.objects.filter(
        etapa=primeira_etapa, ativo=True
    ).exclude(nome_campo="parceiro_indicador").order_by("ordem", "nome_campo")
    
    if form_dependente_post.is_valid():
                                                                                  
                                                                                           
        dependentes_temporarios = request.session.get("dependentes_temporarios", [])
        dependente_editando_index = request.session.get("dependente_editando_index")

        cpf_novo = form_dependente_post.cleaned_data.get("cpf", "") or ""
        cpf_novo_digits = "".join(c for c in str(cpf_novo) if c.isdigit())

        for idx, dependente_tmp in enumerate(dependentes_temporarios):
            cpf_existente = (dependente_tmp or {}).get("cpf", "") or ""
            cpf_existente_digits = "".join(c for c in str(cpf_existente) if c.isdigit())
            if not cpf_existente_digits:
                continue
            if cpf_existente_digits == cpf_novo_digits:
                                                                    
                if dependente_editando_index is not None and idx == dependente_editando_index:
                    continue
                form_dependente_post.add_error("cpf", "Este CPF já está cadastrado.")
                return None, form_dependente_post

        return _processar_dependente_valido(request, form_dependente_post, etapa_atual), None
    
                  
    logger.error(f"❌ Formulário de dependente inválido: {form_dependente_post.errors}")
    campos_etapa_nomes = set(campos_primeira_etapa.values_list("nome_campo", flat=True))
    _exibir_erros_formulario(
        request,
        form_dependente_post,
        campos_etapa_nomes,
        prefixo="Dependente - ",
        etapa_nome=f"Dependente - {etapa_atual.nome}",
    )
    return None, form_dependente_post


def _preparar_contexto_dependentes(request, etapa_atual, cliente_temporario, etapas, contexto, form_dependente):
       
                                                                        
    
                                                                                           
    
         
                                         
                                                                        
                                                                   
                                           
                                                         
                                                                       
       
    if not (primeira_etapa := etapas.filter(ativo=True).order_by("ordem").first()):
        return
    
    campos_primeira_etapa = CampoEtapaCliente.objects.filter(
        etapa=primeira_etapa, ativo=True
    ).exclude(nome_campo="parceiro_indicador").order_by("ordem", "nome_campo")
    
                                                                                               
    if form_dependente is None:
        form_dependente = _criar_formulario_dependente(request, cliente_temporario, primeira_etapa, etapas)
    
                                             
    dependentes_temporarios = request.session.get("dependentes_temporarios", [])
    
                                                                                             
    etapas_dependente = etapas.filter(ativo=True).exclude(campo_booleano='etapa_membros').order_by("ordem")
    campos_dependente = []
    for etapa in etapas_dependente:
        campos_etapa = CampoEtapaCliente.objects.filter(
            etapa=etapa, ativo=True
        ).exclude(nome_campo="parceiro_indicador").order_by("ordem", "nome_campo")
        campos_dependente.extend(campos_etapa)
    
                                                                            
    dependente_editando_dados = request.session.get('dependente_editando_dados')
    
                                                                                           
    assessor_id = None
    if cliente_temporario and hasattr(cliente_temporario, 'assessor_responsavel_id') and cliente_temporario.assessor_responsavel_id:
        assessor_id = cliente_temporario.assessor_responsavel_id
    else:
                                            
        dados_temporarios = _obter_dados_temporarios_sessao(request)
        if dados_temporarios and (assessor_valor := dados_temporarios.get('assessor_responsavel')):
                                              
            try:
                assessor_id = int(assessor_valor) if isinstance(assessor_valor, str) else assessor_valor
            except (ValueError, TypeError):
                assessor_id = None
                                                   
        if not assessor_id:
            if consultor := obter_consultor_usuario(request.user):
                assessor_id = consultor.pk
    
    contexto['primeira_etapa'] = primeira_etapa
    contexto['campos_primeira_etapa'] = campos_primeira_etapa
    contexto['campos_dependente'] = campos_dependente                                                          
    contexto['etapas_dependente'] = etapas_dependente                           
    contexto['form_dependente'] = form_dependente
    contexto['dependentes_temporarios'] = dependentes_temporarios                        
    contexto['dependentes'] = []                                                 
    contexto['dependente_editando_dados'] = dependente_editando_dados                                                 
    contexto['assessor_id'] = assessor_id                                      


def _processar_cancelamento_cadastro(request):
       
                                                   
    
                                                                       
    
         
                                         
    
            
                                                                        
    
          
                                                     
       
                            
    _adicionar_log_debug(request, "Cadastro cancelado pelo usuário")
    
                              
    _limpar_dados_temporarios_sessao(request)
    
                                    
    if "dependentes_temporarios" in request.session:
        request.session.pop("dependentes_temporarios", None)
    
                                 
    keys_to_remove = [key for key in request.session.keys() if key.startswith('cadastro_finalizado_')]
    for key in keys_to_remove:
        request.session.pop(key, None)
    
    request.session.modified = True
    messages.info(request, "Cadastro cancelado.")
    return redirect("system:home_clientes")


def _processar_remover_dependente(request, etapa_atual):
       
                                                             
    
                                                                       
                                    
    
         
                                         
                                                                        
    
            
                                                                 
       
    try:
        dependente_index = int(request.POST.get("dependente_index", -1))
    except (ValueError, TypeError):
        dependente_index = -1
    
    if dependente_index < 0:
        messages.error(request, "Índice de dependente inválido.")
        return redirect(f"{request.path}?etapa_id={etapa_atual.pk}")
    
    dependentes_temporarios = request.session.get("dependentes_temporarios", [])
    
    if dependente_index >= len(dependentes_temporarios):
        messages.error(request, "Dependente não encontrado.")
        return redirect(f"{request.path}?etapa_id={etapa_atual.pk}")
    
    dependente_removido = dependentes_temporarios[dependente_index]
    nome_dependente = dependente_removido.get('nome', 'Desconhecido')
    
                                   
    dependentes_temporarios.pop(dependente_index)
    request.session["dependentes_temporarios"] = dependentes_temporarios
    request.session.modified = True
    
    logger.info(f"🗑️ Dependente temporário removido: {nome_dependente} (índice {dependente_index})")
    _adicionar_log_debug(request, f"Dependente '{nome_dependente}' removido temporariamente")
    messages.success(request, f"{nome_dependente} removido da lista de membros.")
    
    return redirect(f"{request.path}?etapa_id={etapa_atual.pk}")


def _processar_editar_dependente(request, etapa_atual):
       
                                                            
    
                                                             
    
         
                                         
                                                                        
    
            
                                                                                                    
       
    try:
        dependente_index = int(request.POST.get("dependente_index", -1))
    except (ValueError, TypeError):
        dependente_index = -1
    
    if dependente_index < 0:
        messages.error(request, "Índice de dependente inválido.")
        return redirect(f"{request.path}?etapa_id={etapa_atual.pk}")
    
    dependentes_temporarios = request.session.get("dependentes_temporarios", [])
    
    if dependente_index >= len(dependentes_temporarios):
        messages.error(request, "Dependente não encontrado.")
        return redirect(f"{request.path}?etapa_id={etapa_atual.pk}")
    
    dependente_para_editar = dependentes_temporarios[dependente_index]
    nome_dependente = dependente_para_editar.get('nome', 'Desconhecido')
    
                                                                         
    request.session['dependente_editando_index'] = dependente_index
    request.session['dependente_editando_dados'] = dependente_para_editar
    request.session.modified = True
    
    logger.info(f"✏️ Editando dependente {nome_dependente} (índice {dependente_index})")
    messages.info(request, f"Editando {nome_dependente}. Modifique os dados e clique em 'Salvar Alterações' para atualizar.")
    return redirect(f"{request.path}?etapa_id={etapa_atual.pk}&editando_dependente=true")


def _preparar_dados_iniciais_formulario(request, cliente_temporario):
                                                                  
    if not request.POST and cliente_temporario:
        if dados_temporarios := _obter_dados_temporarios_sessao(request):
            dados_iniciais = dados_temporarios.copy()
            dados_iniciais.pop('confirmar_senha', None)
            return dados_iniciais
    return None


def _extrair_assessor_id_sessao(dados_iniciais):
                                                                            
    if 'assessor_responsavel' not in dados_iniciais:
        return None
    
    assessor_valor = dados_iniciais['assessor_responsavel']
    if not assessor_valor:
        return None
    
    if hasattr(assessor_valor, 'pk'):
        return assessor_valor.pk
    if isinstance(assessor_valor, str) and assessor_valor.isdigit():
        return int(assessor_valor)
    return assessor_valor if isinstance(assessor_valor, int) else None


def _criar_formulario_get(request, etapa_atual, dados_iniciais):
                                                                  
    form = ClienteConsultoriaForm(data=dados_iniciais, instance=None, user=request.user)
    
    assessor_id_sessao = _extrair_assessor_id_sessao(dados_iniciais) if dados_iniciais else None
    
    if assessor_id_sessao and dados_iniciais:
        dados_iniciais['assessor_responsavel'] = assessor_id_sessao
        form = ClienteConsultoriaForm(data=dados_iniciais, instance=None, user=request.user)
        form.fields["assessor_responsavel"].initial = assessor_id_sessao
    
    _configurar_campos_formulario(form, etapa_atual)
    return form


def _limpar_flags_finalizacao(request):
                                                                                                                         
    etapa_id = request.GET.get("etapa_id")
                                                                                                                  
                                                            
    if not etapa_id and request.method == "GET" and not request.GET.get("clientes"):
        keys_to_remove = [key for key in request.session.keys() if key.startswith('cadastro_finalizado_')]
        for key in keys_to_remove:
            request.session.pop(key, None)


def _preparar_contexto_final(request, etapa_atual, cliente_temporario, etapas, contexto, form_dependente, tem_cep_na_etapa, tem_senha_na_etapa):
                                                               
    contexto['tem_cep_na_etapa'] = tem_cep_na_etapa
    contexto['tem_senha_na_etapa'] = tem_senha_na_etapa
    
    debug_logs_json = request.session.get('debug_logs_json', [])
    contexto['debug_logs_json'] = json.dumps(debug_logs_json)
    
    dados_temporarios = _obter_dados_temporarios_sessao(request)
    contexto['dados_temporarios'] = dados_temporarios
    
    if etapa_atual.campo_booleano == 'etapa_membros' and cliente_temporario:
        _preparar_contexto_dependentes(
            request, etapa_atual, cliente_temporario, etapas, contexto, form_dependente
        )
    
    return contexto


def _criar_formulario_cliente(request, etapa_atual, dados_iniciais=None):
                                                 
                                                                                       
    initial_data = {}
    if request.POST:
        dados_temporarios = _obter_dados_temporarios_sessao(request)
        if dados_temporarios and 'assessor_responsavel' in dados_temporarios:
            assessor_id = dados_temporarios.get('assessor_responsavel')
                                                     
            if assessor_id and (not request.POST.get('assessor_responsavel') or request.POST.get('assessor_responsavel') == ''):
                initial_data['assessor_responsavel'] = assessor_id
    
    form = ClienteConsultoriaForm(
        data=request.POST or dados_iniciais,
        initial=initial_data or None,
        instance=None,
        user=request.user
    )
    _configurar_campos_formulario(form, etapa_atual)
    return form


def _validar_etapa_anterior(etapa_atual, etapas, request):
                                                   
    if etapa_atual.ordem <= 1 or _obter_dados_temporarios_sessao(request):
        return None
    primeira_etapa = etapas.first()
    messages.error(request, f"Complete a etapa '{primeira_etapa.nome}' primeiro.")
    return redirect(f"{request.path}?etapa_id={primeira_etapa.pk}")


def _criar_e_validar_cliente_do_banco(request) -> ClienteConsultoria:
                                                              
    logger.info("📝 Criando cliente do banco...")
    cliente = _criar_cliente_do_banco(request)
    logger.info(f"✅ Cliente criado com sucesso: {cliente.nome} (ID: {cliente.pk})")
    
                                                           
    if not cliente.assessor_responsavel_id:
        logger.warning("⚠️ assessor_responsavel não definido, tentando definir...")
        if consultor := obter_consultor_usuario(request.user):
            cliente.assessor_responsavel = consultor
            cliente.save(update_fields=['assessor_responsavel'])
            logger.info(f"✅ assessor_responsavel definido: {consultor.nome}")
        else:
            raise ValueError("Não foi possível determinar o assessor responsável. Por favor, selecione um assessor na primeira etapa.")
    
    return cliente


def _processar_finalizacao_etapa_membros(request, etapa_atual, etapas, criar_viagem=False):
                                                               
    logger.info(f"🔄 _processar_finalizacao_etapa_membros chamada - criar_viagem={criar_viagem}")
    
    if dados_temporarios := _obter_dados_temporarios_sessao(request):
        dados_temporarios['etapa_membros'] = True
        _salvar_dados_temporarios_sessao(request, dados_temporarios)

                                                                        
        dependentes_temporarios = request.session.get("dependentes_temporarios", [])
        logger.info(
            f"🧾 Finalizacao etapa_membros (sessao) - dependentes_temporarios={len(dependentes_temporarios)} "
            f"flag_etapa_membros=True"
        )
        
        try:
            cliente = _criar_e_validar_cliente_do_banco(request)
            logger.info(f"🚀 Finalizando cadastro e redirecionando (criar_viagem={criar_viagem})...")
            return _finalizar_cadastro_cliente(request, cliente, criar_viagem)
        except DependentesNaoValidosError:
                                                                                                  
                                                                     
            return redirect(f"{request.path}?etapa_id={etapa_atual.pk}")
        except Exception as e:
            logger.error(f"❌ Erro ao finalizar cadastro: {str(e)}", exc_info=True)
            messages.error(request, str(e))
            _adicionar_log_debug(request, f"Erro ao finalizar cadastro: {str(e)}", "error")
            primeira_etapa = etapas.first()
            return redirect(f"{request.path}?etapa_id={primeira_etapa.pk}")
    
    primeira_etapa = etapas.first()
    logger.error("❌ Dados temporários não encontrados na sessão")
    messages.error(request, "Dados não encontrados. Por favor, inicie o cadastro novamente.")
    _adicionar_log_debug(request, "Tentativa de finalizar sem dados temporários na sessão", "error")
    return redirect(f"{request.path}?etapa_id={primeira_etapa.pk}")


def _processar_finalizacao_outras_etapas(request, form, etapa_atual, campos_etapa_nomes, criar_viagem=False):
                                                                
    if not form.is_valid():
        _exibir_erros_formulario(request, form, campos_etapa_nomes, etapa_nome=etapa_atual.nome)
        return None
    
    _salvar_etapa_na_sessao(form, etapa_atual, request)
    
    try:
        cliente = _criar_cliente_do_banco(request)
        redirect_response = _finalizar_cadastro_cliente(request, cliente, criar_viagem)
        _adicionar_log_debug(request, f"Redirect de finalização retornado: {redirect_response}")
        return redirect_response
    except ValueError as e:
        messages.error(request, str(e))
        _adicionar_log_debug(request, f"Erro ao finalizar cadastro: {str(e)}", "error")
        return redirect("system:home_clientes")


def _processar_finalizacao(request, form, etapa_atual, etapas, campos_etapa_nomes, form_dependente=None, criar_viagem=False):
                                           
    if etapa_atual.campo_booleano == 'etapa_membros':
        redirect_response = _processar_finalizacao_etapa_membros(request, etapa_atual, etapas, criar_viagem)
        _adicionar_log_debug(request, f"Finalização etapa_membros - Redirect retornado: {redirect_response is not None}")
        if redirect_response:
            return redirect_response, None, None
                                                                                
        return None, form, form_dependente
    
    redirect_response = _processar_finalizacao_outras_etapas(request, form, etapa_atual, campos_etapa_nomes, criar_viagem)
    _adicionar_log_debug(request, f"Finalização outras etapas - Redirect retornado: {redirect_response is not None}")
    if redirect_response:
        return redirect_response, None, None
    
                                                                                          
    return None, form, form_dependente


def _processar_avancar_etapa(request, form, etapa_atual, etapas):
                                             
                                                                                           
    if etapa_atual.campo_booleano == 'etapa_membros':
        _adicionar_log_debug(request, "Etapa 'Adicionar Membros' - permanecendo na mesma página para adicionar dependentes")
        return redirect(f"{request.path}?etapa_id={etapa_atual.pk}"), None, None
    
    _salvar_etapa_na_sessao(form, etapa_atual, request)
    
    if redirect_response := _avancar_para_proxima_etapa(etapa_atual, etapas, request.path, request):
        return redirect_response, None, None
    
                                                        
    _adicionar_log_debug(request, "Não há próxima etapa após avançar - finalizando cadastro automaticamente")
    try:
        cliente = _criar_cliente_do_banco(request)
        return _finalizar_cadastro_cliente(request, cliente), None, None
    except ValueError as e:
        messages.error(request, str(e))
        _adicionar_log_debug(request, f"Erro ao finalizar cadastro: {str(e)}", "error")
        return redirect("system:home_clientes"), None, None


def _log_finalizar_cadastro(request, etapa_atual):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"Finalizar cadastro clicado - usuario={request.user.username} etapa={etapa_atual.nome} ts={timestamp}")


def _processar_post_cadastro_cliente(request, etapa_atual, etapas, campos_etapa_nomes):
       
                                                    
    
                                                                     
                                                    
                                                     
                                                    
                                                     
    
         
                                           
                                               
                                           
                                                                 
    
            
                                                                                                          
                                                        
                                                                                   
                                                          
    
          
                                                                
       
    acao = request.POST.get("acao", "salvar")
    form_type = request.POST.get("form_type", "")
    _adicionar_log_debug(request, f"POST recebido - Ação: {acao}, Form Type: {form_type}, Etapa: {etapa_atual.nome}")
    
    if acao in ("finalizar", "finalizar_e_criar_viagem"):
        _log_finalizar_cadastro(request, etapa_atual)
    
                            
    if acao == "cancelar":
        return _processar_cancelamento_cadastro(request), None, None
    
                                     
    if acao == "remover_dependente" and etapa_atual.campo_booleano == 'etapa_membros':
        return _processar_remover_dependente(request, etapa_atual), None, None
    
    if acao == "editar_dependente":
        if etapa_atual.campo_booleano == 'etapa_membros':
            return _processar_editar_dependente(request, etapa_atual), None, None
        messages.error(request, "Ação inválida para esta etapa.")
        return redirect(f"{request.path}?etapa_id={etapa_atual.pk}"), None, None
    
                                                    
    form_dependente = None
    cliente_temporario = _criar_cliente_da_sessao(request)
    
    if (
        etapa_atual.campo_booleano == 'etapa_membros' 
        and cliente_temporario 
        and form_type == "dependente"
    ):
        redirect_response, form_dependente_result = _processar_cadastro_dependente(
            request, etapa_atual, cliente_temporario, etapas
        )
        if redirect_response:
            return redirect_response, None, None
        if form_dependente_result:
            form_dependente = form_dependente_result
    
                                 
    dados_iniciais = _preparar_dados_iniciais_formulario(request, cliente_temporario)
    form = _criar_formulario_cliente(request, etapa_atual, dados_iniciais)
    
                            
    if redirect_response := _validar_etapa_anterior(etapa_atual, etapas, request):
        return redirect_response, None, None

                                                                                     
                                                                                     
                                                                     
    if (
        etapa_atual.campo_booleano == "etapa_membros"
        and form_type == "dependente"
        and form_dependente is not None
        and form_dependente.errors
    ):
        return None, form, form_dependente
    
                                                                               
    if acao in ("finalizar", "finalizar_e_criar_viagem"):
        criar_viagem = (acao == "finalizar_e_criar_viagem")
        _adicionar_log_debug(request, f"Ação '{acao}' detectada - processando finalização (criar_viagem={criar_viagem})")
        redirect_result = _processar_finalizacao(request, form, etapa_atual, etapas, campos_etapa_nomes, form_dependente, criar_viagem)
        return redirect_result
    
                                                                                      
    proxima_etapa = etapas.filter(ordem__gt=etapa_atual.ordem).first()
    if not proxima_etapa and etapa_atual.campo_booleano != 'etapa_membros':
        _adicionar_log_debug(request, "Última etapa detectada sem botão finalizar - processando finalização automaticamente")
        if form.is_valid():
            _salvar_etapa_na_sessao(form, etapa_atual, request)
            try:
                cliente = _criar_cliente_do_banco(request)
                return _finalizar_cadastro_cliente(request, cliente), None, None
            except ValueError as e:
                messages.error(request, str(e))
                _adicionar_log_debug(request, f"Erro ao finalizar cadastro: {str(e)}", "error")
                return redirect("system:home_clientes"), None, None
    
                                                                       
    if form.is_valid():
        return _processar_avancar_etapa(request, form, etapa_atual, etapas)
    
                                          
    _exibir_erros_formulario(request, form, campos_etapa_nomes, etapa_nome=etapa_atual.nome)
    return None, form, form_dependente


@login_required
def cadastrar_cliente_view(request):
       
                                                                       
    
                                                
                                     
                              
                                                                    
                                                         
                                                 
    
          
                                                          
                                                                                 
    
         
                            
    
            
                                                              
       
    logger.info(f"View cadastrar_cliente_view chamada - Método: {request.method}, URL: {request.path}")
    
    consultor = obter_consultor_usuario(request.user)
    _limpar_flags_finalizacao(request)
    
    etapas = EtapaCadastroCliente.objects.filter(ativo=True).order_by("ordem", "nome")
    if not etapas.exists():
        messages.error(request, "Nenhuma etapa configurada. Configure as etapas primeiro.")
        return redirect("system:home_clientes")
    
    etapa_id = request.GET.get("etapa_id")
    etapa_atual = _obter_etapa_atual(etapas, etapa_id)
    
    campos_etapa = CampoEtapaCliente.objects.filter(
        etapa=etapa_atual, ativo=True
    ).order_by("ordem", "nome_campo")
    
    campos_etapa_nomes = {campo.nome_campo for campo in campos_etapa}
    tem_cep_na_etapa = 'cep' in campos_etapa_nomes
    tem_senha_na_etapa = 'senha' in campos_etapa_nomes
    
    if request.method == "POST":
        redirect_response, form, form_dependente = _processar_post_cadastro_cliente(
            request, etapa_atual, etapas, campos_etapa_nomes
        )
        if redirect_response:
            logger.info(f"Redirect recebido: {redirect_response.url if hasattr(redirect_response, 'url') else redirect_response}")
            return redirect_response
    else:
        cliente_temporario = _criar_cliente_da_sessao(request)
        dados_iniciais = _preparar_dados_iniciais_formulario(request, cliente_temporario)
        form = _criar_formulario_get(request, etapa_atual, dados_iniciais)
        form_dependente = None
    
    cliente_temporario = _criar_cliente_da_sessao(request)
    contexto = _preparar_contexto(
        etapas, etapa_atual, campos_etapa, form, cliente_temporario, consultor
    )
    contexto = _preparar_contexto_final(
        request, etapa_atual, cliente_temporario, etapas, contexto, form_dependente,
        tem_cep_na_etapa, tem_senha_na_etapa
    )
    
    return render(request, "client/cadastrar_cliente.html", contexto)


@login_required
def visualizar_cliente(request, pk: int):
                                                                                   
    consultor = obter_consultor_usuario(request.user)
    cliente = get_object_or_404(
        ClienteConsultoria.objects.select_related(
            "assessor_responsavel",
            "cliente_principal",
            "assessor_responsavel__perfil",
        ).prefetch_related("dependentes"),
        pk=pk,
    )

                         
    pode_visualizar = usuario_pode_gerenciar_todos(request.user, consultor) or (
        consultor and cliente.assessor_responsavel_id == consultor.pk
        or cliente.criado_por == request.user
    )
    
    if not pode_visualizar:
        raise PermissionDenied
    
                               
    viagens = Viagem.objects.filter(
        clientes=cliente
    ).select_related(
        "pais_destino",
        "tipo_visto",
        "assessor_responsavel",
    ).prefetch_related("clientes").order_by("-data_prevista_viagem")
    
                                 
    processos = Processo.objects.filter(
        cliente=cliente
    ).select_related(
        "viagem",
        "viagem__pais_destino",
        "viagem__tipo_visto",
        "assessor_responsavel",
    ).prefetch_related("etapas", "etapas__status").order_by("-criado_em")
    
                                             
    registros_financeiros = Financeiro.objects.filter(
        cliente=cliente
    ).select_related(
        "viagem",
        "assessor_responsavel",
    ).order_by("-criado_em")
    
                       
    status_financeiro = _obter_status_financeiro_cliente(cliente)
    
    contexto = {
        "cliente": cliente,
        "viagens": viagens,
        "processos": processos,
        "registros_financeiros": registros_financeiros,
        "status_financeiro": status_financeiro,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": usuario_pode_gerenciar_todos(request.user, consultor),
        "pode_editar": pode_visualizar,
    }
    
    return render(request, "client/visualizar_cliente.html", contexto)


@login_required
def editar_cliente_view(request, pk: int):
                                                   
    consultor = obter_consultor_usuario(request.user)
    cliente = get_object_or_404(
        ClienteConsultoria.objects.select_related(
            "assessor_responsavel",
            "cliente_principal",
        ).prefetch_related("dependentes"),
        pk=pk,
    )

                         
    pode_editar = usuario_pode_gerenciar_todos(request.user, consultor) or (
        consultor and cliente.assessor_responsavel_id == consultor.pk
        or cliente.criado_por == request.user
    )
    
    if not pode_editar:
        raise PermissionDenied

    if request.method == "POST":
        form = ClienteConsultoriaForm(data=request.POST, user=request.user, instance=cliente)
        form.fields["senha"].required = False
        form.fields["confirmar_senha"].required = False
        
        if form.is_valid():
                                                                         
            cliente_atualizado = form.save()
            messages.success(request, f"{cliente_atualizado.nome} atualizado com sucesso.")
            return redirect("system:listar_clientes_view")
        messages.error(request, "Não foi possível atualizar o cliente. Verifique os campos.")
    else:
        form = ClienteConsultoriaForm(user=request.user, instance=cliente)
                                       
        form.fields["senha"].required = False
        form.fields["senha"].widget.attrs["placeholder"] = "Deixe em branco para manter a senha atual"
        form.fields["confirmar_senha"].required = False
        form.fields["confirmar_senha"].widget.attrs["placeholder"] = "Deixe em branco para manter a senha atual"
                                            
        if cliente.parceiro_indicador:
            form.fields["parceiro_indicador"].initial = cliente.parceiro_indicador.pk

    contexto = {
        "form": form,
        "cliente": cliente,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "client/editar_cliente.html", contexto)


@login_required
@require_GET
def api_buscar_cep(request):
                                                    
    cep = request.GET.get("cep", "").strip()

    if not cep:
        return JsonResponse({"error": "Informe um CEP."}, status=400)

    try:
        endereco = buscar_endereco_por_cep(cep)
        return JsonResponse(endereco)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_GET
def api_dados_cliente(request):
                                                                      
    cliente_id = request.GET.get("cliente_id")

    if not cliente_id:
        return JsonResponse({"error": "ID do cliente não informado."}, status=400)

    try:
        cliente = ClienteConsultoria.objects.get(pk=cliente_id)
        data_base = cliente.criado_em.date().isoformat()
        response_data = {
            "data_base": data_base,
            "cliente": {
                "nome": cliente.nome,
            },
        }
        return JsonResponse(response_data)
    except ClienteConsultoria.DoesNotExist:
        return JsonResponse({"error": "Cliente não encontrado."}, status=404)


@login_required
def cadastrar_dependente(request, pk: int):
                                                                                                          
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    cliente_principal = get_object_or_404(ClienteConsultoria, pk=pk)
    
                         
    if not pode_gerenciar_todos and (not consultor or cliente_principal.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para gerenciar este cliente.")
    
                                             
    primeira_etapa = EtapaCadastroCliente.objects.filter(ativo=True).order_by("ordem").first()
    if not primeira_etapa:
        messages.error(request, "Nenhuma etapa configurada. Configure as etapas primeiro.")
        return redirect("system:home_clientes")
    
    campos_etapa = CampoEtapaCliente.objects.filter(
        etapa=primeira_etapa, ativo=True
    ).exclude(nome_campo="parceiro_indicador").order_by("ordem", "nome_campo")
    
    if request.method == "POST":
        if (acao := request.POST.get("acao", "salvar")) == "finalizar":
            messages.success(request, "Cadastro de dependentes finalizado.")
            return redirect("system:home_clientes")
        
                                                               
        etapas = EtapaCadastroCliente.objects.filter(ativo=True).order_by("ordem")
                                                                              
        form = _preparar_formulario_dependente_post(request, primeira_etapa, etapas, cliente_principal=cliente_principal)
        
        if form.is_valid():
            usar_dados_principal = request.POST.get('usar_dados_cliente_principal') == 'on'
            _salvar_dependente(form, cliente_principal, primeira_etapa, request.user, usar_dados_principal=usar_dados_principal)
            messages.success(request, f"{form.cleaned_data['nome']} cadastrado como dependente com sucesso.")
            return redirect("system:cadastrar_dependente", pk=cliente_principal.pk)
        
                                                       
        campos_etapa_nomes = set(campos_etapa.values_list("nome_campo", flat=True))
        _exibir_erros_formulario(
            request,
            form,
            campos_etapa_nomes,
            etapa_nome=f"Dependente - {primeira_etapa.nome}",
        )
    else:
                                                               
        etapas = EtapaCadastroCliente.objects.filter(ativo=True).order_by("ordem")
        form = _criar_formulario_dependente(request, cliente_principal, primeira_etapa, etapas)
    
                                                                                          
    assessor_id = None
    if cliente_principal.assessor_responsavel:
        assessor_id = cliente_principal.assessor_responsavel.pk
    elif consultor:
        assessor_id = consultor.pk
    
    contexto = {
        "cliente_principal": cliente_principal,
        "form": form,
        "etapa_atual": primeira_etapa,
        "campos_etapa": campos_etapa,
        "dependentes": cliente_principal.dependentes.all().order_by("nome"),
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "assessor_id": assessor_id,
    }
    
    return render(request, "client/cadastrar_dependente.html", contexto)


@login_required
def adicionar_dependente(request, pk: int):
                                                        
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    cliente_principal = get_object_or_404(ClienteConsultoria, pk=pk)

                         
    if not pode_gerenciar_todos and (not consultor or cliente_principal.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para gerenciar este cliente.")

    if request.method == "POST":
        if dependente_id := request.POST.get("dependente_id"):
            try:
                dependente = ClienteConsultoria.objects.get(pk=dependente_id)
                                                           
                if dependente.cliente_principal:
                    messages.error(request, "Este cliente já é dependente de outro cliente.")
                elif dependente.pk == cliente_principal.pk:
                    messages.error(request, "Um cliente não pode ser dependente de si mesmo.")
                else:
                    dependente.cliente_principal = cliente_principal
                    dependente.save()
                    messages.success(request, f"{dependente.nome} adicionado como dependente.")
                    return redirect("system:editar_cliente", pk=cliente_principal.pk)
            except ClienteConsultoria.DoesNotExist:
                messages.error(request, "Cliente não encontrado.")

                                                                                             
    clientes_disponiveis = ClienteConsultoria.objects.filter(
        cliente_principal__isnull=True
    ).exclude(pk=cliente_principal.pk).order_by("nome")

    contexto = {
        "cliente_principal": cliente_principal,
        "clientes_disponiveis": clientes_disponiveis,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "client/adicionar_dependente.html", contexto)


@login_required
@require_http_methods(["POST"])
def remover_dependente(request, pk: int, dependente_id: int):
                                                       
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    cliente_principal = get_object_or_404(ClienteConsultoria, pk=pk)
    dependente = get_object_or_404(ClienteConsultoria, pk=dependente_id)

                         
    if not pode_gerenciar_todos and (not consultor or cliente_principal.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para gerenciar este cliente.")

                                                                           
    if dependente.cliente_principal != cliente_principal:
        messages.error(request, "Este cliente não é dependente do cliente selecionado.")
        return redirect("system:editar_cliente", pk=cliente_principal.pk)

    dependente_nome = dependente.nome
    dependente.cliente_principal = None
    dependente.save()

    messages.success(request, f"{dependente_nome} removido como dependente.")
    return redirect("system:editar_cliente", pk=cliente_principal.pk)

