"""
Views da área do cliente (dashboard e formulários).
"""

from contextlib import suppress
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date

from consultancy.models import (
    ClienteConsultoria,
    ClienteViagem,
    FormularioVisto,
    OpcaoSelecao,
    PerguntaFormulario,
    RespostaFormulario,
    Viagem,
)
from system.views.travel_views import _obter_formulario_por_tipo_visto, _obter_tipo_visto_cliente


def _get_cliente_from_session(request):
    """Obtém o cliente da sessão ou retorna None."""
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return None
    try:
        return ClienteConsultoria.objects.get(pk=cliente_id)
    except ClienteConsultoria.DoesNotExist:
        return None


def _obter_formulario_cliente(viagem, cliente):
    """Obtém o formulário do cliente baseado no tipo_visto individual."""
    # Obter o tipo_visto individual do cliente
    tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)
    
    # Buscar formulário diretamente do banco de dados
    return _obter_formulario_por_tipo_visto(tipo_visto_cliente, apenas_ativo=False)


def cliente_dashboard(request):
    """Dashboard do cliente mostrando suas viagens."""
    cliente = _get_cliente_from_session(request)
    if not cliente:
        messages.error(request, "Você precisa fazer login para acessar esta página.")
        return redirect("login")

    # Buscar viagens vinculadas ao cliente
    viagens = (
        Viagem.objects.filter(clientes=cliente)
        .select_related("pais_destino", "tipo_visto", "assessor_responsavel")
        .prefetch_related("tipo_visto__formulario__perguntas")
        .order_by("-data_prevista_viagem")
    )

    contexto = {
        "cliente": cliente,
        "viagens": viagens,
    }

    return render(request, "client_area/dashboard.html", contexto)


def cliente_visualizar_formulario(request, viagem_id: int):
    """Visualiza e responde o formulário vinculado à viagem."""
    cliente = _get_cliente_from_session(request)
    if not cliente:
        messages.error(request, "Você precisa fazer login para acessar esta página.")
        return redirect("login")

    viagem = get_object_or_404(
        Viagem.objects.select_related("tipo_visto__formulario"), pk=viagem_id
    )

    # Verificar se o cliente está vinculado à viagem
    if cliente not in viagem.clientes.all():
        raise PermissionDenied("Você não tem permissão para acessar esta viagem.")

    formulario = _obter_formulario_cliente(viagem, cliente)

    if not formulario or not formulario.ativo:
        messages.warning(
            request,
            "Este tipo de visto ainda não possui um formulário cadastrado ou o formulário está inativo.",
        )
        return redirect("system:cliente_dashboard")

    # Buscar perguntas ativas ordenadas
    perguntas = (
        formulario.perguntas.filter(ativo=True)
        .prefetch_related("opcoes")
        .order_by("ordem", "pergunta")
    )

    # Buscar respostas existentes - criar lista de tuplas para template
    respostas_list = RespostaFormulario.objects.filter(
        viagem=viagem, cliente=cliente
    ).select_related("resposta_selecao")
    
    # Criar dicionário para acesso fácil no template
    respostas_existentes = {r.pergunta_id: r for r in respostas_list}
    
    # Criar também uma lista de IDs para verificação rápida
    respostas_ids = list(respostas_existentes.keys())

    contexto = {
        "cliente": cliente,
        "viagem": viagem,
        "formulario": formulario,
        "perguntas": perguntas,
        "respostas_existentes": respostas_existentes,
        "respostas_ids": respostas_ids,
    }

    return render(request, "client_area/visualizar_formulario.html", contexto)


def _limpar_campos_resposta(resposta):
    """Limpa todos os campos de resposta."""
    resposta.resposta_texto = ""
    resposta.resposta_data = None
    resposta.resposta_numero = None
    resposta.resposta_booleano = None
    resposta.resposta_selecao = None


def _atualizar_resposta_por_tipo(resposta, pergunta, valor):
    """Atualiza a resposta de acordo com o tipo de campo da pergunta."""
    _limpar_campos_resposta(resposta)
    
    if pergunta.tipo_campo == "texto":
        resposta.resposta_texto = valor or ""
    elif pergunta.tipo_campo == "data":
        resposta.resposta_data = parse_date(valor) if valor else None
    elif pergunta.tipo_campo == "numero":
        if valor:
            try:
                resposta.resposta_numero = Decimal(valor)
            except (InvalidOperation, ValueError) as e:
                raise ValueError(f"Valor inválido para a pergunta '{pergunta.pergunta}'.") from e
    elif pergunta.tipo_campo == "booleano":
        resposta.resposta_booleano = valor == "sim" if valor else None
    elif pergunta.tipo_campo == "selecao":
        if valor:
            try:
                opcao_id = int(valor)
                resposta.resposta_selecao = OpcaoSelecao.objects.get(pk=opcao_id, pergunta=pergunta)
            except (ValueError, OpcaoSelecao.DoesNotExist) as e:
                raise ValueError(f"Opção inválida para a pergunta '{pergunta.pergunta}'.") from e


def cliente_salvar_resposta(request, viagem_id: int):
    """Salva ou atualiza uma resposta do formulário."""
    cliente = _get_cliente_from_session(request)
    if not cliente:
        messages.error(request, "Você precisa fazer login para acessar esta página.")
        return redirect("login")

    viagem = get_object_or_404(
        Viagem.objects.select_related("tipo_visto__formulario"), pk=viagem_id
    )

    # Verificar se o cliente está vinculado à viagem
    if cliente not in viagem.clientes.all():
        raise PermissionDenied("Você não tem permissão para acessar esta viagem.")

    if request.method != "POST":
        return redirect("system:cliente_visualizar_formulario", viagem_id=viagem_id)

    formulario = _obter_formulario_cliente(viagem, cliente)
    if not formulario:
        messages.error(request, "Formulário não encontrado.")
        return redirect("system:cliente_dashboard")

    # Processar todas as respostas enviadas
    perguntas = formulario.perguntas.filter(ativo=True)
    respostas_salvas = 0
    erros = []

    for pergunta in perguntas:
        campo_name = f"pergunta_{pergunta.pk}"
        valor = request.POST.get(campo_name)

        # Verificar se é obrigatório
        if pergunta.obrigatorio and not valor:
            erros.append(f"A pergunta '{pergunta.pergunta}' é obrigatória.")
            continue

        # Buscar ou criar resposta
        resposta, _ = RespostaFormulario.objects.get_or_create(
            viagem=viagem,
            cliente=cliente,
            pergunta=pergunta,
            defaults={},
        )

        # Atualizar resposta de acordo com o tipo
        try:
            _atualizar_resposta_por_tipo(resposta, pergunta, valor)
            resposta.save()
            respostas_salvas += 1
        except ValueError as e:
            erros.append(str(e))

    if erros:
        for erro in erros:
            messages.error(request, erro)
    else:
        messages.success(
            request,
            f"Formulário salvo com sucesso! {respostas_salvas} resposta(s) registrada(s).",
        )

    return redirect("system:cliente_visualizar_formulario", viagem_id=viagem_id)

