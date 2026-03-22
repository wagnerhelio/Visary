from contextlib import suppress
from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Q, Count, Sum
from django.shortcuts import redirect, render

from system.models import ClienteConsultoria, ClienteViagem, FormularioVisto, Processo, RespostaFormulario, Viagem
from system.models.financial_models import Financeiro, StatusFinanceiro


def _get_partner_from_session(request):
    partner_id = request.session.get("partner_id")
    if not partner_id:
        return None
    try:
        return type("Partner", (), {"pk": partner_id, "nome": request.session.get("partner_nome", "")})()
    except Exception:
        return None


def _parse_positive_int(value):
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _selecionar_prioritarios(prioritarios, secundarios, limite):
    selecionados = []
    vistos = set()
    for item in prioritarios:
        if item in vistos:
            continue
        vistos.add(item)
        selecionados.append(item)
        if len(selecionados) >= limite:
            return selecionados
    for item in secundarios:
        if item in vistos:
            continue
        vistos.add(item)
        selecionados.append(item)
        if len(selecionados) >= limite:
            break
    return selecionados


def _obter_status_financeiro_cliente(cliente):
    financeiro = Financeiro.objects.filter(cliente=cliente).order_by("-criado_em").first()
    if not financeiro:
        return None
    return financeiro.get_status_display()


def _obter_status_formulario_cliente(cliente):
    total_perguntas = 0
    total_respostas = 0
    cliente_viagens = ClienteViagem.objects.filter(cliente=cliente).select_related("viagem")
    for cv in cliente_viagens:
        tipo_visto = cv.tipo_visto or cv.viagem.tipo_visto
        if not tipo_visto:
            continue
        formulario = (
            FormularioVisto.objects.filter(tipo_visto=tipo_visto, ativo=True)
            .annotate(total=Count("perguntas", filter=Q(perguntas__ativo=True)))
            .first()
        )
        if formulario:
            total_perguntas += formulario.total
            total_respostas += RespostaFormulario.objects.filter(
                viagem=cv.viagem, cliente=cliente
            ).count()
    if total_perguntas == 0:
        status = "Sem formulario"
    elif total_respostas == 0:
        status = "Nao preenchido"
    elif total_respostas >= total_perguntas:
        status = "Completo"
    else:
        status = "Parcial"
    return {"status": status, "total_perguntas": total_perguntas, "total_respostas": total_respostas}


def _obter_tipo_visto_cliente(viagem, cliente):
    with suppress(ClienteViagem.DoesNotExist):
        cliente_viagem = ClienteViagem.objects.select_related("tipo_visto__formulario").get(
            viagem=viagem, cliente=cliente
        )
        if cliente_viagem.tipo_visto:
            return cliente_viagem.tipo_visto
    return viagem.tipo_visto


def _obter_formulario_por_tipo_visto(tipo_visto, apenas_ativo=True):
    if not tipo_visto or not hasattr(tipo_visto, "pk") or not tipo_visto.pk:
        return None
    try:
        if apenas_ativo:
            return FormularioVisto.objects.select_related("tipo_visto").get(
                tipo_visto_id=tipo_visto.pk, ativo=True
            )
        return FormularioVisto.objects.select_related("tipo_visto").get(tipo_visto_id=tipo_visto.pk)
    except FormularioVisto.DoesNotExist:
        return None


def parceiro_dashboard(request):
    partner = _get_partner_from_session(request)
    if not partner:
        messages.error(request, "Voce precisa fazer login para acessar a area do parceiro.")
        return redirect("login")

    dashboard_limite = 10
    dias_proximidade_viagem = 30
    hoje = date.today()

    filtros_painel = {
        "cliente": request.GET.get("cliente", "").strip(),
        "visto": request.GET.get("visto", "").strip(),
        "formulario": request.GET.get("formulario", "").strip(),
    }

    selected_cliente_id = _parse_positive_int(filtros_painel["cliente"])
    selected_visto_id = _parse_positive_int(filtros_painel["visto"])

    clientes_base = ClienteConsultoria.objects.filter(parceiro_indicador_id=partner.pk)

    if selected_cliente_id:
        ids_cliente = {selected_cliente_id}
        cliente_filter = (
            clientes_base.filter(pk=selected_cliente_id).select_related("cliente_principal").first()
        )
        if cliente_filter and cliente_filter.cliente_principal_id:
            ids_cliente.add(cliente_filter.cliente_principal_id)
        elif cliente_filter:
            ids_cliente.update(cliente_filter.dependentes.values_list("pk", flat=True))
        clientes_base = clientes_base.filter(pk__in=ids_cliente)

    if selected_visto_id:
        clientes_base = clientes_base.filter(viagens__tipo_visto_id=selected_visto_id).distinct()

    clientes_ids = list(clientes_base.values_list("pk", flat=True))

    clientes_qs = (
        clientes_base.select_related("assessor_responsavel", "criado_por", "parceiro_indicador")
        .prefetch_related("dependentes", "viagens")
        .order_by("-criado_em")
    )

    processos_qs = (
        Processo.objects.filter(cliente__pk__in=clientes_ids)
        .select_related("viagem", "viagem__pais_destino", "viagem__tipo_visto", "cliente", "assessor_responsavel")
        .prefetch_related("etapas")
        .order_by("-criado_em")
    )

    viagens_qs = (
        Viagem.objects.filter(clientes__pk__in=clientes_ids)
        .select_related("pais_destino", "tipo_visto", "assessor_responsavel")
        .prefetch_related("clientes")
        .distinct()
        .order_by("-data_prevista_viagem")
    )

    if selected_visto_id:
        processos_qs = processos_qs.filter(viagem__tipo_visto_id=selected_visto_id)
        viagens_qs = viagens_qs.filter(tipo_visto_id=selected_visto_id)

    total_clientes = clientes_base.count()
    total_dependentes = clientes_base.filter(cliente_principal__isnull=False).count()
    total_viagens = viagens_qs.count()
    total_viagens_proximas = viagens_qs.filter(
        data_prevista_viagem__gte=hoje,
        data_prevista_viagem__lte=hoje + timedelta(days=dias_proximidade_viagem),
    ).count()
    total_viagens_concluidas = viagens_qs.filter(data_prevista_retorno__lt=hoje).count()
    total_processos = processos_qs.count()
    total_processos_andamento = (
        processos_qs.filter(Q(etapas__concluida=False) | Q(etapas__isnull=True)).distinct().count()
    )
    total_processos_concluidos = max(total_processos - total_processos_andamento, 0)
    total_formularios = (
        RespostaFormulario.objects.filter(cliente__pk__in=clientes_ids)
        .values("viagem", "cliente")
        .distinct()
        .count()
    )

    def build_cliente_item(cliente):
        status_financeiro = _obter_status_financeiro_cliente(cliente)
        status_formulario = _obter_status_formulario_cliente(cliente)
        return {
            "cliente": cliente,
            "status_financeiro": status_financeiro,
            "status_formulario": status_formulario["status"],
            "total_perguntas": status_formulario["total_perguntas"],
            "total_respostas": status_formulario["total_respostas"],
        }

    clientes_com_status = [build_cliente_item(c) for c in clientes_qs[:dashboard_limite]]

    if filtros_painel["formulario"]:
        clientes_com_status = [
            item
            for item in clientes_com_status
            if item["status_formulario"].lower().replace("ã", "a")
            .replace("á", "a")
            .replace("ç", "c")
            .replace(" ", "-")
            == filtros_painel["formulario"]
        ]

    processos_recentes_ids = list(processos_qs.values_list("pk", flat=True)[:dashboard_limite])
    processos_nao_finalizados_ids = list(
        processos_qs.filter(Q(etapas__concluida=False) | Q(etapas__isnull=True))
        .values_list("pk", flat=True)
        .distinct()
    )
    processos_ids_display = _selecionar_prioritarios(
        processos_nao_finalizados_ids, processos_recentes_ids, dashboard_limite
    )
    processos_display = list(processos_qs.filter(pk__in=processos_ids_display))
    ordem_processos = {pk: idx for idx, pk in enumerate(processos_ids_display)}
    processos_display.sort(key=lambda processo: ordem_processos.get(processo.pk, dashboard_limite + 1))

    viagens_recentes_ids = list(viagens_qs.order_by("-criado_em").values_list("pk", flat=True)[:dashboard_limite])
    viagens_proximas_ids = list(
        viagens_qs.filter(
            data_prevista_viagem__gte=hoje,
            data_prevista_viagem__lte=hoje + timedelta(days=dias_proximidade_viagem),
        )
        .order_by("data_prevista_viagem")
        .values_list("pk", flat=True)
    )
    viagens_ids_dashboard = _selecionar_prioritarios(
        viagens_proximas_ids, viagens_recentes_ids, dashboard_limite
    )
    viagens_dashboard = list(viagens_qs.filter(pk__in=viagens_ids_dashboard))
    ordem_viagens = {pk: idx for idx, pk in enumerate(viagens_ids_dashboard)}
    viagens_dashboard.sort(key=lambda viagem: ordem_viagens.get(viagem.pk, dashboard_limite + 1))

    formularios_candidatos = []
    for viagem in viagens_qs.order_by("-criado_em")[:50]:
        clientes_viagem = viagem.clientes.filter(pk__in=clientes_ids)
        if not clientes_viagem.exists():
            continue

        principais_v = [c for c in clientes_viagem if not c.cliente_principal_id]
        dependentes_v = [c for c in clientes_viagem if c.cliente_principal_id]
        principais_v.sort(key=lambda c: c.pk)
        dependentes_v.sort(key=lambda d: d.pk)
        clientes_ordenados_v = principais_v + dependentes_v

        for cliente in clientes_ordenados_v:
            tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)
            if not tipo_visto_cliente:
                continue
            formulario = _obter_formulario_por_tipo_visto(tipo_visto_cliente, apenas_ativo=True)
            if not formulario:
                continue

            total_perguntas = formulario.perguntas.filter(ativo=True).count()
            total_respostas = RespostaFormulario.objects.filter(
                viagem=viagem, cliente=cliente
            ).count()
            completo = total_respostas == total_perguntas if total_perguntas > 0 else False
            if completo:
                status_slug = "completo"
            elif total_respostas == 0:
                status_slug = "nao-preenchido"
            else:
                status_slug = "parcial"

            formularios_candidatos.append(
                {
                    "chave": (viagem.pk, cliente.pk),
                    "viagem": viagem,
                    "cliente_info": {
                        "cliente": cliente,
                        "tipo_visto": tipo_visto_cliente,
                        "formulario": formulario,
                        "total_perguntas": total_perguntas,
                        "total_respostas": total_respostas,
                        "completo": completo,
                        "status_slug": status_slug,
                    },
                }
            )

    formularios_recentes = sorted(formularios_candidatos, key=lambda item: item["viagem"].criado_em, reverse=True)
    formularios_incompletos_chaves = [
        item["chave"]
        for item in formularios_candidatos
        if item["cliente_info"]["status_slug"] in {"parcial", "nao-preenchido"}
    ]
    formularios_recentes_chaves = [item["chave"] for item in formularios_recentes]
    formularios_chaves_display = _selecionar_prioritarios(
        formularios_incompletos_chaves, formularios_recentes_chaves, dashboard_limite
    )
    formularios_mapa = {item["chave"]: item for item in formularios_candidatos}
    formularios_display = [
        formularios_mapa[chave]
        for chave in formularios_chaves_display
        if chave in formularios_mapa
    ]

    if filtros_painel["formulario"]:
        formularios_display = [
            item for item in formularios_display
            if item["cliente_info"]["status_slug"] == filtros_painel["formulario"]
        ]

    formularios_pendentes = [
        item for item in formularios_display
        if item["cliente_info"]["status_slug"] in {"parcial", "nao-preenchido"}
    ]
    formularios_preenchidos = [
        item for item in formularios_display
        if item["cliente_info"]["status_slug"] == "completo"
    ]
    total_formularios_pendentes = len(formularios_pendentes)
    total_formularios_preenchidos = len(formularios_preenchidos)
    total_formularios_monitorados = total_formularios_pendentes + total_formularios_preenchidos

    if filtros_painel["formulario"]:
        total_formularios = total_formularios_pendentes + total_formularios_preenchidos

    filtro_clientes = [
        {
            "pk": cliente.pk,
            "nome": cliente.nome,
            "principal_pk": cliente.cliente_principal_id,
        }
        for cliente in clientes_base.order_by("nome")
    ]

    seen_vistos = set()
    filtro_vistos = []
    for p in processos_display:
        tv = p.viagem.tipo_visto
        if tv and tv.pk not in seen_vistos:
            seen_vistos.add(tv.pk)
            filtro_vistos.append({"pk": tv.pk, "nome": tv.nome})
    for item in formularios_pendentes + formularios_preenchidos:
        tv = item["cliente_info"]["tipo_visto"]
        if tv and hasattr(tv, "pk") and tv.pk not in seen_vistos:
            seen_vistos.add(tv.pk)
            filtro_vistos.append({"pk": tv.pk, "nome": tv.nome})
    for viagem in viagens_dashboard:
        tv = viagem.tipo_visto
        if tv and tv.pk not in seen_vistos:
            seen_vistos.add(tv.pk)
            filtro_vistos.append({"pk": tv.pk, "nome": tv.nome})
    filtro_vistos.sort(key=lambda x: x["nome"].lower())

    partner_nome = request.session.get("partner_nome", "Parceiro")

    contexto = {
        "partner_nome": partner_nome,
        "clientes_com_status": clientes_com_status,
        "processos": processos_display,
        "viagens_dashboard": viagens_dashboard,
        "total_clientes": total_clientes,
        "total_dependentes": total_dependentes,
        "total_viagens": total_viagens,
        "total_viagens_proximas": total_viagens_proximas,
        "total_viagens_concluidas": total_viagens_concluidas,
        "total_processos": total_processos,
        "total_processos_andamento": total_processos_andamento,
        "total_processos_concluidos": total_processos_concluidos,
        "total_formularios": total_formularios,
        "total_formularios_monitorados": total_formularios_monitorados,
        "total_formularios_pendentes": total_formularios_pendentes,
        "total_formularios_preenchidos": total_formularios_preenchidos,
        "formularios_pendentes": formularios_pendentes,
        "formularios_preenchidos": formularios_preenchidos,
        "filtro_clientes": filtro_clientes,
        "filtro_vistos": filtro_vistos,
        "filtros_painel": filtros_painel,
        "dashboard_limite": dashboard_limite,
        "dias_proximidade_viagem": dias_proximidade_viagem,
    }

    return render(request, "partner_area/dashboard.html", contexto)


def parceiro_visualizar_cliente(request, cliente_id: int):
    from django.shortcuts import get_object_or_404
    from django.db.models import Prefetch

    partner = _get_partner_from_session(request)
    if not partner:
        messages.error(request, "Voce precisa fazer login para acessar a area do parceiro.")
        return redirect("login")

    cliente = get_object_or_404(
        ClienteConsultoria.objects.select_related(
            "assessor_responsavel", "cliente_principal", "parceiro_indicador"
        ),
        pk=cliente_id,
        parceiro_indicador_id=partner.pk,
    )

    cliente_viagens = list(
        ClienteViagem.objects.filter(cliente=cliente)
        .select_related(
            "viagem",
            "viagem__pais_destino",
            "viagem__tipo_visto",
            "viagem__assessor_responsavel",
            "tipo_visto",
        )
        .order_by("-viagem__data_prevista_viagem")
    )

    processos = (
        Processo.objects.filter(cliente=cliente)
        .select_related("viagem", "viagem__pais_destino", "viagem__tipo_visto")
        .prefetch_related(Prefetch("etapas"))
        .order_by("-criado_em")
    )

    tipo_visto_ids = {
        item.tipo_visto_id or item.viagem.tipo_visto_id for item in cliente_viagens
    }
    formularios = FormularioVisto.objects.filter(
        ativo=True,
        tipo_visto_id__in=tipo_visto_ids,
    ).annotate(total_perguntas=Count("perguntas", filter=Q(perguntas__ativo=True)))
    formulario_por_tipo = {formulario.tipo_visto_id: formulario for formulario in formularios}

    respostas_por_viagem = {
        item["viagem_id"]: item["total"]
        for item in RespostaFormulario.objects.filter(
            cliente=cliente,
            viagem_id__in=[item.viagem_id for item in cliente_viagens],
        )
        .values("viagem_id")
        .annotate(total=Count("id"))
    }

    formularios_resumo = []
    for item in cliente_viagens:
        tipo_visto = item.tipo_visto or item.viagem.tipo_visto
        formulario = formulario_por_tipo.get(tipo_visto.pk)
        total_perguntas = formulario.total_perguntas if formulario else 0
        total_respostas = respostas_por_viagem.get(item.viagem_id, 0)

        if total_perguntas == 0:
            status = "Nao aplicavel"
        elif total_respostas == 0:
            status = "Nao preenchido"
        elif total_respostas >= total_perguntas:
            status = "Completo"
        else:
            status = "Parcial"

        formularios_resumo.append(
            {
                "viagem": item.viagem,
                "tipo_visto": tipo_visto,
                "status": status,
                "total_respostas": total_respostas,
                "total_perguntas": total_perguntas,
            }
        )

    partner_nome = request.session.get("partner_nome", "Parceiro")

    contexto = {
        "partner_nome": partner_nome,
        "cliente": cliente,
        "cliente_viagens": cliente_viagens,
        "processos": processos,
        "formularios_resumo": formularios_resumo,
        "hoje": date.today(),
    }
    return render(request, "partner_area/visualizar_cliente.html", contexto)


def parceiro_logout_view(request):
    if "partner_id" in request.session:
        partner_name = request.session.get("partner_nome", "Parceiro")
        messages.success(request, f"Ate logo, {partner_name}!")
        request.session.flush()
    return redirect("login")
