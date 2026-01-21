"""
Views auxiliares relacionadas aos clientes.
"""

import json
import logging
from contextlib import suppress
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
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

# Configurar logger para debug do cadastro de clientes
logger = logging.getLogger(__name__)


def _aplicar_filtros_clientes(clientes, request, incluir_assessor=False):
    """Aplica filtros de busca aos clientes e retorna queryset filtrado e dicionário de filtros."""
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
    """
    Determina o status financeiro do cliente baseado nos registros financeiros.
    
    Retorna:
    - "Pendente" se houver registros pendentes
    - "Pago" se todos os registros estão pagos
    - "Cancelado" se todos os registros estão cancelados
    - "Sem registros" se não houver registros financeiros
    """
    registros = Financeiro.objects.filter(cliente=cliente)
    
    if not registros.exists():
        return "Sem registros"
    
    tem_pendente = registros.filter(status=StatusFinanceiro.PENDENTE).exists()
    tem_pago = registros.filter(status=StatusFinanceiro.PAGO).exists()
    tem_cancelado = registros.filter(status=StatusFinanceiro.CANCELADO).exists()
    
    # Prioridade: Pendente > Pago > Cancelado
    return "Pendente" if tem_pendente else "Pago" if tem_pago else "Cancelado" if tem_cancelado else "Sem registros"


def _obter_tipo_visto_cliente(viagem, cliente):
    """Obtém o tipo de visto individual do cliente na viagem, ou o tipo de visto da viagem como fallback."""
    with suppress(ClienteViagem.DoesNotExist):
        cliente_viagem = ClienteViagem.objects.select_related('tipo_visto__formulario').get(
            viagem=viagem, cliente=cliente
        )
        if cliente_viagem.tipo_visto:
            return cliente_viagem.tipo_visto
    return viagem.tipo_visto


def _obter_formulario_por_tipo_visto(tipo_visto, apenas_ativo=True):
    """Obtém o formulário de um tipo de visto diretamente do banco de dados."""
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
    """
    Determina o status do formulário do cliente baseado em todas as suas viagens.
    
    Retorna um dicionário com:
    - "status": "Completo", "Parcial", "Não preenchido", ou "Sem formulário"
    - "total_perguntas": total de perguntas
    - "total_respostas": total de respostas
    - "completo": boolean indicando se está completo
    """
    # Buscar todas as viagens do cliente ordenadas pela mais recente
    # Usar prefetch_related para otimizar consultas
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
    
    # Verificar a viagem mais recente (ou melhor status entre todas)
    melhor_status = None
    melhor_info = None
    
    for viagem in viagens:
        # Obter o tipo_visto individual do cliente
        tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)
        
        if not tipo_visto_cliente:
            continue
        
        # Buscar formulário diretamente do banco de dados
        formulario = _obter_formulario_por_tipo_visto(tipo_visto_cliente, apenas_ativo=True)
        
        if not formulario:
            continue
        
        # Calcular informações do formulário para este cliente
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
        
        # Priorizar: Completo > Parcial > Não preenchido
        if completo:
            status = "Completo"
        elif total_respostas > 0:
            status = "Parcial"
        else:
            status = "Não preenchido"
        
        info["status"] = status
        
        # Atualizar melhor status (prioridade: Completo > Parcial > Não preenchido)
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
    
    # Nenhuma viagem com formulário encontrada
    return {
        "status": "Sem formulário",
        "total_perguntas": 0,
        "total_respostas": 0,
        "completo": False,
    }


def listar_clientes(user: User) -> QuerySet[ClienteConsultoria]:
    """
    Retorna queryset dos clientes com relacionamentos carregados.
    Inclui dependentes cujo cliente principal está acessível ao usuário.
    """

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

    # Incluir clientes principais e dependentes acessíveis
    # Clientes principais: apenas os onde assessor_responsavel_id corresponde ao consultor
    # Dependentes: apenas os cujo cliente_principal tem assessor_responsavel_id correspondente ao consultor
    # NOTA: Filtramos apenas por assessor_responsavel_id para garantir que apenas clientes vinculados ao assessor sejam exibidos
    consultor_id = consultor.pk
    return queryset.filter(
        # Cliente principal vinculado ao assessor
        Q(assessor_responsavel_id=consultor_id) |
        # OU dependente cujo cliente principal está vinculado ao assessor
        Q(cliente_principal__assessor_responsavel_id=consultor_id)
    ).distinct()


def usuario_pode_gerenciar_todos(user: User, consultor: UsuarioConsultoria | None) -> bool:
    return (
        user.is_superuser
        or user.is_staff
        or (consultor and consultor.perfil.nome.lower() == "administrador")
    )


def obter_consultor_usuario(user: User) -> UsuarioConsultoria | None:
    """Obtém o consultor associado ao usuário usando username (que é o email do consultor)."""
    if not user or not user.username:
        return None
    
    # Buscar pelo username primeiro (que é o email do consultor via _sync_consultant_user)
    consultor = (
        UsuarioConsultoria.objects.select_related("perfil")
        .filter(email__iexact=user.username.strip(), ativo=True)
        .first()
    )
    
    # Fallback: tentar buscar por email do user se não encontrar por username
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
    """Página inicial de clientes com opções de navegação."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    perfil_usuario = consultor.perfil.nome if consultor and consultor.perfil else ("Administrador" if request.user.is_superuser else None)
    
    # Buscar clientes vinculados ao usuário (para administradores retorna todos, para assessores retorna apenas os vinculados)
    clientes = listar_clientes(request.user).prefetch_related("dependentes", "viagens")
    
    # Aplicar filtros
    clientes, filtros = _aplicar_filtros_clientes(clientes, request)
    
    # Adicionar status financeiro e status do formulário aos clientes
    clientes_com_status = []
    for cliente in clientes:
        status_financeiro = _obter_status_financeiro_cliente(cliente)
        status_formulario = _obter_status_formulario_cliente(cliente)
        clientes_com_status.append({
            "cliente": cliente,
            "status_financeiro": status_financeiro,
            "status_formulario": status_formulario["status"],
            "total_perguntas": status_formulario["total_perguntas"],
            "total_respostas": status_formulario["total_respostas"],
            "completo": status_formulario["completo"],
        })
    
    return render(request, "client/home_clientes.html", {
        "total_clientes": clientes.count(),
        "clientes_com_status": clientes_com_status,
        "perfil_usuario": perfil_usuario,
        "pode_excluir_clientes": pode_gerenciar_todos,
        "filtros": filtros,
    })


@login_required
def listar_clientes_view(request):
    """Lista todos os clientes cadastrados com filtros."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    # Listar TODOS os clientes, independente de assessor
    clientes = ClienteConsultoria.objects.select_related(
        "assessor_responsavel",
        "criado_por",
        "assessor_responsavel__perfil",
        "cliente_principal",
        "cliente_principal__assessor_responsavel",
        "parceiro_indicador",
    ).prefetch_related("dependentes", "viagens").order_by("-criado_em")
    
    # Aplicar filtros (incluindo filtro de assessor)
    clientes, filtros = _aplicar_filtros_clientes(clientes, request, incluir_assessor=True)
    
    # Adicionar status financeiro e status do formulário aos clientes
    clientes_com_status = []
    for cliente in clientes:
        status_financeiro = _obter_status_financeiro_cliente(cliente)
        status_formulario = _obter_status_formulario_cliente(cliente)
        clientes_com_status.append({
            "cliente": cliente,
            "status_financeiro": status_financeiro,
            "status_formulario": status_formulario["status"],
            "total_perguntas": status_formulario["total_perguntas"],
            "total_respostas": status_formulario["total_respostas"],
            "completo": status_formulario["completo"],
        })
    
    return render(request, "client/listar_clientes.html", {
        "clientes_com_status": clientes_com_status,
        "assessores": UsuarioConsultoria.objects.filter(ativo=True).order_by("nome"),
        "perfil_usuario": consultor.perfil.nome if consultor and consultor.perfil else None,
        "pode_excluir_clientes": pode_gerenciar_todos,
        "filtros": filtros,
    })


# ============================================================================
# FUNÇÕES AUXILIARES PARA CADASTRO DE CLIENTES - NOVA IMPLEMENTAÇÃO
# ============================================================================

def _obter_etapa_atual(etapas, etapa_id: str | None) -> EtapaCadastroCliente:
    """
    Obtém a etapa atual baseada no ID fornecido ou retorna a primeira etapa.
    
    Args:
        etapas: QuerySet de EtapaCadastroCliente
        etapa_id: ID da etapa desejada (opcional)
    
    Returns:
        EtapaCadastroCliente: A etapa atual ou a primeira etapa se não especificada
    """
    etapa_atual = etapas.first()
    if etapa_id:
        with suppress(ValueError, EtapaCadastroCliente.DoesNotExist):
            etapa_atual = etapas.get(pk=int(etapa_id))
    return etapa_atual


def _obter_dados_temporarios_sessao(request) -> dict:
    """
    Obtém os dados temporários do cliente armazenados na sessão.
    
    Durante o cadastro em etapas, os dados são armazenados temporariamente na sessão
    e só são salvos no banco quando o usuário clicar em "Finalizar Cadastro".
    
    Args:
        request: HttpRequest com a sessão
    
    Returns:
        dict: Dicionário com os dados temporários ou {} se vazio
    """
    return request.session.get("cliente_dados_temporarios", {})


def _serializar_dados_para_sessao(dados: dict, preservar_confirmar_senha: bool = False) -> dict:
    """
    Serializa dados para armazenamento na sessão.
    
    Converte objetos não serializáveis (date, datetime, ForeignKey) para formatos
    compatíveis com JSON.
    
    Args:
        dados: Dicionário com os dados a serem serializados
        preservar_confirmar_senha: Se True, preserva confirmar_senha (útil para dependentes)
    
    Returns:
        dict: Dicionário com dados serializados
    """
    dados_serializados = {}
    for campo, valor in dados.items():
        # Para dependentes, preservar confirmar_senha para validação posterior
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
    """
    Salva dados temporários do cliente na sessão.
    
    Converte objetos não serializáveis (date, datetime, ForeignKey) para formatos
    compatíveis com JSON antes de armazenar na sessão.
    
    Args:
        request: HttpRequest com a sessão
        dados: Dicionário com os dados a serem salvos
    """
    dados_serializados = _serializar_dados_para_sessao(dados)
    request.session["cliente_dados_temporarios"] = dados_serializados
    request.session.modified = True


def _limpar_dados_temporarios_sessao(request):
    """
    Remove os dados temporários da sessão.
    
    Usado após finalizar o cadastro ou cancelar.
    
    Args:
        request: HttpRequest com a sessão
    """
    if "cliente_dados_temporarios" in request.session:
        request.session.pop("cliente_dados_temporarios", None)
    # Limpar flags de finalização (mas manter por um tempo para evitar duplicação)
    # Os flags serão limpos quando um novo cadastro começar
    request.session.modified = True


def _converter_valor_campo(instancia, campo_nome: str, valor):
    """
    Converte um valor da sessão para o formato correto do campo do modelo Django.
    
    Converte ForeignKeys (IDs para objetos), strings ISO para date/datetime, etc.
    
    Args:
        instancia: Instância do modelo Django (ClienteConsultoria)
        campo_nome: Nome do campo no modelo
        valor: Valor a ser convertido (da sessão)
    
    Returns:
        Valor convertido ou o valor original se não precisar conversão
    """
    if not hasattr(instancia, campo_nome):
        return valor
    
    with suppress(AttributeError, TypeError):
        field = instancia._meta.get_field(campo_nome)
        # Converter ForeignKeys (IDs para objetos)
        if hasattr(field, 'remote_field') and field.remote_field and valor:
            # Ignorar valores vazios ou None
            if valor == '' or valor is None:
                return None
            related_model = field.remote_field.model
            with suppress(related_model.DoesNotExist, ValueError):
                # Tentar converter para int se for string
                pk_value = int(valor) if isinstance(valor, str) and valor.isdigit() else valor
                return related_model.objects.get(pk=pk_value)
        # Converter strings ISO para date/datetime
        elif isinstance(field, (models.DateField, models.DateTimeField)) and isinstance(valor, str):
            with suppress(ValueError, AttributeError):
                if isinstance(field, models.DateTimeField):
                    if 'T' in valor or ' ' in valor:
                        return datetime.fromisoformat(valor.replace('Z', '+00:00'))
                    return datetime.combine(date.fromisoformat(valor), datetime.min.time())
                return date.fromisoformat(valor)
    
    return valor


def _aplicar_dados_ao_cliente(cliente, dados: dict, campos_excluidos: set = None):
    """
    Aplica dados de um dicionário a uma instância de ClienteConsultoria.
    
    Args:
        cliente: Instância de ClienteConsultoria
        dados: Dicionário com os dados a serem aplicados
        campos_excluidos: Set com nomes de campos a serem ignorados
    """
    if campos_excluidos is None:
        campos_excluidos = {'confirmar_senha'}
    
    for campo_nome, valor in dados.items():
        if campo_nome in campos_excluidos or not hasattr(cliente, campo_nome):
            continue
        
        # CRÍTICO: NUNCA sobrescrever cliente_principal se já estiver definido
        if campo_nome == 'cliente_principal' and hasattr(cliente, 'cliente_principal_id') and cliente.cliente_principal_id:
            continue
        
        # Ignorar valores vazios em ForeignKeys obrigatórios (serão definidos depois)
        with suppress(AttributeError, TypeError):
            field = cliente._meta.get_field(campo_nome)
            if hasattr(field, 'remote_field') and field.remote_field and (valor == '' or valor is None):
                # Não aplicar valores vazios em ForeignKeys - serão definidos depois se necessário
                continue
        
        valor_convertido = _converter_valor_campo(cliente, campo_nome, valor)
        setattr(cliente, campo_nome, valor_convertido)


def _adicionar_log_debug(request, mensagem: str, nivel: str = "info"):
    """
    Adiciona uma mensagem aos logs de debug.
    
    Logs são enviados para o terminal (Python logging) e para o console do navegador
    via JavaScript (através do contexto 'debug_logs_json').
    
    Args:
        request: HttpRequest com a sessão
        mensagem: Mensagem a ser logada
        nivel: Nível do log ('info', 'warning', 'error', 'debug')
    """
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_msg = f"[{timestamp}] {mensagem}"
    
    # Log no terminal (Python)
    log_level = getattr(logging, nivel.upper(), logging.INFO)
    logger.log(log_level, log_msg)
    
    # Armazenar no contexto para JavaScript (máximo 20 logs)
    if 'debug_logs_json' not in request.session:
        request.session['debug_logs_json'] = []
    request.session['debug_logs_json'].append({
        'timestamp': timestamp,
        'message': mensagem,
        'level': nivel
    })
    # Manter apenas os últimos 20 logs
    if len(request.session['debug_logs_json']) > 20:
        request.session['debug_logs_json'] = request.session['debug_logs_json'][-20:]
    request.session.modified = True


def _criar_cliente_da_sessao(request) -> ClienteConsultoria | None:
    """
    Cria uma instância temporária de ClienteConsultoria a partir dos dados da sessão.
    
    Esta instância NÃO é salva no banco, apenas usada para preencher formulários.
    
    Args:
        request: HttpRequest com a sessão
    
    Returns:
        ClienteConsultoria | None: Instância temporária ou None se não houver dados
    """
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
    """Configura campos obrigatórios/opcionais do formulário conforme a etapa."""
    campos_etapa_dict = {
        campo.nome_campo: campo
        for campo in CampoEtapaCliente.objects.filter(
            etapa=etapa_atual, ativo=True
        ).order_by("ordem", "nome_campo")
    }
    for field_name, field in form.fields.items():
        campo_config = campos_etapa_dict.get(field_name)
        # Se o campo está na etapa atual, usa a configuração de obrigatório
        # Se não está, torna não obrigatório para não validar campos de outras etapas
        field.required = campo_config.obrigatorio if campo_config else False


def _salvar_etapa_na_sessao(form, etapa_atual, request):
    """
    Salva os dados da etapa atual na sessão temporária.
    
    Esta função é chamada quando o usuário avança para a próxima etapa.
    Os dados são armazenados na sessão e NÃO são salvos no banco ainda.
    
    Args:
        form: ClienteConsultoriaForm validado
        etapa_atual: EtapaCadastroCliente atual
        request: HttpRequest com a sessão
    
    Debug:
        Adiciona log na sessão indicando que a etapa foi salva
    """
    # Obter dados existentes da sessão
    dados_existentes = _obter_dados_temporarios_sessao(request)
    
    # Atualizar com os dados da etapa atual
    dados_atualizados = dados_existentes.copy()
    dados_atualizados.update(form.cleaned_data)
    
    # Preservar assessor_responsavel se:
    # 1. Estiver nos dados existentes E
    # 2. Não estiver no cleaned_data OU estiver vazio/None no cleaned_data
    # (pode acontecer se o campo não estiver na etapa atual ou vier vazio do POST)
    assessor_existente = dados_existentes.get('assessor_responsavel')
    assessor_cleaned = form.cleaned_data.get('assessor_responsavel')
    
    # Converter assessor_cleaned para ID se for um objeto
    assessor_cleaned_id = None
    if assessor_cleaned:
        if hasattr(assessor_cleaned, 'pk'):
            assessor_cleaned_id = assessor_cleaned.pk
        elif isinstance(assessor_cleaned, (int, str)) and str(assessor_cleaned).strip():
            try:
                assessor_cleaned_id = int(assessor_cleaned)
            except (ValueError, TypeError):
                assessor_cleaned_id = None
    
    # Preservar se não houver valor válido no cleaned_data
    if assessor_existente and not assessor_cleaned_id:
        dados_atualizados['assessor_responsavel'] = assessor_existente
        logger.debug(f"🔒 Preservando assessor_responsavel da sessão: {assessor_existente}")
    
    # Marcar etapa como concluída
    if etapa_atual.campo_booleano:
        dados_atualizados[etapa_atual.campo_booleano] = True
    
    # Adicionar log de debug
    _adicionar_log_debug(request, f"Etapa '{etapa_atual.nome}' salva na sessão")
    
    # Salvar na sessão (com serialização automática)
    _salvar_dados_temporarios_sessao(request, dados_atualizados)


def _avancar_para_proxima_etapa(etapa_atual, etapas, request_path, request):
    """
    Determina e retorna o redirecionamento para a próxima etapa.
    
    Args:
        etapa_atual: EtapaCadastroCliente atual
        etapas: QuerySet de todas as etapas
        request_path: Caminho da requisição atual
        request: HttpRequest para mensagens
    
    Returns:
        HttpResponseRedirect: Redirecionamento para a próxima etapa ou None
    """
    if proxima_etapa := etapas.filter(ordem__gt=etapa_atual.ordem).first():
        messages.success(request, f"Etapa '{etapa_atual.nome}' concluída!")
        return redirect(f"{request_path}?etapa_id={proxima_etapa.pk}")
    
    # Se for etapa de membros, permanecer na mesma página
    if etapa_atual.campo_booleano == 'etapa_membros':
        messages.success(request, f"Etapa '{etapa_atual.nome}' concluída! Você pode adicionar dependentes abaixo.")
        return redirect(f"{request_path}?etapa_id={etapa_atual.pk}")
    
    return None


def _criar_dependente_do_banco(dados_dependente: dict, cliente_principal: ClienteConsultoria, user) -> ClienteConsultoria | None:
    """
    Cria e salva um dependente no banco de dados a partir de dados temporários.
    
    Args:
        dados_dependente: Dicionário com dados do dependente
        cliente_principal: ClienteConsultoria principal
        user: Usuário que está criando
    
    Returns:
        ClienteConsultoria: Dependente salvo ou None se houver erro
    """
    nome_dependente = dados_dependente.get('nome', 'Desconhecido')
    email_dependente = dados_dependente.get('email', '')
    
    try:
        logger.info(f"📝 Criando dependente: {nome_dependente} (email: {email_dependente}) para cliente principal: {cliente_principal.nome}")
        
        # Verificar se email já existe e permitir apenas se for do cliente principal ou outro dependente do mesmo grupo
        if email_dependente and (cliente_existente := ClienteConsultoria.objects.filter(email=email_dependente).first()):
                # Permitir apenas se o email pertence ao cliente principal ou outro dependente do mesmo grupo
                if cliente_existente.pk != cliente_principal.pk and cliente_existente.cliente_principal_id != cliente_principal.pk:
                    logger.error(f"❌ Email {email_dependente} já está em uso por outro cliente: {cliente_existente.nome}")
                    return None
                # Se o email pertence ao cliente principal, usar o mesmo email (permitido)
                if cliente_existente.pk == cliente_principal.pk:
                    logger.info(f"ℹ️ Dependente {nome_dependente} compartilhará email com cliente principal")
        
        # Verificar se deve usar dados do cliente principal
        usar_dados_principal = dados_dependente.get('usar_dados_cliente_principal', False)
        if usar_dados_principal:
            # Usar email do cliente principal
            dados_dependente['email'] = cliente_principal.email
            logger.info(f"ℹ️ Dependente usará email do cliente principal: {cliente_principal.email}")
        
        # Garantir que confirmar_senha está presente se senha estiver presente
        if 'senha' in dados_dependente and dados_dependente.get('senha') and 'confirmar_senha' not in dados_dependente:
            dados_dependente['confirmar_senha'] = dados_dependente['senha']
            logger.info("🔧 Adicionando confirmar_senha aos dados do dependente (usando valor da senha)")
        
        form_dependente = ClienteConsultoriaForm(data=dados_dependente, instance=None, user=user, cliente_principal=cliente_principal, usar_dados_principal=usar_dados_principal)
        if not form_dependente.is_valid():
            logger.error(f"❌ Formulário de dependente inválido para {nome_dependente}: {form_dependente.errors}")
            return None
        
        dependente = form_dependente.save(commit=False)
        
        # CRÍTICO: Vincular ao cliente principal ANTES de aplicar dados
        # Isso garante que o relacionamento seja mantido
        dependente.cliente_principal_id = cliente_principal.pk
        dependente.assessor_responsavel = cliente_principal.assessor_responsavel
        dependente.parceiro_indicador = cliente_principal.parceiro_indicador
        dependente.criado_por = user
        
        logger.info(f"🔗 Vinculando dependente {nome_dependente} ao cliente principal {cliente_principal.nome} (ID: {cliente_principal.pk})")
        
        # Aplicar conversões de campos (excluindo cliente_principal para não sobrescrever)
        dados_dependente_sem_principal = {k: v for k, v in dados_dependente.items() if k != 'cliente_principal'}
        _aplicar_dados_ao_cliente(dependente, dados_dependente_sem_principal)
        
        # Garantir que cliente_principal não foi sobrescrito (verificação final)
        if dependente.cliente_principal_id != cliente_principal.pk:
            logger.error("❌ ERRO CRÍTICO: cliente_principal foi sobrescrito! Corrigindo...")
            dependente.cliente_principal_id = cliente_principal.pk
        
        # Salvar senha: usar do cliente principal se solicitado, senão usar a senha fornecida
        if usar_dados_principal := dados_dependente.get('usar_dados_cliente_principal', False):
            # Copiar o hash da senha do cliente principal
            dependente.senha = cliente_principal.senha
            logger.info("ℹ️ Copiando hash da senha do cliente principal para o dependente")
        elif senha := dados_dependente.get('senha'):
            dependente.set_password(senha)
        
        # Marcar etapa de dados pessoais como concluída
        primeira_etapa = EtapaCadastroCliente.objects.filter(ativo=True).order_by("ordem").first()
        if primeira_etapa and primeira_etapa.campo_booleano:
            setattr(dependente, primeira_etapa.campo_booleano, True)
        
        # Salvar no banco
        dependente.save()
        
        # Verificar se foi salvo corretamente
        dependente_refreshed = ClienteConsultoria.objects.get(pk=dependente.pk)
        if dependente_refreshed.cliente_principal_id != cliente_principal.pk:
            logger.error(f"❌ ERRO CRÍTICO: Dependente {nome_dependente} não está vinculado após salvar! cliente_principal_id={dependente_refreshed.cliente_principal_id}")
            return None
        
        logger.info(f"✅ Dependente {nome_dependente} salvo com sucesso (ID: {dependente.pk}, cliente_principal_id: {dependente.cliente_principal_id})")
        return dependente
    except Exception as e:
        logger.error(f"❌ Erro ao salvar dependente {nome_dependente}: {str(e)}", exc_info=True)
        return None


def _marcar_etapas_concluidas(cliente: ClienteConsultoria, dados_temporarios: dict):
    """Marca as etapas como concluídas no cliente baseado nos dados temporários."""
    etapas_booleanas = ['etapa_dados_pessoais', 'etapa_endereco', 'etapa_passaporte', 'etapa_membros']
    for campo_booleano in etapas_booleanas:
        if dados_temporarios.get(campo_booleano):
            setattr(cliente, campo_booleano, True)


def _processar_dependentes_temporarios(request, cliente: ClienteConsultoria) -> int:
    """
    Processa e salva dependentes temporários da sessão.
    
    Args:
        request: HttpRequest com a sessão
        cliente: ClienteConsultoria principal
    
    Returns:
        int: Número de dependentes salvos com sucesso
    """
    dependentes_temporarios = request.session.get("dependentes_temporarios", [])
    if not dependentes_temporarios:
        logger.info(f"ℹ️ Nenhum dependente temporário encontrado na sessão para cliente {cliente.nome}")
        return 0
    
    logger.info(f"📦 Processando {len(dependentes_temporarios)} dependente(s) temporário(s) para cliente {cliente.nome}")
    dependentes_salvos = 0
    dependentes_com_erro = []
    
    for idx, dados_dependente in enumerate(dependentes_temporarios):
        nome = dados_dependente.get('nome', 'Desconhecido')
        email = dados_dependente.get('email', '')
        
        logger.info(f"🔄 Processando dependente {idx + 1}/{len(dependentes_temporarios)}: {nome} (email: {email})")
        logger.info(f"📋 Dados do dependente: {dados_dependente}")
        
        # Verificar se os dados essenciais estão presentes
        if not nome:
            logger.error(f"❌ Dependente {idx + 1} não tem nome - pulando")
            dependentes_com_erro.append(f"Dependente {idx + 1} (sem nome)")
            continue
        
        if not email:
            logger.error(f"❌ Dependente {nome} não tem email - pulando (emails são obrigatórios e únicos)")
            dependentes_com_erro.append(f"{nome} (sem email)")
            continue
        
        # Tentar salvar o dependente
        try:
            if dependente := _criar_dependente_do_banco(dados_dependente, cliente, request.user):
                dependentes_salvos += 1
                # Verificar se o relacionamento foi criado corretamente
                dependente.refresh_from_db()
                if dependente.cliente_principal_id == cliente.pk:
                    logger.info(f"✅ Dependente {nome} salvo com sucesso (ID: {dependente.pk}, cliente_principal_id: {dependente.cliente_principal_id})")
                else:
                    logger.error(f"❌ ERRO CRÍTICO: Dependente {nome} não está vinculado corretamente! cliente_principal_id={dependente.cliente_principal_id}, esperado={cliente.pk}")
                    # Tentar corrigir
                    dependente.cliente_principal_id = cliente.pk
                    dependente.save(update_fields=['cliente_principal'])
                    logger.info(f"✅ Relacionamento corrigido para dependente {nome}")
            else:
                dependentes_com_erro.append(nome)
                logger.error(f"❌ Falha ao salvar dependente: {nome}")
                _adicionar_log_debug(request, f"Erro ao salvar dependente: {nome}")
        except Exception as e:
            dependentes_com_erro.append(nome)
            logger.error(f"❌ Exceção ao salvar dependente {nome}: {str(e)}", exc_info=True)
            _adicionar_log_debug(request, f"Exceção ao salvar dependente {nome}: {str(e)}")
    
    # Limpar dependentes temporários da sessão
    request.session.pop("dependentes_temporarios", None)
    
    if dependentes_com_erro:
        logger.warning(f"⚠️ {len(dependentes_com_erro)} dependente(s) não foram salvos: {', '.join(dependentes_com_erro)}")
    
    logger.info(f"📊 Total de dependentes salvos: {dependentes_salvos}/{len(dependentes_temporarios)}")
    return dependentes_salvos


def _recuperar_assessor_dos_dados_temporarios(dados_temporarios: dict) -> UsuarioConsultoria | None:
    """Recupera assessor dos dados temporários convertendo o ID se necessário."""
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
    """Define o assessor no cliente e registra log."""
    cliente.assessor_responsavel = assessor
    logger.info(f"✅ Assessor {origem}: {assessor.nome} (ID: {assessor.pk})")


def _garantir_assessor_responsavel(cliente: ClienteConsultoria, dados_temporarios: dict, user) -> None:
    """Garante que o cliente tenha um assessor_responsavel definido."""
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
    """Processa dependentes temporários e adiciona logs apropriados."""
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
    """Valida se há dados temporários na sessão."""
    if not dados_temporarios:
        raise ValueError("Dados não encontrados na sessão. Por favor, inicie o cadastro novamente.")


def _criar_e_configurar_cliente(dados_temporarios: dict, user) -> ClienteConsultoria:
    """Cria e configura instância do cliente com dados temporários."""
    cliente = ClienteConsultoria()
    _aplicar_dados_ao_cliente(cliente, dados_temporarios)
    cliente.criado_por = user
    _garantir_assessor_responsavel(cliente, dados_temporarios, user)
    return cliente


def _configurar_senha_e_etapas(cliente: ClienteConsultoria, dados_temporarios: dict) -> None:
    """Configura senha e marca etapas como concluídas."""
    if senha := dados_temporarios.get('senha'):
        cliente.set_password(senha)
    _marcar_etapas_concluidas(cliente, dados_temporarios)


def _salvar_e_logar_cliente(request, cliente: ClienteConsultoria) -> None:
    """Salva cliente, processa dependentes e adiciona logs."""
    cliente.save()
    _processar_e_logar_dependentes(request, cliente)
    logger.info(f"✅ Cliente '{cliente.nome}' salvo no banco (ID: {cliente.pk})")
    _adicionar_log_debug(request, f"Cliente '{cliente.nome}' salvo no banco (ID: {cliente.pk})")
    request.session.modified = True


def _criar_cliente_do_banco(request) -> ClienteConsultoria:
    """
    Cria e salva o cliente no banco de dados a partir dos dados da sessão.
    
    Esta função é chamada APENAS quando o usuário clica em "Finalizar Cadastro".
    Ela converte todos os dados temporários da sessão em um objeto ClienteConsultoria
    e salva no banco de dados.
    
    Args:
        request: HttpRequest com a sessão contendo os dados temporários
    
    Returns:
        ClienteConsultoria: Cliente salvo no banco
    
    Raises:
        ValueError: Se não houver dados temporários na sessão
    
    Debug:
        Adiciona log na sessão indicando que o cliente foi salvo no banco
    """
    dados_temporarios = _obter_dados_temporarios_sessao(request)
    _validar_dados_temporarios(dados_temporarios)
    
    cliente = _criar_e_configurar_cliente(dados_temporarios, request.user)
    _configurar_senha_e_etapas(cliente, dados_temporarios)
    _salvar_e_logar_cliente(request, cliente)
    
    return cliente


def _obter_ids_clientes_com_dependentes(cliente: ClienteConsultoria) -> list:
    """Coleta IDs do cliente principal e seus dependentes."""
    clientes_ids = [cliente.pk]
    dependentes = ClienteConsultoria.objects.filter(cliente_principal=cliente)
    clientes_ids.extend(dependentes.values_list('pk', flat=True))
    return clientes_ids


def _criar_redirect_viagem_com_clientes(request, cliente: ClienteConsultoria):
    """Cria redirect para criar viagem com clientes pré-selecionados."""
    logger.info(f"🚀 Redirecionando para criar viagem com cliente {cliente.nome} (ID: {cliente.pk})")
    # Coletar todos os clientes (principal + dependentes)
    clientes_ids = _obter_ids_clientes_com_dependentes(cliente)
    redirect_url = f"{reverse('system:criar_viagem')}?clientes={','.join(map(str, clientes_ids))}"
    logger.info(f"✅ Redirect para criar viagem: {redirect_url}")
    _adicionar_log_debug(request, f"Redirecionando para criar viagem com {len(clientes_ids)} cliente(s)")
    return redirect(redirect_url)


def _finalizar_cadastro_cliente(request, cliente: ClienteConsultoria, criar_viagem: bool = False):
    """
    Finaliza o cadastro do cliente e redireciona para a home de clientes ou criar viagem.
    
    Esta função:
    1. Limpa todos os dados temporários da sessão
    2. Exibe mensagem de sucesso
    3. Redireciona para a home de clientes ou criar viagem com clientes pré-selecionados
    
    Args:
        request: HttpRequest com a sessão
        cliente: ClienteConsultoria salvo no banco
        criar_viagem: Se True, redireciona para criar viagem com clientes pré-selecionados
    
    Returns:
        HttpResponseRedirect: Redirecionamento apropriado
    
    Debug:
        Adiciona log na sessão indicando que o cadastro foi finalizado
    """
    # Verificar se já foi finalizado para evitar duplicação de mensagens
    # Usar um flag baseado no ID do cliente para evitar duplicação
    flag_key = f'cadastro_finalizado_{cliente.pk}'
    if request.session.get(flag_key, False):
        # Se já foi finalizado para este cliente, apenas redirecionar sem adicionar mensagem novamente
        logger.info(f"⚠️ Tentativa de finalizar cadastro duplicada para cliente {cliente.pk} - redirecionando sem mensagem")
        if criar_viagem:
            # Coletar todos os clientes (principal + dependentes)
            clientes_ids = _obter_ids_clientes_com_dependentes(cliente)
            return redirect(f"{reverse('system:criar_viagem')}?clientes={','.join(map(str, clientes_ids))}")
        return redirect("system:home_clientes")
    
    # Marcar como finalizado na sessão ANTES de adicionar mensagem (usando ID do cliente para ser mais específico)
    request.session[flag_key] = True
    request.session.modified = True
    
    # Contar dependentes cadastrados ANTES de adicionar mensagem
    num_dependentes = ClienteConsultoria.objects.filter(cliente_principal=cliente).count()
    
    # Adicionar log de debug
    _adicionar_log_debug(request, f"Cadastro finalizado com sucesso! Cliente: {cliente.nome}, Dependentes: {num_dependentes}")
    
    # Limpar dados temporários (mas NÃO limpar o flag de finalização ainda)
    if "cliente_dados_temporarios" in request.session:
        request.session.pop("cliente_dados_temporarios", None)
    if "dependentes_temporarios" in request.session:
        request.session.pop("dependentes_temporarios", None)
    # Manter o flag de finalização para evitar duplicação
    request.session.modified = True
    
    # Mensagem de sucesso única e completa (apenas uma vez)
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
    
    # Garantir que as mensagens sejam salvas antes do redirect
    request.session.modified = True
    
    # Se criar_viagem for True, redirecionar para criar viagem com clientes pré-selecionados
    if criar_viagem:
        return _criar_redirect_viagem_com_clientes(request, cliente)
    
    # Redirecionar para home de clientes
    redirect_url_name = "system:home_clientes"
    _adicionar_log_debug(request, f"Redirecionando para: {redirect_url_name}")
    logger.info(f"Finalizando cadastro - criando redirect para: {redirect_url_name}")
    
    # Criar redirect usando o nome da URL
    redirect_response = redirect(redirect_url_name)
    
    # Verificar se o redirect foi criado corretamente
    if hasattr(redirect_response, 'url'):
        logger.info(f"✅ Redirect criado com sucesso - URL: {redirect_response.url}")
        _adicionar_log_debug(request, f"Redirect criado - URL: {redirect_response.url}")
    else:
        logger.warning(f"⚠️ Redirect criado mas sem atributo 'url' - Tipo: {type(redirect_response)}")
        _adicionar_log_debug(request, f"Redirect criado - Tipo: {type(redirect_response)}", "warning")
    
    return redirect_response


def _preparar_contexto(etapas, etapa_atual, campos_etapa, form, cliente, consultor):
    """Prepara o contexto para renderização do template."""
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


def _exibir_erros_formulario(request, form, campos_etapa_nomes, prefixo=""):
    """Exibe erros do formulário apenas para os campos da etapa atual."""
    if "senha" in campos_etapa_nomes:
        campos_etapa_nomes.add("confirmar_senha")
    
    for field_name, errors in form.errors.items():
        if field_name in campos_etapa_nomes:
            field_label = form.fields[field_name].label if field_name in form.fields else field_name
            for error in errors:
                messages.error(request, f"{prefixo}{field_label}: {error}")

def _obter_assessor_id_dependente(request, cliente, dados_temporarios):
    """Obtém o ID do assessor para o formulário de dependente."""
    assessor_id = None
    
    # Tentar obter do cliente temporário (instância)
    if hasattr(cliente, 'assessor_responsavel_id') and cliente.assessor_responsavel_id:
        assessor_id = cliente.assessor_responsavel_id
    # Tentar obter dos dados temporários (sessão)
    elif dados_temporarios and (assessor_valor := dados_temporarios.get('assessor_responsavel')):
        # Converter para int se necessário
        try:
            assessor_id = int(assessor_valor) if isinstance(assessor_valor, str) else assessor_valor
        except (ValueError, TypeError):
            assessor_id = None
    
    # Se ainda não tem assessor, usar o consultor atual
    if not assessor_id:
        if consultor := obter_consultor_usuario(request.user):
            assessor_id = consultor.pk
    
    return assessor_id


def _preparar_dados_iniciais_dependente(request, assessor_id):
    """Prepara dados iniciais para o formulário de dependente."""
    dependente_editando_dados = request.session.get('dependente_editando_dados')
    dados_iniciais = None
    usar_dados_principal_edit = False
    
    if dependente_editando_dados:
        # Carregar dados do dependente sendo editado
        dados_iniciais = dependente_editando_dados.copy()
        usar_dados_principal_edit = dependente_editando_dados.get('usar_dados_cliente_principal', False)
        logger.info(f"📝 Carregando dados do dependente para edição: {dados_iniciais.get('nome', 'Desconhecido')}")
        # Se não tiver assessor nos dados do dependente, usar o do cliente principal
        if assessor_id and ('assessor_responsavel' not in dados_iniciais or not dados_iniciais.get('assessor_responsavel')):
            dados_iniciais['assessor_responsavel'] = assessor_id
    elif assessor_id:
        # Se não está editando, criar dados_iniciais com o assessor_id
        dados_iniciais = {'assessor_responsavel': assessor_id}
    
    return dados_iniciais, usar_dados_principal_edit


def _preencher_campos_endereco_dependente(form_dependente, cliente, dados_temporarios):
    """Preenche campos de endereço do formulário de dependente."""
    campos_endereco = ['cep', 'logradouro', 'numero', 'complemento', 'bairro', 'cidade', 'uf']
    for campo in campos_endereco:
        if campo in form_dependente.fields:
            # Tentar obter do cliente temporário (instância)
            if hasattr(cliente, campo) and (valor := getattr(cliente, campo)):
                form_dependente.fields[campo].initial = valor
            # Tentar obter dos dados temporários (sessão)
            elif dados_temporarios and (valor := dados_temporarios.get(campo)):
                form_dependente.fields[campo].initial = valor


def _configurar_campos_formulario_dependente(form_dependente, primeira_etapa, etapas):
    """Configura campos do formulário de dependente baseado nas etapas."""
    if not etapas:
        # Fallback: usar apenas primeira etapa
        _configurar_campos_formulario(form_dependente, primeira_etapa)
        return
    
    # Obter todas as etapas: dados pessoais, endereço e passaporte
    etapas_dependente = etapas.filter(ativo=True).exclude(campo_booleano='etapa_membros').order_by("ordem")
    campos_dependente = set()
    for etapa in etapas_dependente:
        campos_etapa = CampoEtapaCliente.objects.filter(etapa=etapa, ativo=True).exclude(nome_campo="parceiro_indicador")
        campos_dependente.update(campos_etapa.values_list("nome_campo", flat=True))
    
    # Configurar obrigatoriedade apenas para campos da primeira etapa
    campos_primeira_etapa_dict = {
        campo.nome_campo: campo
        for campo in CampoEtapaCliente.objects.filter(etapa=primeira_etapa, ativo=True)
    }
    
    for field_name, field in form_dependente.fields.items():
        if field_name == 'confirmar_senha':
            continue
        # Campos da primeira etapa: usar configuração
        # Campos de outras etapas: tornar opcionais mas visíveis
        if campo_config := campos_primeira_etapa_dict.get(field_name):
            field.required = campo_config.obrigatorio
        elif field_name in campos_dependente:
            # Campos de endereço e passaporte: opcionais
            field.required = False


def _criar_formulario_dependente(request, cliente, primeira_etapa, etapas=None):
    """
    Cria e configura formulário para cadastro de dependente.
    
    Inclui campos de:
    - Dados Pessoais (primeira etapa)
    - Endereço (preenchido automaticamente do cliente principal)
    - Passaporte (para cadastro completo)
    """
    # cliente aqui é o cliente_principal quando usado para criar dependente
    cliente_principal = cliente if isinstance(cliente, ClienteConsultoria) and cliente.is_principal else None
    
    # Obter dados temporários e assessor_id
    dados_temporarios = _obter_dados_temporarios_sessao(request)
    assessor_id = _obter_assessor_id_dependente(request, cliente, dados_temporarios)
    
    # Preparar dados iniciais
    dados_iniciais, usar_dados_principal_edit = _preparar_dados_iniciais_dependente(request, assessor_id)
    
    # Criar formulário
    form_dependente = ClienteConsultoriaForm(
        data=None,
        initial=dados_iniciais,
        user=request.user,
        cliente_principal=cliente_principal,
        usar_dados_principal=usar_dados_principal_edit
    )
    
    # Garantir que assessor_responsavel esteja definido no formulário
    if assessor_id:
        form_dependente.fields["assessor_responsavel"].initial = assessor_id
    
    # Remover parceiro_indicador do formulário de dependente
    if "parceiro_indicador" in form_dependente.fields:
        del form_dependente.fields["parceiro_indicador"]
    
    # Preencher campos de endereço
    _preencher_campos_endereco_dependente(form_dependente, cliente, dados_temporarios)
    
    # Configurar campos do formulário
    _configurar_campos_formulario_dependente(form_dependente, primeira_etapa, etapas)
    
    return form_dependente

def _remover_parceiro_indicador(form):
    """Remove parceiro_indicador do formulário de dependente."""
    if "parceiro_indicador" in form.fields:
        del form.fields["parceiro_indicador"]


def _tornar_senha_opcional(form):
    """Torna campos de senha opcionais no formulário."""
    if 'senha' in form.fields:
        form.fields['senha'].required = False
    if 'confirmar_senha' in form.fields:
        form.fields['confirmar_senha'].required = False


def _preencher_email_cliente_principal(form, cliente_principal, usar_dados_principal, user):
    """Preenche email do cliente principal no formulário."""
    if not (usar_dados_principal and cliente_principal and 'email' in form.data):
        return form
    
    from django.http import QueryDict
    if isinstance(form.data, QueryDict):
        form_data = form.data.copy()
        form_data['email'] = cliente_principal.email
        form = ClienteConsultoriaForm(
            data=form_data,
            user=user,
            cliente_principal=cliente_principal,
            usar_dados_principal=usar_dados_principal
        )
        _remover_parceiro_indicador(form)
    
    return form


def _preparar_formulario_dependente_post(request, primeira_etapa, etapas=None, cliente_principal=None):
    """Prepara formulário de dependente a partir de dados POST."""
    usar_dados_principal = request.POST.get('usar_dados_cliente_principal') == 'on'
    
    # Criar formulário com a flag usar_dados_principal desde o início
    form = ClienteConsultoriaForm(
        data=request.POST,
        user=request.user,
        cliente_principal=cliente_principal,
        usar_dados_principal=usar_dados_principal
    )
    _remover_parceiro_indicador(form)
    
    # Preencher email se estiver usando dados do cliente principal
    form = _preencher_email_cliente_principal(form, cliente_principal, usar_dados_principal, request.user)
    
    # Tornar senha opcional se estiver usando dados do cliente principal
    if usar_dados_principal:
        _tornar_senha_opcional(form)
    
    # Configurar campos do formulário
    _configurar_campos_formulario_dependente(form, primeira_etapa, etapas)
    
    # Garantir que senha não é obrigatória se usar_dados_principal (após todas as configurações)
    if usar_dados_principal:
        _tornar_senha_opcional(form)
    
    return form


def _salvar_dependente(form, cliente_principal, primeira_etapa, user, usar_dados_principal=False):
    """Salva um dependente vinculado ao cliente principal."""
    dependente = form.save(commit=False)
    dependente.cliente_principal = cliente_principal
    dependente.assessor_responsavel = cliente_principal.assessor_responsavel
    # Dependentes herdam o parceiro indicador do cliente principal
    dependente.parceiro_indicador = cliente_principal.parceiro_indicador
    if not dependente.criado_por_id:
        dependente.criado_por = user
    
    # Se deve usar dados do cliente principal, copiar hash da senha
    if usar_dados_principal:
        dependente.email = cliente_principal.email
        dependente.senha = cliente_principal.senha
        logger.info(f"ℹ️ Dependente {dependente.nome} usando email e senha do cliente principal")
    
    dependente.save()
    
    # Marcar etapa de dados pessoais como concluída
    if primeira_etapa.campo_booleano:
        setattr(dependente, primeira_etapa.campo_booleano, True)
        dependente.save(update_fields=[primeira_etapa.campo_booleano])


def _armazenar_dependente_temporario_na_sessao(request, dados_dependente: dict):
    """
    Armazena um dependente temporário na sessão.
    
    Os dependentes são armazenados temporariamente na sessão e só são salvos
    no banco quando o cliente principal for finalizado.
    
    Args:
        request: HttpRequest com a sessão
        dados_dependente: Dicionário com os dados do dependente (cleaned_data do form)
    
    Debug:
        Adiciona log na sessão quando dependente é armazenado
    """
    nome_dependente = dados_dependente.get('nome', 'Desconhecido')
    logger.info(f"💾 Armazenando dependente temporário na sessão: {nome_dependente}")
    logger.info(f"📋 Dados do dependente antes de serializar: {dados_dependente}")
    
    dependentes_temporarios = request.session.get("dependentes_temporarios", [])
    logger.info(f"📋 Dependentes temporários existentes na sessão: {len(dependentes_temporarios)}")
    
    # Preservar confirmar_senha para dependentes (necessário para validação posterior)
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
    """Processa um dependente válido e armazena na sessão."""
    logger.info("✅ Formulário de dependente válido. Armazenando na sessão...")
    
    dados_dependente = form_dependente_post.cleaned_data.copy()
    
    # Verificar se deve usar dados do cliente principal
    usar_dados_principal = request.POST.get('usar_dados_cliente_principal') == 'on'
    if usar_dados_principal:
        dados_dependente['usar_dados_cliente_principal'] = True
        logger.info("ℹ️ Dependente configurado para usar email e senha do cliente principal")
    
    # Verificar se está editando um dependente existente
    dependente_editando_index = request.session.get('dependente_editando_index')
    if dependente_editando_index is not None:
        # Atualizar dependente existente
        dependentes_temporarios = request.session.get("dependentes_temporarios", [])
        if 0 <= dependente_editando_index < len(dependentes_temporarios):
            dados_serializados = _serializar_dados_para_sessao(dados_dependente, preservar_confirmar_senha=True)
            dependentes_temporarios[dependente_editando_index] = dados_serializados
            request.session["dependentes_temporarios"] = dependentes_temporarios
            # Limpar dados de edição
            request.session.pop('dependente_editando_index', None)
            request.session.pop('dependente_editando_dados', None)
            request.session.modified = True
            nome_dependente = dados_dependente.get('nome', 'Desconhecido')
            messages.success(request, f"{nome_dependente} atualizado. Será salvo ao finalizar o cadastro.")
            logger.info(f"✅ Dependente {nome_dependente} atualizado com sucesso. Redirecionando...")
            return redirect(f"{request.path}?etapa_id={etapa_atual.pk}")
    
    # Adicionar novo dependente
    _armazenar_dependente_temporario_na_sessao(request, dados_dependente)
    nome_dependente = dados_dependente.get('nome', 'Desconhecido')
    messages.success(request, f"{nome_dependente} adicionado. Será salvo ao finalizar o cadastro.")
    logger.info(f"✅ Dependente {nome_dependente} adicionado com sucesso. Redirecionando...")
    return redirect(f"{request.path}?etapa_id={etapa_atual.pk}")

def _obter_cliente_principal_dependente(dados_temporarios, cliente_temporario, usar_dados_principal):
    """Obtém o cliente principal para o formulário de dependente."""
    cliente_principal = None
    
    if dados_temporarios and 'cliente_principal_id' in dados_temporarios:
        cliente_principal_id = dados_temporarios['cliente_principal_id']
        with suppress(ClienteConsultoria.DoesNotExist):
            cliente_principal = ClienteConsultoria.objects.get(pk=cliente_principal_id)
    elif cliente_temporario and isinstance(cliente_temporario, ClienteConsultoria) and cliente_temporario.is_principal:
        cliente_principal = cliente_temporario
    
    # Se não tem cliente_principal salvo, usar cliente_temporario se tiver email
    if usar_dados_principal and not cliente_principal and cliente_temporario:
        cliente_principal = cliente_temporario
    
    return cliente_principal


def _garantir_assessor_no_formulario(form_dependente_post, cliente_temporario, dados_temporarios, cliente_principal, request, primeira_etapa):
    """Garante que assessor_responsavel esteja definido no formulário."""
    if form_dependente_post.data.get('assessor_responsavel'):
        return form_dependente_post
    
    # Obter assessor_id usando a mesma lógica de outras funções
    assessor_id = _obter_assessor_id_dependente(request, cliente_temporario, dados_temporarios)
    
    if not assessor_id:
        return form_dependente_post
    
    # Adicionar assessor aos dados do formulário
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
    """
    Processa o cadastro de um dependente na etapa de membros.
    
    NOTA IMPORTANTE: Como o cliente principal ainda não está salvo no banco,
    os dependentes serão armazenados temporariamente na sessão e vinculados
    ao cliente principal quando ele for finalizado.
    
    Args:
        request: HttpRequest com dados POST
        etapa_atual: EtapaCadastroCliente atual (deve ser etapa_membros)
        cliente_temporario: ClienteConsultoria temporário da sessão
        etapas: QuerySet de todas as etapas
    
    Returns:
        tuple: (HttpResponseRedirect | None, ClienteConsultoriaForm | None)
            - Se válido: (redirect, None)
            - Se inválido: (None, form_com_erros)
    """
    if not (primeira_etapa := etapas.filter(ativo=True).order_by("ordem").first()):
        return None, None
    
    # Obter dados temporários e cliente_principal
    dados_temporarios = _obter_dados_temporarios_sessao(request)
    usar_dados_principal = request.POST.get('usar_dados_cliente_principal') == 'on'
    cliente_principal = _obter_cliente_principal_dependente(dados_temporarios, cliente_temporario, usar_dados_principal)
    
    # Preparar formulário
    form_dependente_post = _preparar_formulario_dependente_post(
        request, primeira_etapa, etapas, cliente_principal=cliente_principal
    )
    
    # Garantir que assessor_responsavel esteja definido
    form_dependente_post = _garantir_assessor_no_formulario(
        form_dependente_post, cliente_temporario, dados_temporarios, cliente_principal, request, primeira_etapa
    )
    
    # Validar e processar
    campos_primeira_etapa = CampoEtapaCliente.objects.filter(
        etapa=primeira_etapa, ativo=True
    ).exclude(nome_campo="parceiro_indicador").order_by("ordem", "nome_campo")
    
    if form_dependente_post.is_valid():
        return _processar_dependente_valido(request, form_dependente_post, etapa_atual), None
    
    # Exibir erros
    logger.error(f"❌ Formulário de dependente inválido: {form_dependente_post.errors}")
    campos_etapa_nomes = set(campos_primeira_etapa.values_list("nome_campo", flat=True))
    _exibir_erros_formulario(request, form_dependente_post, campos_etapa_nomes, prefixo="Dependente - ")
    return None, form_dependente_post


def _preparar_contexto_dependentes(request, etapa_atual, cliente_temporario, etapas, contexto, form_dependente):
    """
    Prepara o contexto para cadastro de dependentes na etapa de membros.
    
    Como o cliente principal ainda não está salvo, lista dependentes temporários da sessão.
    
    Args:
        request: HttpRequest com a sessão
        etapa_atual: EtapaCadastroCliente atual (deve ser etapa_membros)
        cliente_temporario: ClienteConsultoria temporário da sessão
        etapas: QuerySet de todas as etapas
        contexto: Dicionário de contexto a ser atualizado
        form_dependente: ClienteConsultoriaForm para dependente ou None
    """
    if not (primeira_etapa := etapas.filter(ativo=True).order_by("ordem").first()):
        return
    
    campos_primeira_etapa = CampoEtapaCliente.objects.filter(
        etapa=primeira_etapa, ativo=True
    ).exclude(nome_campo="parceiro_indicador").order_by("ordem", "nome_campo")
    
    # Se houve erro no formulário de dependente (POST), usar o form com dados, senão criar novo
    if form_dependente is None:
        form_dependente = _criar_formulario_dependente(request, cliente_temporario, primeira_etapa, etapas)
    
    # Obter dependentes temporários da sessão
    dependentes_temporarios = request.session.get("dependentes_temporarios", [])
    
    # Obter campos de todas as etapas para dependentes (dados pessoais, endereço, passaporte)
    etapas_dependente = etapas.filter(ativo=True).exclude(campo_booleano='etapa_membros').order_by("ordem")
    campos_dependente = []
    for etapa in etapas_dependente:
        campos_etapa = CampoEtapaCliente.objects.filter(
            etapa=etapa, ativo=True
        ).exclude(nome_campo="parceiro_indicador").order_by("ordem", "nome_campo")
        campos_dependente.extend(campos_etapa)
    
    # Verificar se está editando um dependente para passar dados ao contexto
    dependente_editando_dados = request.session.get('dependente_editando_dados')
    
    # Calcular assessor_id: usar do cliente temporário ou do consultor logado como fallback
    assessor_id = None
    if cliente_temporario and hasattr(cliente_temporario, 'assessor_responsavel_id') and cliente_temporario.assessor_responsavel_id:
        assessor_id = cliente_temporario.assessor_responsavel_id
    else:
        # Tentar obter dos dados temporários
        dados_temporarios = _obter_dados_temporarios_sessao(request)
        if dados_temporarios and (assessor_valor := dados_temporarios.get('assessor_responsavel')):
            # Converter para int se necessário
            try:
                assessor_id = int(assessor_valor) if isinstance(assessor_valor, str) else assessor_valor
            except (ValueError, TypeError):
                assessor_id = None
        # Se ainda não tem, usar o consultor logado
        if not assessor_id:
            if consultor := obter_consultor_usuario(request.user):
                assessor_id = consultor.pk
    
    contexto['primeira_etapa'] = primeira_etapa
    contexto['campos_primeira_etapa'] = campos_primeira_etapa
    contexto['campos_dependente'] = campos_dependente  # Todos os campos (dados pessoais, endereço, passaporte)
    contexto['etapas_dependente'] = etapas_dependente  # Etapas para dependentes
    contexto['form_dependente'] = form_dependente
    contexto['dependentes_temporarios'] = dependentes_temporarios  # Lista de dicionários
    contexto['dependentes'] = []  # Lista vazia pois cliente ainda não está salvo
    contexto['dependente_editando_dados'] = dependente_editando_dados  # Dados do dependente sendo editado (se houver)
    contexto['assessor_id'] = assessor_id  # ID do assessor para o campo hidden


def _processar_cancelamento_cadastro(request):
    """
    Processa o cancelamento do cadastro de cliente.
    
    Limpa todos os dados temporários da sessão e redireciona para home.
    
    Args:
        request: HttpRequest com a sessão
    
    Returns:
        HttpResponseRedirect: Redirecionamento para system:home_clientes
    
    Debug:
        Adiciona log na sessão indicando cancelamento
    """
    # Adicionar log de debug
    _adicionar_log_debug(request, "Cadastro cancelado pelo usuário")
    
    # Limpar dados temporários
    _limpar_dados_temporarios_sessao(request)
    
    # Limpar dependentes temporários
    if "dependentes_temporarios" in request.session:
        request.session.pop("dependentes_temporarios", None)
    
    # Limpar flags de finalização
    keys_to_remove = [key for key in request.session.keys() if key.startswith('cadastro_finalizado_')]
    for key in keys_to_remove:
        request.session.pop(key, None)
    
    request.session.modified = True
    messages.info(request, "Cadastro cancelado.")
    return redirect("system:home_clientes")


def _processar_remover_dependente(request, etapa_atual):
    """
    Processa a remoção de um dependente temporário da sessão.
    
    Remove um dependente específico da lista de dependentes temporários
    sem afetar o cadastro principal.
    
    Args:
        request: HttpRequest com a sessão
        etapa_atual: EtapaCadastroCliente atual (deve ser etapa_membros)
    
    Returns:
        HttpResponseRedirect: Redirecionamento para a mesma etapa
    """
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
    
    # Remover o dependente da lista
    dependentes_temporarios.pop(dependente_index)
    request.session["dependentes_temporarios"] = dependentes_temporarios
    request.session.modified = True
    
    logger.info(f"🗑️ Dependente temporário removido: {nome_dependente} (índice {dependente_index})")
    _adicionar_log_debug(request, f"Dependente '{nome_dependente}' removido temporariamente")
    messages.success(request, f"{nome_dependente} removido da lista de membros.")
    
    return redirect(f"{request.path}?etapa_id={etapa_atual.pk}")


def _processar_editar_dependente(request, etapa_atual):
    """
    Processa a edição de um dependente temporário da sessão.
    
    Carrega os dados do dependente no formulário para edição.
    
    Args:
        request: HttpRequest com a sessão
        etapa_atual: EtapaCadastroCliente atual (deve ser etapa_membros)
    
    Returns:
        HttpResponseRedirect: Redirecionamento para a mesma etapa com dados do dependente carregados
    """
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
    
    # Armazenar o índice do dependente sendo editado e os dados na sessão
    request.session['dependente_editando_index'] = dependente_index
    request.session['dependente_editando_dados'] = dependente_para_editar
    request.session.modified = True
    
    logger.info(f"✏️ Editando dependente {nome_dependente} (índice {dependente_index})")
    messages.info(request, f"Editando {nome_dependente}. Modifique os dados e clique em 'Salvar Alterações' para atualizar.")
    return redirect(f"{request.path}?etapa_id={etapa_atual.pk}&editando_dependente=true")


def _preparar_dados_iniciais_formulario(request, cliente_temporario):
    """Prepara dados iniciais do formulário a partir da sessão."""
    if not request.POST and cliente_temporario:
        if dados_temporarios := _obter_dados_temporarios_sessao(request):
            dados_iniciais = dados_temporarios.copy()
            dados_iniciais.pop('confirmar_senha', None)
            return dados_iniciais
    return None


def _extrair_assessor_id_sessao(dados_iniciais):
    """Extrai e converte assessor_responsavel dos dados iniciais para ID."""
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
    """Cria formulário para requisição GET com dados da sessão."""
    form = ClienteConsultoriaForm(data=dados_iniciais, instance=None, user=request.user)
    
    assessor_id_sessao = _extrair_assessor_id_sessao(dados_iniciais) if dados_iniciais else None
    
    if assessor_id_sessao and dados_iniciais:
        dados_iniciais['assessor_responsavel'] = assessor_id_sessao
        form = ClienteConsultoriaForm(data=dados_iniciais, instance=None, user=request.user)
        form.fields["assessor_responsavel"].initial = assessor_id_sessao
    
    _configurar_campos_formulario(form, etapa_atual)
    return form


def _limpar_flags_finalizacao(request):
    """Limpa flags de finalização de cadastros anteriores, mas apenas se não estiver redirecionando para criar viagem."""
    etapa_id = request.GET.get("etapa_id")
    # Não limpar flags se estiver vindo de um redirect de finalização (sem etapa_id, GET e sem parâmetro clientes)
    # Isso evita limpar o flag antes da mensagem ser exibida
    if not etapa_id and request.method == "GET" and not request.GET.get("clientes"):
        keys_to_remove = [key for key in request.session.keys() if key.startswith('cadastro_finalizado_')]
        for key in keys_to_remove:
            request.session.pop(key, None)


def _preparar_contexto_final(request, etapa_atual, cliente_temporario, etapas, contexto, form_dependente, tem_cep_na_etapa, tem_senha_na_etapa):
    """Prepara contexto final para renderização do template."""
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
    """Cria e configura formulário de cliente."""
    # Se há POST, usar dados da sessão como initial para preservar assessor_responsavel
    initial_data = {}
    if request.POST:
        dados_temporarios = _obter_dados_temporarios_sessao(request)
        if dados_temporarios and 'assessor_responsavel' in dados_temporarios:
            assessor_id = dados_temporarios.get('assessor_responsavel')
            # Preservar assessor se o POST vier vazio
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
    """Valida se a etapa anterior foi concluída."""
    if etapa_atual.ordem <= 1 or _obter_dados_temporarios_sessao(request):
        return None
    primeira_etapa = etapas.first()
    messages.error(request, f"Complete a etapa '{primeira_etapa.nome}' primeiro.")
    return redirect(f"{request.path}?etapa_id={primeira_etapa.pk}")


def _criar_e_validar_cliente_do_banco(request) -> ClienteConsultoria:
    """Cria cliente do banco e valida assessor_responsavel."""
    logger.info("📝 Criando cliente do banco...")
    cliente = _criar_cliente_do_banco(request)
    logger.info(f"✅ Cliente criado com sucesso: {cliente.nome} (ID: {cliente.pk})")
    
    # Ensure assessor_responsavel is set if it's still None
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
    """Processa finalização quando está na etapa de membros."""
    logger.info(f"🔄 _processar_finalizacao_etapa_membros chamada - criar_viagem={criar_viagem}")
    
    if dados_temporarios := _obter_dados_temporarios_sessao(request):
        dados_temporarios['etapa_membros'] = True
        _salvar_dados_temporarios_sessao(request, dados_temporarios)
        
        try:
            cliente = _criar_e_validar_cliente_do_banco(request)
            logger.info(f"🚀 Finalizando cadastro e redirecionando (criar_viagem={criar_viagem})...")
            return _finalizar_cadastro_cliente(request, cliente, criar_viagem)
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
    """Processa finalização para outras etapas (não membros)."""
    if not form.is_valid():
        _exibir_erros_formulario(request, form, campos_etapa_nomes)
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
    """Processa finalização do cadastro."""
    if etapa_atual.campo_booleano == 'etapa_membros':
        redirect_response = _processar_finalizacao_etapa_membros(request, etapa_atual, etapas, criar_viagem)
        _adicionar_log_debug(request, f"Finalização etapa_membros - Redirect retornado: {redirect_response is not None}")
        if redirect_response:
            return redirect_response, None, None
        # Se não retornou redirect, há um erro - retornar form para exibir erros
        return None, form, form_dependente
    
    redirect_response = _processar_finalizacao_outras_etapas(request, form, etapa_atual, campos_etapa_nomes, criar_viagem)
    _adicionar_log_debug(request, f"Finalização outras etapas - Redirect retornado: {redirect_response is not None}")
    if redirect_response:
        return redirect_response, None, None
    
    # Se não retornou redirect, há um erro no formulário - retornar form para exibir erros
    return None, form, form_dependente


def _processar_avancar_etapa(request, form, etapa_atual, etapas):
    """Processa avanço para próxima etapa."""
    # Se for etapa de membros, não salvar etapa (já foi salva) e permanecer na mesma página
    if etapa_atual.campo_booleano == 'etapa_membros':
        _adicionar_log_debug(request, "Etapa 'Adicionar Membros' - permanecendo na mesma página para adicionar dependentes")
        return redirect(f"{request.path}?etapa_id={etapa_atual.pk}"), None, None
    
    _salvar_etapa_na_sessao(form, etapa_atual, request)
    
    if redirect_response := _avancar_para_proxima_etapa(etapa_atual, etapas, request.path, request):
        return redirect_response, None, None
    
    # Se não há próxima etapa, finalizar automaticamente
    _adicionar_log_debug(request, "Não há próxima etapa após avançar - finalizando cadastro automaticamente")
    try:
        cliente = _criar_cliente_do_banco(request)
        return _finalizar_cadastro_cliente(request, cliente), None, None
    except ValueError as e:
        messages.error(request, str(e))
        _adicionar_log_debug(request, f"Erro ao finalizar cadastro: {str(e)}", "error")
        return redirect("system:home_clientes"), None, None


def _log_finalizar_cadastro(request, etapa_atual):
    """Registra log quando o botão 'Finalizar Cadastro' é clicado."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print("\n" + "=" * 80, flush=True)
    print("🔥 BOTÃO 'FINALIZAR CADASTRO' FOI CLICADO!", flush=True)
    print(f"   Usuário: {request.user.username}", flush=True)
    print(f"   Etapa atual: {etapa_atual.nome}", flush=True)
    print(f"   Timestamp: {timestamp}", flush=True)
    print("=" * 80 + "\n", flush=True)
    
    logger.info("=" * 80)
    logger.info("🔥 BOTÃO 'FINALIZAR CADASTRO' FOI CLICADO!")
    logger.info(f"   Usuário: {request.user.username}")
    logger.info(f"   Etapa atual: {etapa_atual.nome}")
    logger.info(f"   Timestamp: {timestamp}")
    logger.info("=" * 80)


def _processar_post_cadastro_cliente(request, etapa_atual, etapas, campos_etapa_nomes):
    """
    Processa requisição POST do cadastro de cliente.
    
    Esta é a função principal que orquestra todo o fluxo de cadastro:
    1. Verifica a ação (cancelar, salvar, finalizar)
    2. Processa cadastro de dependentes se necessário
    3. Valida e salva dados da etapa atual na sessão
    4. Avança para próxima etapa ou finaliza cadastro
    
    Args:
        request: HttpRequest com dados POST
        etapa_atual: EtapaCadastroCliente atual
        etapas: QuerySet de todas as etapas
        campos_etapa_nomes: set de nomes de campos da etapa atual
    
    Returns:
        tuple: (HttpResponseRedirect | None, ClienteConsultoriaForm | None, ClienteConsultoriaForm | None)
            - Se houver redirect: (redirect, None, None)
            - Se houver form de dependente: (None, form_principal, form_dependente)
            - Caso contrário: (None, form_principal, None)
    
    Debug:
        Adiciona logs na sessão para cada etapa do processamento
    """
    # Log inicial para capturar QUALQUER POST
    print("\n" + "="*80, flush=True)
    print("📥 FUNÇÃO _processar_post_cadastro_cliente CHAMADA", flush=True)
    print(f"   Método: {request.method}", flush=True)
    print(f"   Path: {request.path}", flush=True)
    print(f"   POST data: {dict(request.POST)}", flush=True)
    print("="*80 + "\n", flush=True)
    
    acao = request.POST.get("acao", "salvar")
    form_type = request.POST.get("form_type", "")
    
    print(f"📥 POST RECEBIDO - Ação extraída: '{acao}' | Form Type: '{form_type}' | Etapa: {etapa_atual.nome}", flush=True)
    print(f"   Todos os valores de 'acao' no POST: {request.POST.getlist('acao')}", flush=True)
    _adicionar_log_debug(request, f"POST recebido - Ação: {acao}, Form Type: {form_type}, Etapa: {etapa_atual.nome}")
    
    if acao in ("finalizar", "finalizar_e_criar_viagem"):
        _log_finalizar_cadastro(request, etapa_atual)
    
    # Processar cancelamento
    if acao == "cancelar":
        return _processar_cancelamento_cadastro(request), None, None
    
    # Processar remoção de dependente
    if acao == "remover_dependente" and etapa_atual.campo_booleano == 'etapa_membros':
        return _processar_remover_dependente(request, etapa_atual), None, None
    
    if acao == "editar_dependente":
        if etapa_atual.campo_booleano == 'etapa_membros':
            return _processar_editar_dependente(request, etapa_atual), None, None
        messages.error(request, "Ação inválida para esta etapa.")
        return redirect(f"{request.path}?etapa_id={etapa_atual.pk}"), None, None
    
    # Processar cadastro de dependente se necessário
    form_dependente = None
    cliente_temporario = _criar_cliente_da_sessao(request)
    
    if (
        etapa_atual.campo_booleano == 'etapa_membros' 
        and cliente_temporario 
        and form_type == "dependente"
    ):
        print("🔄 Processando cadastro de dependente...", flush=True)
        redirect_response, form_dependente_result = _processar_cadastro_dependente(
            request, etapa_atual, cliente_temporario, etapas
        )
        if redirect_response:
            return redirect_response, None, None
        if form_dependente_result:
            form_dependente = form_dependente_result
    
    # Preparar e criar formulário
    dados_iniciais = _preparar_dados_iniciais_formulario(request, cliente_temporario)
    form = _criar_formulario_cliente(request, etapa_atual, dados_iniciais)
    
    # Validar etapa anterior
    if redirect_response := _validar_etapa_anterior(etapa_atual, etapas, request):
        return redirect_response, None, None
    
    # Processar finalização - DEVE SER PROCESSADO ANTES DE VALIDAR O FORMULÁRIO
    if acao in ("finalizar", "finalizar_e_criar_viagem"):
        print("▶️ Iniciando processamento de finalização do cadastro...")
        logger.info("▶️ Iniciando processamento de finalização do cadastro...")
        criar_viagem = (acao == "finalizar_e_criar_viagem")
        _adicionar_log_debug(request, f"Ação '{acao}' detectada - processando finalização (criar_viagem={criar_viagem})")
        redirect_result = _processar_finalizacao(request, form, etapa_atual, etapas, campos_etapa_nomes, form_dependente, criar_viagem)
        redirect_status = redirect_result[0] is not None
        print(f"✅ Processamento de finalização concluído - Redirect: {redirect_status}")
        logger.info(f"✅ Processamento de finalização concluído - Redirect: {redirect_status}")
        return redirect_result
    
    # Se estiver na etapa de membros e não há próxima etapa, considerar como finalizar
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
    
    # Validar e processar formulário normalmente (ação não é finalizar)
    if form.is_valid():
        return _processar_avancar_etapa(request, form, etapa_atual, etapas)
    
    # Se formulário inválido, exibir erros
    _exibir_erros_formulario(request, form, campos_etapa_nomes)
    return None, form, form_dependente


@login_required
def cadastrar_cliente_view(request):
    """
    View principal para cadastrar novo cliente em etapas configuráveis.
    
    Esta view gerencia todo o fluxo de cadastro:
    1. Carrega as etapas configuradas
    2. Determina a etapa atual
    3. Processa requisições POST (salvar etapa, finalizar, cancelar)
    4. Prepara formulário com dados da sessão (se houver)
    5. Renderiza o template com contexto completo
    
    Fluxo:
    - Durante as etapas: dados são salvos apenas na sessão
    - Ao finalizar: dados são salvos no banco e usuário é redirecionado para home
    
    Args:
        request: HttpRequest
    
    Returns:
        HttpResponse: Template renderizado ou redirecionamento
    """
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
    """Visualiza todas as informações do cliente, incluindo viagens e processos."""
    consultor = obter_consultor_usuario(request.user)
    cliente = get_object_or_404(
        ClienteConsultoria.objects.select_related(
            "assessor_responsavel",
            "cliente_principal",
            "assessor_responsavel__perfil",
        ).prefetch_related("dependentes"),
        pk=pk,
    )

    # Verificar permissão
    pode_visualizar = usuario_pode_gerenciar_todos(request.user, consultor) or (
        consultor and cliente.assessor_responsavel_id == consultor.pk
        or cliente.criado_por == request.user
    )
    
    if not pode_visualizar:
        raise PermissionDenied
    
    # Buscar viagens do cliente
    viagens = Viagem.objects.filter(
        clientes=cliente
    ).select_related(
        "pais_destino",
        "tipo_visto",
        "assessor_responsavel",
    ).prefetch_related("clientes").order_by("-data_prevista_viagem")
    
    # Buscar processos do cliente
    processos = Processo.objects.filter(
        cliente=cliente
    ).select_related(
        "viagem",
        "viagem__pais_destino",
        "viagem__tipo_visto",
        "assessor_responsavel",
    ).prefetch_related("etapas", "etapas__status").order_by("-criado_em")
    
    # Buscar registros financeiros do cliente
    registros_financeiros = Financeiro.objects.filter(
        cliente=cliente
    ).select_related(
        "viagem",
        "assessor_responsavel",
    ).order_by("-criado_em")
    
    # Status financeiro
    status_financeiro = _obter_status_financeiro_cliente(cliente)
    
    contexto = {
        "cliente": cliente,
        "viagens": viagens,
        "processos": processos,
        "registros_financeiros": registros_financeiros,
        "status_financeiro": status_financeiro,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": usuario_pode_gerenciar_todos(request.user, consultor),
    }
    
    return render(request, "client/visualizar_cliente.html", contexto)


@login_required
def editar_cliente_view(request, pk: int):
    """Formulário para editar cliente existente."""
    consultor = obter_consultor_usuario(request.user)
    cliente = get_object_or_404(
        ClienteConsultoria.objects.select_related(
            "assessor_responsavel",
            "cliente_principal",
        ).prefetch_related("dependentes"),
        pk=pk,
    )

    # Verificar permissão
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
            # O formulário já trata a senha corretamente no método save()
            cliente_atualizado = form.save()
            messages.success(request, f"{cliente_atualizado.nome} atualizado com sucesso.")
            return redirect("system:listar_clientes_view")
        messages.error(request, "Não foi possível atualizar o cliente. Verifique os campos.")
    else:
        form = ClienteConsultoriaForm(user=request.user, instance=cliente)
        # Não preencher senha ao editar
        form.fields["senha"].required = False
        form.fields["senha"].widget.attrs["placeholder"] = "Deixe em branco para manter a senha atual"
        form.fields["confirmar_senha"].required = False
        form.fields["confirmar_senha"].widget.attrs["placeholder"] = "Deixe em branco para manter a senha atual"
        # Carregar parceiro atual se existir
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
    """API para buscar endereço por CEP via AJAX."""
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
    """Retorna dados auxiliares do cliente para uso em formulários."""
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
    """Cadastra um novo dependente para um cliente principal usando apenas os campos da primeira etapa."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    cliente_principal = get_object_or_404(ClienteConsultoria, pk=pk)
    
    # Verificar permissão
    if not pode_gerenciar_todos and (not consultor or cliente_principal.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para gerenciar este cliente.")
    
    # Obter a primeira etapa (Dados Pessoais)
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
        
        # Obter todas as etapas para o formulário de dependente
        etapas = EtapaCadastroCliente.objects.filter(ativo=True).order_by("ordem")
        # Criar formulário com campos de dados pessoais, endereço e passaporte
        form = _preparar_formulario_dependente_post(request, primeira_etapa, etapas, cliente_principal=cliente_principal)
        
        if form.is_valid():
            usar_dados_principal = request.POST.get('usar_dados_cliente_principal') == 'on'
            _salvar_dependente(form, cliente_principal, primeira_etapa, request.user, usar_dados_principal=usar_dados_principal)
            messages.success(request, f"{form.cleaned_data['nome']} cadastrado como dependente com sucesso.")
            return redirect("system:cadastrar_dependente", pk=cliente_principal.pk)
        
        # Exibir apenas erros dos campos da etapa atual
        campos_etapa_nomes = set(campos_etapa.values_list("nome_campo", flat=True))
        _exibir_erros_formulario(request, form, campos_etapa_nomes)
    else:
        # Obter todas as etapas para o formulário de dependente
        etapas = EtapaCadastroCliente.objects.filter(ativo=True).order_by("ordem")
        form = _criar_formulario_dependente(request, cliente_principal, primeira_etapa, etapas)
    
    # Calcular assessor_id: usar do cliente principal ou do consultor logado como fallback
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
    """Adiciona um dependente a um cliente principal."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    cliente_principal = get_object_or_404(ClienteConsultoria, pk=pk)

    # Verificar permissão
    if not pode_gerenciar_todos and (not consultor or cliente_principal.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para gerenciar este cliente.")

    if request.method == "POST":
        if dependente_id := request.POST.get("dependente_id"):
            try:
                dependente = ClienteConsultoria.objects.get(pk=dependente_id)
                # Verificar se o dependente não é principal
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

    # Buscar clientes disponíveis para serem dependentes (que não são dependentes de ninguém)
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
    """Remove um dependente de um cliente principal."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    cliente_principal = get_object_or_404(ClienteConsultoria, pk=pk)
    dependente = get_object_or_404(ClienteConsultoria, pk=dependente_id)

    # Verificar permissão
    if not pode_gerenciar_todos and (not consultor or cliente_principal.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para gerenciar este cliente.")

    # Verificar se o dependente realmente pertence a este cliente principal
    if dependente.cliente_principal != cliente_principal:
        messages.error(request, "Este cliente não é dependente do cliente selecionado.")
        return redirect("system:editar_cliente", pk=cliente_principal.pk)

    dependente_nome = dependente.nome
    dependente.cliente_principal = None
    dependente.save()

    messages.success(request, f"{dependente_nome} removido como dependente.")
    return redirect("system:editar_cliente", pk=cliente_principal.pk)

