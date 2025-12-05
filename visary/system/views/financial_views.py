"""
Views relacionadas a finanças.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from consultancy.forms import DarBaixaFinanceiroForm
from consultancy.models import Financeiro
from system.views.client_views import obter_consultor_usuario, usuario_pode_gerenciar_todos


@login_required
def home_financeiro(request):
    """Página inicial de financeiro com estatísticas."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    # Estatísticas
    total_registros = Financeiro.objects.count()
    total_pendente = Financeiro.objects.filter(status="pendente").count()
    total_pago = Financeiro.objects.filter(status="pago").count()
    
    # Valor total
    valor_total = Financeiro.objects.aggregate(Sum("valor"))["valor__sum"] or 0
    valor_pago = Financeiro.objects.filter(status="pago").aggregate(Sum("valor"))["valor__sum"] or 0
    valor_pendente = Financeiro.objects.filter(status="pendente").aggregate(Sum("valor"))["valor__sum"] or 0

    # Últimos registros
    ultimos_registros = Financeiro.objects.select_related(
        "viagem",
        "cliente",
        "cliente__cliente_principal",
        "assessor_responsavel",
    ).order_by("-criado_em")[:10]

    contexto = {
        "total_registros": total_registros,
        "total_pendente": total_pendente,
        "total_pago": total_pago,
        "valor_total": valor_total,
        "valor_pago": valor_pago,
        "valor_pendente": valor_pendente,
        "ultimos_registros": ultimos_registros,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "financial/home_financeiro.html", contexto)


@login_required
def listar_financeiro(request):
    """Lista todos os registros financeiros com filtros."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    registros = Financeiro.objects.select_related(
        "viagem",
        "cliente",
        "cliente__cliente_principal",
        "assessor_responsavel",
    ).order_by("-criado_em")

    # Filtros
    cliente_filter = request.GET.get("cliente", "")
    assessor_filter = request.GET.get("assessor", "")
    status_filter = request.GET.get("status", "")
    data_inicio = request.GET.get("data_inicio", "")
    data_fim = request.GET.get("data_fim", "")

    if cliente_filter:
        registros = registros.filter(
            Q(cliente__nome__icontains=cliente_filter) |
            Q(cliente__email__icontains=cliente_filter)
        )

    if assessor_filter:
        registros = registros.filter(
            Q(assessor_responsavel__nome__icontains=assessor_filter) |
            Q(assessor_responsavel__email__icontains=assessor_filter)
        )

    if status_filter:
        registros = registros.filter(status=status_filter)

    if data_inicio:
        registros = registros.filter(criado_em__date__gte=data_inicio)

    if data_fim:
        registros = registros.filter(criado_em__date__lte=data_fim)

    contexto = {
        "registros": registros,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "filtros": {
            "cliente": cliente_filter,
            "assessor": assessor_filter,
            "status": status_filter,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
        },
    }

    return render(request, "financial/listar_financeiro.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def dar_baixa_financeiro(request, pk: int):
    """Dar baixa no pagamento de um registro financeiro."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    registro = get_object_or_404(
        Financeiro.objects.select_related("viagem", "cliente", "cliente__cliente_principal", "assessor_responsavel"),
        pk=pk
    )

    if request.method == "POST":
        form = DarBaixaFinanceiroForm(data=request.POST, instance=registro)
        if form.is_valid():
            form.save()
            messages.success(request, "Baixa no pagamento registrada com sucesso.")
            return redirect("system:listar_financeiro")
        messages.error(request, "Não foi possível registrar a baixa. Verifique os campos.")
    else:
        form = DarBaixaFinanceiroForm(instance=registro)

    contexto = {
        "form": form,
        "registro": registro,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "financial/dar_baixa_financeiro.html", contexto)

