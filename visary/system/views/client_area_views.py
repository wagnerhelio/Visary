   
                                                   
   

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date

from system.models import (
    ClienteConsultoria,
    OpcaoSelecao,
    RespostaFormulario,
    Viagem,
)
from system.views.travel_views import _build_pergunta_estado, _obter_formulario_por_tipo_visto, _obter_tipo_visto_cliente, _pergunta_e_visivel
from system.services.form_stages import build_stage_items, filter_questions_by_stage, resolve_stage_token
from system.services.form_prefill import prefill_form_answers


def _get_cliente_from_session(request):
                                                    
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return None
    try:
        return ClienteConsultoria.objects.get(pk=cliente_id)
    except ClienteConsultoria.DoesNotExist:
        return None


def _obter_formulario_cliente(viagem, cliente):
                                                                         
                                              
    tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)
    
                                                     
    return _obter_formulario_por_tipo_visto(tipo_visto_cliente, apenas_ativo=False)


def cliente_dashboard(request):
                                                      
    cliente = _get_cliente_from_session(request)
    if not cliente:
        messages.error(request, "Você precisa fazer login para acessar esta página.")
        return redirect("login")

                                                               
    if cliente.is_principal:
                                                                               
        dependentes = cliente.dependentes.all()
        clientes_ids = [cliente.pk] + list(dependentes.values_list('pk', flat=True))
        
        viagens = (
            Viagem.objects.filter(clientes__pk__in=clientes_ids)
            .select_related("pais_destino", "tipo_visto", "assessor_responsavel")
            .prefetch_related("tipo_visto__formulario", "clientes")
            .distinct()
            .order_by("-data_prevista_viagem")
        )
    else:
                                                      
        viagens = (
            Viagem.objects.filter(clientes=cliente)
            .select_related("pais_destino", "tipo_visto", "assessor_responsavel")
            .prefetch_related("tipo_visto__formulario", "clientes")
            .order_by("-data_prevista_viagem")
        )

    contexto = {
        "cliente": cliente,
        "viagens": viagens,
    }

    return render(request, "client_area/dashboard.html", contexto)


def cliente_visualizar_formulario(request, viagem_id: int):
    cliente = _get_cliente_from_session(request)
    if not cliente:
        messages.error(request, "Você precisa fazer login para acessar esta página.")
        return redirect("login")

    viagem = get_object_or_404(
        Viagem.objects.select_related("tipo_visto__formulario"), pk=viagem_id
    )

    cliente_na_viagem = cliente in viagem.clientes.all()
    dependente_na_viagem = False
    
    if not cliente_na_viagem and cliente.is_principal:
        dependentes_ids = list(cliente.dependentes.values_list('pk', flat=True))
        dependente_na_viagem = viagem.clientes.filter(pk__in=dependentes_ids).exists()
    
    if not (cliente_na_viagem or dependente_na_viagem):
        raise PermissionDenied("Você não tem permissão para acessar esta viagem.")

    formulario = _obter_formulario_cliente(viagem, cliente)

    if not formulario or not formulario.ativo:
        messages.warning(
            request,
            "Este tipo de visto ainda não possui um formulário cadastrado ou o formulário está inativo.",
        )
        return redirect("system:cliente_dashboard")

    perguntas = (
        formulario.perguntas.filter(ativo=True)
        .prefetch_related("opcoes")
        .order_by("ordem", "pergunta")
    )

    respostas_list = RespostaFormulario.objects.filter(
        viagem=viagem, cliente=cliente
    ).select_related("resposta_selecao")
    
    respostas_existentes = {r.pergunta_id: r for r in respostas_list}

    prefill_form_answers(viagem, cliente, perguntas, respostas_existentes)

    stage_items = build_stage_items(formulario)
    stage_token = request.GET.get("etapa")
    current_stage = resolve_stage_token(stage_items, stage_token)
    stage_perguntas = filter_questions_by_stage(perguntas, current_stage)
    stage_perguntas_list = list(stage_perguntas)

    stage_index = 0
    if current_stage and stage_items:
        for i, item in enumerate(stage_items):
            if item["token"] == current_stage["token"]:
                stage_index = i
                break

    next_stage = stage_items[stage_index + 1] if stage_index + 1 < len(stage_items) else None
    prev_stage = stage_items[stage_index - 1] if stage_index > 0 else None

    respostas_ids = list(respostas_existentes.keys())

    contexto = {
        "cliente": cliente,
        "viagem": viagem,
        "formulario": formulario,
        "perguntas": stage_perguntas_list,
        "all_perguntas": perguntas,
        "respostas_existentes": respostas_existentes,
        "respostas_ids": respostas_ids,
        "stage_items": stage_items,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "prev_stage": prev_stage,
        "stage_index": stage_index,
    }

    return render(request, "client_area/visualizar_formulario.html", contexto)


def _limpar_campos_resposta(resposta):
                                            
    resposta.resposta_texto = ""
    resposta.resposta_data = None
    resposta.resposta_numero = None
    resposta.resposta_booleano = None
    resposta.resposta_selecao = None


def _atualizar_resposta_por_tipo(resposta, pergunta, valor):
                                                                        
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
    cliente = _get_cliente_from_session(request)
    if not cliente:
        messages.error(request, "Você precisa fazer login para acessar esta página.")
        return redirect("login")

    viagem = get_object_or_404(
        Viagem.objects.select_related("tipo_visto__formulario"), pk=viagem_id
    )

    if cliente not in viagem.clientes.all():
        raise PermissionDenied("Você não tem permissão para acessar esta viagem.")

    if request.method != "POST":
        return redirect("system:cliente_visualizar_formulario", viagem_id=viagem_id)

    formulario = _obter_formulario_cliente(viagem, cliente)
    if not formulario:
        messages.error(request, "Formulário não encontrado.")
        return redirect("system:cliente_dashboard")

    perguntas = (
        formulario.perguntas.filter(ativo=True)
        .prefetch_related("opcoes")
    )

    respostas_existentes = {
        r.pergunta_id: r for r in RespostaFormulario.objects.filter(viagem=viagem, cliente=cliente).select_related("resposta_selecao")
    }

    stage_items = build_stage_items(formulario)
    stage_token = request.POST.get("etapa_token")
    current_stage = resolve_stage_token(stage_items, stage_token)
    perguntas_etapa = list(filter_questions_by_stage(perguntas, current_stage))

    respostas_salvas = 0
    erros = []
    estado = _build_pergunta_estado(perguntas_etapa, request.POST, respostas_existentes)

    for pergunta in perguntas_etapa:
        campo_name = f"pergunta_{pergunta.pk}"
        valor = request.POST.get(campo_name)

        if pergunta.obrigatorio and not valor and _pergunta_e_visivel(pergunta, estado):
            erros.append(f"A pergunta '{pergunta.pergunta}' é obrigatória.")
            continue

        resposta, _ = RespostaFormulario.objects.get_or_create(
            viagem=viagem,
            cliente=cliente,
            pergunta=pergunta,
            defaults={},
        )

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
            f"Etapa '{current_stage['nome'] if current_stage else 'Atual'}' salva com sucesso! {respostas_salvas} resposta(s) registrada(s).",
        )

    next_action = request.POST.get("next_action")
    if next_action == "next" and current_stage:
        next_stage = None
        for i, item in enumerate(stage_items):
            if item["token"] == current_stage["token"] and i + 1 < len(stage_items):
                next_stage = stage_items[i + 1]
                break
        if next_stage:
            return redirect(f"{reverse('system:cliente_visualizar_formulario', args=[viagem_id])}?etapa={next_stage['token'].replace(':', '%3A')}")
        return redirect("system:cliente_visualizar_formulario", viagem_id=viagem_id)
    elif next_action == "finish":
        return redirect("system:cliente_visualizar_formulario", viagem_id=viagem_id)
    else:
        stage_param = f"?etapa={current_stage['token'].replace(':', '%3A')}" if current_stage else ""
        return redirect(f"{reverse('system:cliente_visualizar_formulario', args=[viagem_id])}{stage_param}")

