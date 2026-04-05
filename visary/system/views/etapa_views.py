from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from system.forms import (
    ClientStepFieldInlineForm,
    ConsultancyClientForm,
    ClientRegistrationStepForm,
)
from system.models import ClientStepField, ClientRegistrationStep
from system.views.client_views import get_user_consultant, user_can_manage_all


@login_required
def list_registration_steps(request):
    consultant = get_user_consultant(request.user)
    can_manage = user_can_manage_all(request.user, consultant)

    if not can_manage:
        raise PermissionDenied("Você não tem permissão para gerenciar etapas.")

    steps_queryset = ClientRegistrationStep.objects.all().prefetch_related(
        models.Prefetch(
            "fields",
            queryset=ClientStepField.objects.all().order_by("order", "field_name")
        )
    ).order_by("order", "name")

    steps = list(steps_queryset)

    context = {
        "stages": steps,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "client/etapas/list_registration_steps.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def create_registration_step(request):
    consultant = get_user_consultant(request.user)
    can_manage = user_can_manage_all(request.user, consultant)

    if not can_manage:
        raise PermissionDenied("Você não tem permissão para criar etapas.")

    if request.method == "POST":
        form = ClientRegistrationStepForm(data=request.POST)
        if form.is_valid():
            step = form.save()
            messages.success(request, f"Etapa '{step.name}' criada com sucesso.")
            return redirect("system:edit_registration_step", pk=step.pk)

        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"Campo '{form.fields[field].label}': {error}")
    else:
        form = ClientRegistrationStepForm()

    context = {
        "form": form,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "client/etapas/create_registration_step.html", context)


def _get_available_fields(already_linked_fields: set) -> list:
    temp_form = ConsultancyClientForm()
    model_fields = [
        "assigned_advisor",
        "first_name",
        "last_name",
        "cpf",
        "birth_date",
        "nationality",
        "phone",
        "secondary_phone",
        "email",
        "password",
        "confirm_password",
        "referring_partner",
        "zip_code",
        "street",
        "street_number",
        "complement",
        "district",
        "city",
        "state",
        "notes",
    ]

    return [
        {
            "name": field_name,
            "label": temp_form.fields[field_name].label or field_name,
            "already_linked": field_name in already_linked_fields,
        }
        for field_name in model_fields
        if field_name in temp_form.fields
    ]


def _add_step_field(request, step, step_fields, available_fields) -> Optional[HttpResponseRedirect]:
    field_name = request.POST.get("field_name")
    available_names = {c["name"] for c in available_fields}

    if not field_name or field_name not in available_names:
        messages.error(request, "Campo inválido.")
        return None

    if ClientStepField.objects.filter(step=step, field_name=field_name).exists():
        messages.error(request, f"Campo '{field_name}' já está vinculado a esta etapa.")
        return None

    max_order = step_fields.aggregate(models.Max("order"))["order__max"] or 0
    ClientStepField.objects.create(
        step=step,
        field_name=field_name,
        order=max_order + 1,
        is_required=False,
        is_active=True,
    )
    messages.success(request, f"Campo '{field_name}' adicionado à etapa.")
    return redirect("system:edit_registration_step", pk=step.pk)


def _process_step_update(request, form, step) -> Optional[HttpResponseRedirect]:
    if not form.is_valid():
        for field, errors in form.errors.items():
            field_label = form.fields[field].label if field in form.fields else field
            for error in errors:
                messages.error(request, f"Campo '{field_label}': {error}")
        return None

    form.save()
    messages.success(request, f"Etapa '{step.name}' atualizada com sucesso.")
    return redirect("system:edit_registration_step", pk=step.pk)


@require_http_methods(["GET", "POST"])
def edit_registration_step(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage = user_can_manage_all(request.user, consultant)

    if not can_manage:
        raise PermissionDenied("Você não tem permissão para editar etapas.")

    step = get_object_or_404(ClientRegistrationStep, pk=pk)
    step_fields = ClientStepField.objects.filter(step=step).order_by("order", "field_name")
    already_linked_fields = {f.field_name for f in step_fields}
    available_fields = _get_available_fields(already_linked_fields)

    if request.method == "POST":
        if "add_field" in request.POST:
            if redirect_response := _add_step_field(request, step, step_fields, available_fields):
                return redirect_response

        form = ClientRegistrationStepForm(data=request.POST, instance=step)
        if redirect_response := _process_step_update(request, form, step):
            return redirect_response
    else:
        form = ClientRegistrationStepForm(instance=step)

    step_fields = ClientStepField.objects.filter(step=step).order_by("order", "field_name")

    context = {
        "form": form,
        "stage": step,
        "fields_list": step_fields,
        "available_fields": available_fields,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "client/etapas/edit_registration_step.html", context)


@login_required
@require_http_methods(["POST"])
def delete_registration_step(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage = user_can_manage_all(request.user, consultant)

    if not can_manage:
        raise PermissionDenied("Você não tem permissão para excluir etapas.")

    step = get_object_or_404(ClientRegistrationStep, pk=pk)
    step_name = step.name
    step.delete()
    messages.success(request, f"Etapa '{step_name}' excluída com sucesso.")
    return redirect("system:list_registration_steps")


@login_required
@require_http_methods(["GET", "POST"])
def create_step_field(request, step_id: int):
    consultant = get_user_consultant(request.user)
    can_manage = user_can_manage_all(request.user, consultant)

    if not can_manage:
        raise PermissionDenied("Você não tem permissão para criar campos.")

    step = get_object_or_404(ClientRegistrationStep, pk=step_id)

    if request.method == "POST":
        form = ClientStepFieldInlineForm(data=request.POST)
        if form.is_valid():
            field_obj = form.save(commit=False)
            field_obj.step = step
            field_obj.save()
            messages.success(request, f"Campo '{field_obj.field_name}' adicionado à etapa '{step.name}'.")
            return redirect("system:list_registration_steps")

        for field, errors in form.errors.items():
            for error in errors:
                field_label = form.fields[field].label if field in form.fields else field
                messages.error(request, f"Campo '{field_label}': {error}")
    else:
        form = ClientStepFieldInlineForm()

    context = {
        "form": form,
        "stage": step,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "client/etapas/create_step_field.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def edit_step_field(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage = user_can_manage_all(request.user, consultant)

    if not can_manage:
        raise PermissionDenied("Você não tem permissão para editar campos.")

    field_obj = get_object_or_404(ClientStepField, pk=pk)

    if request.method == "POST":
        form = ClientStepFieldInlineForm(data=request.POST, instance=field_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Campo '{field_obj.field_name}' atualizado com sucesso.")
            return redirect("system:list_registration_steps")

        for field, errors in form.errors.items():
            for error in errors:
                field_label = form.fields[field].label if field in form.fields else field
                messages.error(request, f"Campo '{field_label}': {error}")
    else:
        form = ClientStepFieldInlineForm(instance=field_obj)

    context = {
        "form": form,
        "field_obj": field_obj,
        "stage": field_obj.step,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "client/etapas/edit_step_field.html", context)


@login_required
@require_http_methods(["POST"])
def delete_step_field(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage = user_can_manage_all(request.user, consultant)

    if not can_manage:
        raise PermissionDenied("Você não tem permissão para excluir campos.")

    field_obj = get_object_or_404(ClientStepField, pk=pk)
    field_name = field_obj.field_name
    field_obj.delete()
    messages.success(request, f"Campo '{field_name}' excluído com sucesso.")
    return redirect("system:list_registration_steps")
