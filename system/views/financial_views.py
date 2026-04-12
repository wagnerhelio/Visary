from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from system.forms import FinancialSettlementForm
from system.models import ConsultancyClient, FinancialRecord, FinancialStatus
from system.views.client_views import get_user_consultant, user_can_manage_all


def _apply_financial_filters(records, request):
    filters = {
        "client": request.GET.get("client", "").strip(),
        "advisor": request.GET.get("advisor", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "date_start": request.GET.get("date_start", "").strip(),
        "date_end": request.GET.get("date_end", "").strip(),
    }

    if filters["client"]:
        records = records.filter(
            Q(client__first_name__icontains=filters["client"]) |
            Q(client__email__icontains=filters["client"])
        )
    if filters["advisor"]:
        records = records.filter(
            Q(assigned_advisor__name__icontains=filters["advisor"]) |
            Q(assigned_advisor__email__icontains=filters["advisor"])
        )
    if filters["status"]:
        records = records.filter(status=filters["status"])
    if filters["date_start"]:
        records = records.filter(created_at__date__gte=filters["date_start"])
    if filters["date_end"]:
        records = records.filter(created_at__date__lte=filters["date_end"])

    return records, filters


@login_required
def home_financial(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    records = FinancialRecord.objects.select_related(
        "trip",
        "client",
        "assigned_advisor",
    ).order_by("-created_at")
    records, filters = _apply_financial_filters(records, request)

    total_records = records.count()
    total_pending = records.filter(status=FinancialStatus.PENDING).count()
    total_paid = records.filter(status=FinancialStatus.PAID).count()

    total_amount = records.aggregate(Sum("amount"))["amount__sum"] or 0
    paid_amount = records.filter(status=FinancialStatus.PAID).aggregate(Sum("amount"))["amount__sum"] or 0
    pending_amount = records.filter(status=FinancialStatus.PENDING).aggregate(Sum("amount"))["amount__sum"] or 0

    latest_records = records[:10]

    clients = ConsultancyClient.objects.filter(
        primary_client__isnull=True
    ).order_by("first_name")

    context = {
        "total_records": total_records,
        "total_pending": total_pending,
        "total_paid": total_paid,
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "pending_amount": pending_amount,
        "latest_records": latest_records,
        "user_profile": consultant.profile.name if consultant else None,
        "filters_dict": filters,
        "clients": clients,
    }

    return render(request, "financial/home_financial.html", context)


@login_required
def list_financial(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    records = FinancialRecord.objects.select_related(
        "trip",
        "client",
        "assigned_advisor",
    ).order_by("-created_at")
    records, filters = _apply_financial_filters(records, request)

    clients = ConsultancyClient.objects.filter(
        primary_client__isnull=True
    ).order_by("first_name")

    context = {
        "records": records,
        "user_profile": consultant.profile.name if consultant else None,
        "filters_dict": filters,
        "clients": clients,
    }

    return render(request, "financial/list_financial.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def settle_financial(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    record = get_object_or_404(
        FinancialRecord.objects.select_related("trip", "client", "client__primary_client", "assigned_advisor"),
        pk=pk
    )

    if request.method == "POST":
        form = FinancialSettlementForm(data=request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, "Baixa no pagamento registrada com sucesso.")
            return redirect("system:list_financial")
        messages.error(request, "Não foi possível registrar a baixa. Verifique os campos.")
    else:
        form = FinancialSettlementForm(instance=record)

    context = {
        "form": form,
        "record": record,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "financial/settle_financial.html", context)
