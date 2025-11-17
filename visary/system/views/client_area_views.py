"""
Views da área do cliente (dashboard e formulários).
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from consultancy.models import (
    ClienteConsultoria,
    FormularioVisto,
    PerguntaFormulario,
    RespostaFormulario,
    Viagem,
)


def _get_cliente_from_session(request):
    """Obtém o cliente da sessão ou retorna None."""
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return None
    try:
        return ClienteConsultoria.objects.get(pk=cliente_id)
    except ClienteConsultoria.DoesNotExist:
        return None


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

    formulario = None
    try:
        formulario = viagem.tipo_visto.formulario
    except FormularioVisto.DoesNotExist:
        formulario = None

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

    try:
        formulario = viagem.tipo_visto.formulario
    except FormularioVisto.DoesNotExist:
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
        resposta, created = RespostaFormulario.objects.get_or_create(
            viagem=viagem,
            cliente=cliente,
            pergunta=pergunta,
            defaults={},
        )

        # Atualizar resposta de acordo com o tipo
        if pergunta.tipo_campo == "texto":
            resposta.resposta_texto = valor or ""
            resposta.resposta_data = None
            resposta.resposta_numero = None
            resposta.resposta_booleano = None
            resposta.resposta_selecao = None
        elif pergunta.tipo_campo == "data":
            from django.utils.dateparse import parse_date
            resposta.resposta_data = parse_date(valor) if valor else None
            resposta.resposta_texto = ""
            resposta.resposta_numero = None
            resposta.resposta_booleano = None
            resposta.resposta_selecao = None
        elif pergunta.tipo_campo == "numero":
            from decimal import Decimal, InvalidOperation
            try:
                resposta.resposta_numero = Decimal(valor) if valor else None
            except (InvalidOperation, ValueError):
                erros.append(f"Valor inválido para a pergunta '{pergunta.pergunta}'.")
                continue
            resposta.resposta_texto = ""
            resposta.resposta_data = None
            resposta.resposta_booleano = None
            resposta.resposta_selecao = None
        elif pergunta.tipo_campo == "booleano":
            resposta.resposta_booleano = valor == "sim" if valor else None
            resposta.resposta_texto = ""
            resposta.resposta_data = None
            resposta.resposta_numero = None
            resposta.resposta_selecao = None
        elif pergunta.tipo_campo == "selecao":
            from consultancy.models import OpcaoSelecao
            try:
                opcao_id = int(valor) if valor else None
                resposta.resposta_selecao = (
                    OpcaoSelecao.objects.get(pk=opcao_id, pergunta=pergunta)
                    if opcao_id
                    else None
                )
            except (ValueError, OpcaoSelecao.DoesNotExist):
                erros.append(f"Opção inválida para a pergunta '{pergunta.pergunta}'.")
                continue
            resposta.resposta_texto = ""
            resposta.resposta_data = None
            resposta.resposta_numero = None
            resposta.resposta_booleano = None

        resposta.save()
        respostas_salvas += 1

    if erros:
        for erro in erros:
            messages.error(request, erro)
    else:
        messages.success(
            request,
            f"Formulário salvo com sucesso! {respostas_salvas} resposta(s) registrada(s).",
        )

    return redirect("system:cliente_visualizar_formulario", viagem_id=viagem_id)

