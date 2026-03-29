   
                              
   

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from system.forms import DarBaixaFinanceiroForm
from system.models import Financeiro
from system.views.client_views import obter_consultor_usuario, usuario_pode_gerenciar_todos


def _aplicar_filtros_financeiro(registros, request):
    filtros = {
        "cliente": request.GET.get("cliente", "").strip(),
        "assessor": request.GET.get("assessor", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "data_inicio": request.GET.get("data_inicio", "").strip(),
        "data_fim": request.GET.get("data_fim", "").strip(),
    }

    if filtros["cliente"]:
        registros = registros.filter(
            Q(cliente__nome__icontains=filtros["cliente"]) |
            Q(cliente__email__icontains=filtros["cliente"])
        )
    if filtros["assessor"]:
        registros = registros.filter(
            Q(assessor_responsavel__nome__icontains=filtros["assessor"]) |
            Q(assessor_responsavel__email__icontains=filtros["assessor"])
        )
    if filtros["status"]:
        registros = registros.filter(status=filtros["status"])
    if filtros["data_inicio"]:
        registros = registros.filter(criado_em__date__gte=filtros["data_inicio"])
    if filtros["data_fim"]:
        registros = registros.filter(criado_em__date__lte=filtros["data_fim"])

    return registros, filtros


@login_required
def home_financeiro(request):
                                                        
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

                  
    registros = Financeiro.objects.select_related(
        "viagem",
        "cliente",
                "assessor_responsavel",
    ).order_by("-criado_em")
    registros, filtros = _aplicar_filtros_financeiro(registros, request)

    total_registros = registros.count()
    total_pendente = registros.filter(status="pendente").count()
    total_pago = registros.filter(status="pago").count()
    
                 
    valor_total = registros.aggregate(Sum("valor"))["valor__sum"] or 0
    valor_pago = registros.filter(status="pago").aggregate(Sum("valor"))["valor__sum"] or 0
    valor_pendente = registros.filter(status="pendente").aggregate(Sum("valor"))["valor__sum"] or 0

                       
    ultimos_registros = registros[:10]

    contexto = {
        "total_registros": total_registros,
        "total_pendente": total_pendente,
        "total_pago": total_pago,
        "valor_total": valor_total,
        "valor_pago": valor_pago,
        "valor_pendente": valor_pendente,
        "ultimos_registros": ultimos_registros,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "filtros": filtros,
    }

    return render(request, "financial/home_financeiro.html", contexto)


@login_required
def listar_financeiro(request):
                                                           
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    registros = Financeiro.objects.select_related(
        "viagem",
        "cliente",
                "assessor_responsavel",
    ).order_by("-criado_em")
    registros, filtros = _aplicar_filtros_financeiro(registros, request)

    contexto = {
        "registros": registros,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "filtros": filtros,
    }

    return render(request, "financial/listar_financeiro.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def dar_baixa_financeiro(request, pk: int):
                                                           
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

