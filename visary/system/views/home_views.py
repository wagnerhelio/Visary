from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import render

from system.models import ClienteViagem, FormularioVisto, PaisDestino, Partner, Processo, RespostaFormulario, Viagem
from system.models.financial_models import Financeiro, StatusFinanceiro
from system.views.client_views import (
    _obter_status_financeiro_cliente,
    _obter_status_formulario_cliente,
    listar_clientes,
    obter_consultor_usuario,
    usuario_pode_editar_cliente,
    usuario_pode_gerenciar_todos,
)


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


def _build_period_dates(filters):
    year_start = _parse_positive_int(filters.get("financeiro_ano_inicio"))
    year_end = _parse_positive_int(filters.get("financeiro_ano_fim"))
    month_start = _parse_positive_int(filters.get("financeiro_mes_inicio"))
    month_end = _parse_positive_int(filters.get("financeiro_mes_fim"))

    if month_start and not year_start:
        month_start = None
    if month_end and not year_end:
        month_end = None
    if month_start and month_start > 12:
        month_start = None
    if month_end and month_end > 12:
        month_end = None

    start_date = None
    end_date = None
    if year_start:
        start_date = date(year_start, month_start or 1, 1)
    if year_end:
        end_month = month_end or 12
        if end_month == 12:
            end_date = date(year_end, 12, 31)
        else:
            end_date = date(year_end, end_month + 1, 1) - date.resolution

    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


def _filter_financeiro_by_period(financeiro_qs, filters):
    start_date, end_date = _build_period_dates(filters)
    base_periodo = filters.get("financeiro_base_periodo", "entrada")

    if base_periodo == "baixa":
        financeiro_qs = financeiro_qs.exclude(data_pagamento__isnull=True)
        if start_date:
            financeiro_qs = financeiro_qs.filter(data_pagamento__gte=start_date)
        if end_date:
            financeiro_qs = financeiro_qs.filter(data_pagamento__lte=end_date)
        return financeiro_qs

    if start_date:
        financeiro_qs = financeiro_qs.filter(criado_em__date__gte=start_date)
    if end_date:
        financeiro_qs = financeiro_qs.filter(criado_em__date__lte=end_date)
    return financeiro_qs


def _available_financial_years():
    years = set(Financeiro.objects.values_list("criado_em__year", flat=True))
    years.update(
        Financeiro.objects.exclude(data_pagamento__isnull=True).values_list(
            "data_pagamento__year", flat=True
        )
    )
    return sorted([year for year in years if year], reverse=True)


@login_required
def home(request):
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    is_admin = pode_gerenciar_todos
    dashboard_limite = 10
    dias_proximidade_viagem = 30
    hoje = date.today()

    filtros_painel = {
        "cliente": request.GET.get("cliente", "").strip(),
        "visto": request.GET.get("visto", "").strip(),
        "formulario": request.GET.get("formulario", "").strip(),
        "financeiro": request.GET.get("financeiro", "").strip(),
        "financeiro_base_periodo": request.GET.get("financeiro_base_periodo", "entrada").strip() or "entrada",
        "financeiro_ano_inicio": request.GET.get("financeiro_ano_inicio", "").strip(),
        "financeiro_ano_fim": request.GET.get("financeiro_ano_fim", "").strip(),
        "financeiro_mes_inicio": request.GET.get("financeiro_mes_inicio", "").strip(),
        "financeiro_mes_fim": request.GET.get("financeiro_mes_fim", "").strip(),
    }

    selected_cliente_id = _parse_positive_int(filtros_painel["cliente"])
    selected_visto_id = _parse_positive_int(filtros_painel["visto"])
    selected_financeiro_status = filtros_painel["financeiro"]
    if selected_financeiro_status == "sem-registros":
        selected_financeiro_status = "sem_registros"

    clientes_usuario = listar_clientes(request.user)
    clientes_filtro_base = clientes_usuario

    if selected_cliente_id:
        ids_cliente = {selected_cliente_id}
        viagens_do_cliente = ClienteViagem.objects.filter(
            cliente_id=selected_cliente_id
        ).values_list("viagem_id", flat=True).distinct()
        ids_cliente.update(
            ClienteViagem.objects.filter(viagem_id__in=viagens_do_cliente).values_list("cliente_id", flat=True)
        )
        clientes_usuario = clientes_usuario.filter(pk__in=ids_cliente)

    if selected_visto_id:
        clientes_usuario = clientes_usuario.filter(viagens__tipo_visto_id=selected_visto_id).distinct()

    if is_admin and selected_financeiro_status:
        financeiro_filtrado_clientes = Financeiro.objects.exclude(cliente__isnull=True)
        financeiro_filtrado_clientes = _filter_financeiro_by_period(financeiro_filtrado_clientes, filtros_painel)
        if selected_visto_id:
            financeiro_filtrado_clientes = financeiro_filtrado_clientes.filter(viagem__tipo_visto_id=selected_visto_id)
        if selected_financeiro_status != "sem_registros":
            financeiro_filtrado_clientes = financeiro_filtrado_clientes.filter(status=selected_financeiro_status)
            clientes_usuario = clientes_usuario.filter(pk__in=financeiro_filtrado_clientes.values("cliente_id")).distinct()
        else:
            clientes_usuario = clientes_usuario.exclude(pk__in=financeiro_filtrado_clientes.values("cliente_id")).distinct()

    clientes_ids = list(clientes_usuario.values_list("pk", flat=True))

    clientes_qs = clientes_usuario.select_related(
        "assessor_responsavel", "criado_por", "parceiro_indicador"
    ).prefetch_related("viagens").order_by("-criado_em")

    processos_qs = Processo.objects.filter(
        cliente__pk__in=clientes_ids
    ).select_related(
        "viagem", "viagem__pais_destino", "viagem__tipo_visto", "cliente", "assessor_responsavel"
    ).prefetch_related("etapas").order_by("-criado_em")

    viagens_qs = Viagem.objects.filter(clientes__pk__in=clientes_ids).select_related(
        "pais_destino", "tipo_visto", "assessor_responsavel"
    ).prefetch_related("clientes").distinct().order_by("-data_prevista_viagem")

    if selected_visto_id:
        processos_qs = processos_qs.filter(viagem__tipo_visto_id=selected_visto_id)
        viagens_qs = viagens_qs.filter(tipo_visto_id=selected_visto_id)

    total_clientes = clientes_usuario.count()
    total_dependentes = ClienteViagem.objects.filter(
        cliente_id__in=clientes_ids, papel="dependente"
    ).values("cliente_id").distinct().count()
    total_viagens = viagens_qs.count()
    total_viagens_proximas = viagens_qs.filter(
        data_prevista_viagem__gte=hoje,
        data_prevista_viagem__lte=hoje + timedelta(days=dias_proximidade_viagem),
    ).count()
    total_viagens_concluidas = viagens_qs.filter(data_prevista_retorno__lt=hoje).count()
    total_processos = processos_qs.count()
    total_processos_andamento = processos_qs.filter(
        Q(etapas__concluida=False) | Q(etapas__isnull=True)
    ).distinct().count()
    total_processos_concluidos = max(total_processos - total_processos_andamento, 0)
    total_formularios = RespostaFormulario.objects.filter(cliente__pk__in=clientes_ids).values(
        "viagem", "cliente"
    ).distinct().count()

    financeiro_qs_kpi = Financeiro.objects.all()
    if is_admin:
        total_partners = Partner.objects.count()
        total_paises = PaisDestino.objects.count()

        if selected_cliente_id:
            ids_kpi_cliente = {selected_cliente_id}
            viagens_kpi = ClienteViagem.objects.filter(
                cliente_id=selected_cliente_id
            ).values_list("viagem_id", flat=True).distinct()
            ids_kpi_cliente.update(
                ClienteViagem.objects.filter(viagem_id__in=viagens_kpi).values_list("cliente_id", flat=True)
            )
            financeiro_qs_kpi = financeiro_qs_kpi.filter(cliente_id__in=ids_kpi_cliente)

        if selected_visto_id:
            financeiro_qs_kpi = financeiro_qs_kpi.filter(viagem__tipo_visto_id=selected_visto_id)

        financeiro_qs_kpi = _filter_financeiro_by_period(financeiro_qs_kpi, filtros_painel)

        if selected_financeiro_status and selected_financeiro_status != "sem_registros":
            financeiro_qs_kpi = financeiro_qs_kpi.filter(status=selected_financeiro_status)
        elif selected_financeiro_status == "sem_registros":
            financeiro_qs_kpi = financeiro_qs_kpi.none()

        valor_total = financeiro_qs_kpi.aggregate(Sum("valor"))["valor__sum"] or 0
        valor_pago = financeiro_qs_kpi.filter(status=StatusFinanceiro.PAGO).aggregate(Sum("valor"))["valor__sum"] or 0
        valor_pendente = financeiro_qs_kpi.filter(status=StatusFinanceiro.PENDENTE).aggregate(Sum("valor"))["valor__sum"] or 0
    else:
        total_partners = 0
        total_paises = 0
        valor_total = 0
        valor_pago = 0
        valor_pendente = 0

    def build_cliente_item(cliente):
        status_financeiro = _obter_status_financeiro_cliente(cliente)
        status_formulario = _obter_status_formulario_cliente(cliente)
        return {
            "cliente": cliente,
            "status_financeiro": status_financeiro,
            "status_formulario": status_formulario["status"],
            "total_perguntas": status_formulario["total_perguntas"],
            "total_respostas": status_formulario["total_respostas"],
            "pode_editar": usuario_pode_editar_cliente(request.user, consultor, cliente),
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
        processos_nao_finalizados_ids,
        processos_recentes_ids,
        dashboard_limite,
    )
    processos_display = list(processos_qs.filter(pk__in=processos_ids_display))
    ordem_processos = {pk: idx for idx, pk in enumerate(processos_ids_display)}
    processos_display.sort(key=lambda processo: ordem_processos.get(processo.pk, dashboard_limite + 1))

    viagens_recentes_ids = list(
        viagens_qs.order_by("-criado_em").values_list("pk", flat=True)[:dashboard_limite]
    )
    viagens_proximas_ids = list(
        viagens_qs.filter(
            data_prevista_viagem__gte=hoje,
            data_prevista_viagem__lte=hoje + timedelta(days=dias_proximidade_viagem),
        )
        .order_by("data_prevista_viagem")
        .values_list("pk", flat=True)
    )
    viagens_ids_dashboard = _selecionar_prioritarios(
        viagens_proximas_ids,
        viagens_recentes_ids,
        dashboard_limite,
    )
    viagens_dashboard = list(viagens_qs.filter(pk__in=viagens_ids_dashboard))
    ordem_viagens = {pk: idx for idx, pk in enumerate(viagens_ids_dashboard)}
    viagens_dashboard.sort(key=lambda viagem: ordem_viagens.get(viagem.pk, dashboard_limite + 1))

    from contextlib import suppress

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
                    tipo_visto_id=tipo_visto.pk, ativo=True
                )
            return FormularioVisto.objects.select_related('tipo_visto').get(
                tipo_visto_id=tipo_visto.pk
            )
        except FormularioVisto.DoesNotExist:
            return None

    formularios_candidatos = []

    for viagem in viagens_qs.order_by("-criado_em")[:50]:
        clientes_viagem = viagem.clientes.filter(pk__in=clientes_ids)
        if not clientes_viagem.exists():
            continue

        cv_map = {
            cv.cliente_id: cv.papel
            for cv in ClienteViagem.objects.filter(viagem=viagem)
        }
        clientes_ordenados_v = sorted(
            clientes_viagem,
            key=lambda c: (0 if cv_map.get(c.pk) == "principal" else 1, c.pk),
        )

        clientes_info = []
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

            info = {
                "cliente": cliente,
                "tipo_visto": tipo_visto_cliente,
                "formulario": formulario,
                "total_perguntas": total_perguntas,
                "total_respostas": total_respostas,
                "completo": completo,
                "status_slug": status_slug,
            }

            formularios_candidatos.append(
                {
                    "chave": (viagem.pk, cliente.pk),
                    "viagem": viagem,
                    "cliente_info": info,
                }
            )

    formularios_recentes = sorted(
        formularios_candidatos,
        key=lambda item: item["viagem"].criado_em,
        reverse=True,
    )
    formularios_incompletos_chaves = [
        item["chave"]
        for item in formularios_candidatos
        if item["cliente_info"]["status_slug"] in {"parcial", "nao-preenchido"}
    ]
    formularios_recentes_chaves = [item["chave"] for item in formularios_recentes]
    formularios_chaves_display = _selecionar_prioritarios(
        formularios_incompletos_chaves,
        formularios_recentes_chaves,
        dashboard_limite,
    )
    formularios_mapa = {item["chave"]: item for item in formularios_candidatos}
    formularios_display = [
        formularios_mapa[chave]
        for chave in formularios_chaves_display
        if chave in formularios_mapa
    ]

    if filtros_painel["formulario"]:
        formularios_display = [
            item
            for item in formularios_display
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
            "nome": cliente.nome_completo,
            "principal_pk": None,
        }
        for cliente in clientes_usuario.order_by("nome")
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

    anos_financeiro = _available_financial_years() if is_admin else []
    meses_financeiro = [
        (1, "Janeiro"),
        (2, "Fevereiro"),
        (3, "Marco"),
        (4, "Abril"),
        (5, "Maio"),
        (6, "Junho"),
        (7, "Julho"),
        (8, "Agosto"),
        (9, "Setembro"),
        (10, "Outubro"),
        (11, "Novembro"),
        (12, "Dezembro"),
    ]

    contexto = {
        "is_admin": is_admin,
        "consultor": consultor,
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
        "total_paises": total_paises,
        "total_partners": total_partners,
        "total_formularios": total_formularios,
        "total_formularios_monitorados": total_formularios_monitorados,
        "total_formularios_pendentes": total_formularios_pendentes,
        "total_formularios_preenchidos": total_formularios_preenchidos,
        "formularios_pendentes": formularios_pendentes,
        "formularios_preenchidos": formularios_preenchidos,
        "valor_total": valor_total,
        "valor_pago": valor_pago,
        "valor_pendente": valor_pendente,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "filtro_clientes": filtro_clientes,
        "filtro_vistos": filtro_vistos,
        "filtros_painel": filtros_painel,
        "anos_financeiro": anos_financeiro,
        "meses_financeiro": meses_financeiro,
        "dashboard_limite": dashboard_limite,
        "dias_proximidade_viagem": dias_proximidade_viagem,
    }

    return render(request, "home/home.html", contexto)
