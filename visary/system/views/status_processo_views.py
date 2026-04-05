from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from system.forms import ProcessStatusForm
from system.models import ProcessStatus
from system.views.client_views import get_user_consultant, user_can_manage_all


@login_required
def list_process_status(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied("Você não tem permissão para gerenciar status de processos.")

    status_list = ProcessStatus.objects.select_related(
        "visa_type", "visa_type__destination_country"
    ).order_by("order", "name")

    context = {
        "status_list": status_list,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
    }

    return render(request, "process/list_process_status.html", context)


@login_required
def create_process_status(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied("Você não tem permissão para criar status de processos.")

    if request.method == "POST":
        form = ProcessStatusForm(data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Status cadastrado com sucesso.")
            return redirect("system:list_process_status")
        messages.error(request, "Não foi possível cadastrar o status. Verifique os campos.")
    else:
        form = ProcessStatusForm()

    context = {
        "form": form,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "process/create_process_status.html", context)


@login_required
def edit_process_status(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied("Você não tem permissão para editar status de processos.")

    status = get_object_or_404(ProcessStatus, pk=pk)

    if request.method == "POST":
        form = ProcessStatusForm(data=request.POST, instance=status)
        if form.is_valid():
            form.save()
            messages.success(request, "Status atualizado com sucesso.")
            return redirect("system:list_process_status")
        messages.error(request, "Não foi possível atualizar o status. Verifique os campos.")
    else:
        form = ProcessStatusForm(instance=status)

    context = {
        "form": form,
        "status": status,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "process/edit_process_status.html", context)


@login_required
@require_http_methods(["POST"])
def delete_process_status(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied("Você não tem permissão para excluir status de processos.")

    status = get_object_or_404(ProcessStatus, pk=pk)

    if status.stages.exists():
        messages.error(
            request,
            f"Não é possível excluir o status '{status.name}' pois existem processos vinculados a ele.",
        )
        return redirect("system:list_process_status")

    status_name = status.name
    status.delete()

    messages.success(request, f"Status '{status_name}' excluído com sucesso.")
    return redirect("system:list_process_status")
