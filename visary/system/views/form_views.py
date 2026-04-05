from contextlib import suppress

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from system.forms import (
    VisaFormStageForm,
    VisaFormForm,
    SelectOptionForm,
    FormQuestionForm,
)
from system.models import VisaFormStage, VisaForm, SelectOption, DestinationCountry, FormQuestion, Trip
from system.views.client_views import list_clients, get_user_consultant, user_can_manage_all


def _read_form_filters(request):
    return {
        "client": request.GET.get("client", "").strip(),
        "country": request.GET.get("country", "").strip(),
        "visa_type": request.GET.get("visa_type", "").strip(),
        "status": request.GET.get("status", "").strip(),
    }


def _client_form_filter_matches(client_info, trip, filters):
    if filters["client"]:
        full_name = client_info["client"].full_name.lower()
        term = filters["client"].lower()
        if term not in full_name:
            return False
    if filters["country"] and str(trip.destination_country_id) != filters["country"]:
        return False
    if filters["visa_type"] and str(client_info["visa_type"].pk) != filters["visa_type"]:
        return False
    if filters["status"] == "pendente" and client_info["complete"]:
        return False
    if filters["status"] == "complete" and not client_info["complete"]:
        return False
    return True


def _sort_clients_by_family_group(clients, trip=None):
    if trip:
        from system.models import TripClient
        cv_map = {
            cv.client_id: cv.role
            for cv in TripClient.objects.filter(trip=trip)
        }
        return sorted(
            clients,
            key=lambda c: (0 if cv_map.get(c.pk) == "primary" else 1, c.first_name),
        )
    return sorted(clients, key=lambda c: (c.first_name,))


def _apply_form_response_filters(form_responses, filters):
    filtered = []
    for item in form_responses:
        filtered_clients = [
            client_info
            for client_info in item["clients"]
            if _client_form_filter_matches(client_info, item["trip"], filters)
        ]
        if filtered_clients:
            new_item = dict(item)
            new_item["clients"] = filtered_clients
            filtered.append(new_item)
    return filtered


def _form_filter_options(form_responses):
    clients_map = {}
    countries_map = {}
    types_map = {}
    for item in form_responses:
        trip = item["trip"]
        countries_map.setdefault(trip.destination_country.pk, trip.destination_country)
        for client_info in item["clients"]:
            client = client_info["client"]
            visa_type = client_info["visa_type"]
            clients_map.setdefault(client.pk, client)
            types_map.setdefault(visa_type.pk, visa_type)
    return {
        "clients_filter": sorted(clients_map.values(), key=lambda c: c.full_name.lower()),
        "countries_filter": sorted(countries_map.values(), key=lambda p: p.name.lower()),
        "visa_types_filter": sorted(types_map.values(), key=lambda t: t.name.lower()),
    }


def _apply_form_type_filters(visa_forms, request):
    filters = {
        "search": request.GET.get("search", "").strip(),
        "country": request.GET.get("country", "").strip(),
        "status": request.GET.get("status", "").strip(),
    }

    if filters["search"]:
        visa_forms = visa_forms.filter(visa_type__name__icontains=filters["search"])
    if filters["country"]:
        visa_forms = visa_forms.filter(visa_type__destination_country_id=filters["country"])
    if filters["status"] == "ativo":
        visa_forms = visa_forms.filter(is_active=True)
    elif filters["status"] == "inativo":
        visa_forms = visa_forms.filter(is_active=False)

    return visa_forms, filters


def _get_client_visa_type(trip, client):
    from system.models import TripClient
    with suppress(TripClient.DoesNotExist):
        trip_client = TripClient.objects.select_related('visa_type__form').get(
            trip=trip, client=client
        )
        if trip_client.visa_type:
            return trip_client.visa_type
    return trip.visa_type


def _get_visa_form_by_type(visa_type, active_only=True):
    if not visa_type or not hasattr(visa_type, 'pk') or not visa_type.pk:
        return None
    try:
        if active_only:
            return VisaForm.objects.select_related('visa_type').get(
                visa_type_id=visa_type.pk,
                is_active=True
            )
        return VisaForm.objects.select_related('visa_type').get(
            visa_type_id=visa_type.pk
        )
    except VisaForm.DoesNotExist:
        return None


def _build_clients_by_form_data(trip, clients_ordered, form_responses, counter=None):
    from system.models import FormAnswer
    clients_by_form = {}

    for client in clients_ordered:
        client_visa_type = _get_client_visa_type(trip, client)
        if not client_visa_type:
            continue

        visa_form = _get_visa_form_by_type(client_visa_type, active_only=True)
        if not visa_form:
            continue

        key = f"{trip.pk}_{visa_form.pk}"
        if key not in clients_by_form:
            clients_by_form[key] = {
                "trip": trip,
                "visa_form_obj": visa_form,
                "clients": [],
            }

        total_questions = visa_form.questions.filter(is_active=True).count()
        total_answers = FormAnswer.objects.filter(
            trip=trip,
            client=client
        ).count()

        clients_by_form[key]["clients"].append({
            "client": client,
            "visa_type": client_visa_type,
            "total_questions": total_questions,
            "total_answers": total_answers,
            "complete": total_answers == total_questions if total_questions > 0 else False,
        })
        if counter is not None:
            counter[0] += 1

    form_responses.extend(clients_by_form.values())


@login_required
def home_forms(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    user_clients = list_clients(request.user)
    client_ids = list(user_clients.values_list("pk", flat=True))

    trips = Trip.objects.filter(
        clients__pk__in=client_ids
    ).select_related(
        "destination_country",
        "visa_type",
        "visa_type__form",
    ).prefetch_related("clients").distinct().order_by("-planned_departure_date")

    form_responses = []
    total_clients_with_form = [0]

    for trip in trips[:10]:
        trip_clients = trip.clients.filter(pk__in=client_ids)
        if not trip_clients.exists():
            continue
        ordered_clients = _sort_clients_by_family_group(trip_clients)
        _build_clients_by_form_data(trip, ordered_clients, form_responses, counter=total_clients_with_form)

    pending_forms = []
    completed_forms = []
    for item in form_responses:
        for cli in item["clients"]:
            entry = {
                "trip": item["trip"],
                "client_info": {
                    "client": cli["client"],
                    "visa_type": cli["visa_type"],
                    "total_questions": cli["total_questions"],
                    "total_answers": cli["total_answers"],
                    "complete": cli["complete"],
                },
            }
            if cli["complete"]:
                completed_forms.append(entry)
            else:
                pending_forms.append(entry)

    applied_filters = _read_form_filters(request)
    form_responses = _apply_form_response_filters(form_responses, applied_filters)
    pending_forms = [
        item
        for item in pending_forms
        if _client_form_filter_matches(item["client_info"], item["trip"], applied_filters)
    ]
    completed_forms = [
        item
        for item in completed_forms
        if _client_form_filter_matches(item["client_info"], item["trip"], applied_filters)
    ]
    filter_options = _form_filter_options(form_responses)

    total_forms_kpi = len(pending_forms) + len(completed_forms)
    total_pending_kpi = len(pending_forms)
    total_completed_kpi = len(completed_forms)

    context = {
        "total_forms": total_clients_with_form[0],
        "form_responses": form_responses,
        "pending_forms": pending_forms,
        "completed_forms": completed_forms,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "applied_filters_dict": applied_filters,
        **filter_options,
        "total_forms_kpi": total_forms_kpi,
        "total_pending_kpi": total_pending_kpi,
        "total_completed_kpi": total_completed_kpi,
    }

    return render(request, "forms/home_forms.html", context)


@login_required
def list_forms(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    trips = Trip.objects.select_related(
        "destination_country",
        "visa_type",
        "visa_type__form",
    ).prefetch_related("clients").distinct().order_by("-planned_departure_date")

    form_responses = []

    for trip in trips:
        trip_clients = trip.clients.all()
        if not trip_clients.exists():
            continue
        ordered_clients = _sort_clients_by_family_group(trip_clients)
        _build_clients_by_form_data(trip, ordered_clients, form_responses)

    applied_filters = _read_form_filters(request)
    form_responses = _apply_form_response_filters(form_responses, applied_filters)
    filter_options = _form_filter_options(form_responses)
    total_forms_kpi = sum(len(item["clients"]) for item in form_responses)
    total_pending_kpi = sum(
        1
        for item in form_responses
        for client in item["clients"]
        if not client["complete"]
    )
    total_completed_kpi = total_forms_kpi - total_pending_kpi

    context = {
        "form_responses": form_responses,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "applied_filters_dict": applied_filters,
        **filter_options,
        "total_forms_kpi": total_forms_kpi,
        "total_pending_kpi": total_pending_kpi,
        "total_completed_kpi": total_completed_kpi,
    }

    return render(request, "forms/list_forms.html", context)


@login_required
def home_form_types(request):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied
    can_manage_all = True

    visa_forms = VisaForm.objects.select_related("visa_type", "visa_type__destination_country").all().order_by(
        "visa_type__name"
    )
    visa_forms, applied_filters = _apply_form_type_filters(visa_forms, request)
    total_forms = visa_forms.count()

    context = {
        "visa_forms": visa_forms[:10],
        "total_forms": total_forms,
        "user_profile": consultant.profile.name if consultant else "Administrador",
        "can_manage_all": can_manage_all,
        "applied_filters_dict": applied_filters,
        "countries": DestinationCountry.objects.filter(is_active=True).order_by("name"),
    }

    return render(request, "forms/home_form_types.html", context)


@login_required
def create_form(request):
    consultant = get_user_consultant(request.user)

    if request.method == "POST":
        form = VisaFormForm(data=request.POST)
        if form.is_valid():
            visa_form = form.save()
            messages.success(
                request,
                f"Formulário para {visa_form.visa_type.name} criado com sucesso.",
            )
            return redirect("system:edit_form", pk=visa_form.pk)
        messages.error(request, "Não foi possível criar o formulário. Verifique os campos.")
    else:
        form = VisaFormForm()

    context = {
        "form": form,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "forms/create_form.html", context)


@login_required
def list_form_types(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    visa_forms = (
        VisaForm.objects.select_related("visa_type", "visa_type__destination_country")
        .all()
        .order_by("visa_type__name")
    )
    visa_forms, applied_filters = _apply_form_type_filters(visa_forms, request)

    context = {
        "visa_forms": visa_forms,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "applied_filters_dict": applied_filters,
        "countries": DestinationCountry.objects.filter(is_active=True).order_by("name"),
    }

    return render(request, "forms/list_form_types.html", context)


@login_required
def edit_form(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    visa_form = get_object_or_404(
        VisaForm.objects.select_related("visa_type"), pk=pk
    )
    questions = (
        visa_form.questions.all()
        .prefetch_related("options")
        .order_by("order", "question")
    )
    stages = list(
        VisaFormStage.objects.filter(form=visa_form)
        .prefetch_related("questions")
        .order_by("order")
    )
    orphan_questions = list(
        visa_form.questions.filter(is_active=True, stage__isnull=True).order_by("order")
    )

    if request.method == "POST":
        form = VisaFormForm(data=request.POST, instance=visa_form)
        if form.is_valid():
            form.save()
            messages.success(request, "Formulário atualizado com sucesso.")
            return redirect("system:edit_form", pk=visa_form.pk)
        messages.error(request, "Não foi possível atualizar o formulário.")
    else:
        form = VisaFormForm(instance=visa_form)

    context = {
        "form": form,
        "visa_form_obj": visa_form,
        "questions": questions,
        "stages": stages,
        "orphan_questions": orphan_questions,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "forms/edit_form.html", context)


@login_required
def create_form_stage(request, form_id: int):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    visa_form = get_object_or_404(VisaForm, pk=form_id)
    if request.method == "POST":
        form = VisaFormStageForm(data=request.POST, visa_form=visa_form)
        if form.is_valid():
            stage = form.save(commit=False)
            stage.form = visa_form
            stage.save()
            messages.success(request, "Etapa do formulário criada com sucesso.")
            return redirect("system:edit_form", pk=visa_form.pk)
        messages.error(request, "Não foi possível criar a etapa do formulário.")
    else:
        form = VisaFormStageForm(visa_form=visa_form)

    return render(
        request,
        "forms/create_form_stage.html",
        {"form": form, "visa_form_obj": visa_form, "user_profile": consultant.profile.name if consultant else None},
    )


@login_required
def edit_form_stage(request, pk: int):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    stage = get_object_or_404(VisaFormStage.objects.select_related("form"), pk=pk)
    visa_form = stage.form
    questions = stage.questions.all().order_by("order", "question")

    if request.method == "POST":
        form = VisaFormStageForm(data=request.POST, instance=stage)
        if form.is_valid():
            form.save()
            messages.success(request, "Etapa do formulário atualizada com sucesso.")
            return redirect("system:edit_form_stage", pk=stage.pk)
        messages.error(request, "Não foi possível atualizar a etapa do formulário.")
    else:
        form = VisaFormStageForm(instance=stage)

    return render(
        request,
        "forms/edit_form_stage.html",
        {
            "form": form,
            "stage": stage,
            "visa_form_obj": visa_form,
            "questions": questions,
            "user_profile": consultant.profile.name if consultant else None,
        },
    )


@login_required
@require_http_methods(["POST"])
def delete_form_stage(request, pk: int):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    stage = get_object_or_404(VisaFormStage.objects.select_related("form"), pk=pk)
    form_id = stage.form_id
    FormQuestion.objects.filter(stage=stage).update(stage=None)
    stage.delete()
    messages.success(request, "Etapa removida. Perguntas ficaram sem agrupamento.")
    return redirect("system:edit_form", pk=form_id)


@login_required
def delete_form(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    visa_form = get_object_or_404(VisaForm, pk=pk)
    visa_type_name = visa_form.visa_type.name
    visa_form.delete()

    messages.success(request, f"Formulário de {visa_type_name} excluído com sucesso.")
    return redirect("system:list_form_types")


@login_required
def create_question(request, form_id: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    visa_form = get_object_or_404(VisaForm, pk=form_id)

    if request.method == "POST":
        form = FormQuestionForm(data=request.POST, visa_form=visa_form)
        if form.is_valid():
            question = form.save()
            messages.success(request, f"Pergunta '{question.question}' adicionada com sucesso.")
            return redirect("system:edit_form", pk=visa_form.pk)
        messages.error(request, "Não foi possível criar a pergunta. Verifique os campos.")
    else:
        form = FormQuestionForm(visa_form=visa_form)

    context = {
        "form": form,
        "visa_form_obj": visa_form,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "forms/create_question.html", context)


@login_required
def edit_question(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    question = get_object_or_404(
        FormQuestion.objects.select_related("form"), pk=pk
    )
    visa_form = question.form
    options = question.options.all().order_by("order", "text") if question.field_type == "selecao" else []

    if request.method == "POST":
        form = FormQuestionForm(data=request.POST, instance=question, visa_form=visa_form)
        if form.is_valid():
            form.save()
            messages.success(request, f"Pergunta '{question.question}' atualizada com sucesso.")
            return redirect("system:edit_form", pk=visa_form.pk)
        messages.error(request, "Não foi possível atualizar a pergunta.")
    else:
        form = FormQuestionForm(instance=question, visa_form=visa_form)

    context = {
        "form": form,
        "question": question,
        "visa_form_obj": visa_form,
        "options_list": options,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "forms/edit_question.html", context)


@login_required
@require_http_methods(["POST"])
def delete_question(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    question = get_object_or_404(FormQuestion.objects.select_related("form"), pk=pk)
    visa_form = question.form
    question_text = question.question
    question.delete()

    messages.success(request, f"Pergunta '{question_text}' excluída com sucesso.")
    return redirect("system:edit_form", pk=visa_form.pk)


@login_required
def create_select_option(request, question_id: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    question = get_object_or_404(
        FormQuestion.objects.select_related("form"), pk=question_id
    )

    if question.field_type != "selecao":
        messages.error(request, "Apenas perguntas do tipo 'Seleção' podem ter opções.")
        return redirect("system:edit_question", pk=question.pk)

    if request.method == "POST":
        form = SelectOptionForm(data=request.POST, question=question)
        if form.is_valid():
            option = form.save()
            messages.success(request, f"Opção '{option.text}' adicionada com sucesso.")
            return redirect("system:edit_question", pk=question.pk)
        messages.error(request, "Não foi possível criar a opção. Verifique os campos.")
    else:
        form = SelectOptionForm(question=question)

    context = {
        "form": form,
        "question": question,
        "visa_form_obj": question.form,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "forms/create_select_option.html", context)


@login_required
def select_trip_client_form(request):
    from system.models import ConsultancyClient

    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if can_manage_all:
        client_ids = list(ConsultancyClient.objects.values_list("pk", flat=True))
    else:
        user_clients = list_clients(request.user)
        client_ids = list(user_clients.values_list("pk", flat=True))

    trips = Trip.objects.filter(
        clients__pk__in=client_ids,
        visa_type__form__isnull=False,
        visa_type__form__is_active=True
    ).select_related(
        "destination_country",
        "visa_type",
        "visa_type__form",
    ).prefetch_related("clients").distinct().order_by("-planned_departure_date")

    if request.method == "POST":
        trip_id = request.POST.get("trip_id")
        client_id = request.POST.get("client_id")

        if not trip_id or not client_id:
            messages.error(request, "Por favor, selecione uma viagem e um cliente.")
            return redirect("system:select_trip_client_form")

        try:
            trip = Trip.objects.get(pk=trip_id)
            client = ConsultancyClient.objects.get(pk=client_id)

            if not can_manage_all and int(client_id) not in client_ids:
                raise PermissionDenied("Você não tem permissão para acessar este cliente.")

            if client not in trip.clients.all():
                messages.error(request, "Este cliente não está vinculado a esta viagem.")
                return redirect("system:select_trip_client_form")

            return redirect("system:edit_client_form", trip_id=trip_id, client_id=client_id)
        except (Trip.DoesNotExist, ConsultancyClient.DoesNotExist, ValueError):
            messages.error(request, "Viagem ou cliente não encontrado.")
            return redirect("system:select_trip_client_form")

    trips_with_clients = []
    for trip in trips:
        trip_clients = trip.clients.filter(pk__in=client_ids).select_related("assigned_advisor")
        if trip_clients.exists():
            trips_with_clients.append({
                "trip": trip,
                "clients": trip_clients,
            })

    context = {
        "trips_with_clients": trips_with_clients,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
    }

    return render(request, "forms/select_trip_client_form.html", context)


@login_required
def edit_select_option(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    option = get_object_or_404(
        SelectOption.objects.select_related("question__form"), pk=pk
    )
    question = option.question

    if request.method == "POST":
        form = SelectOptionForm(data=request.POST, instance=option, question=question)
        if form.is_valid():
            form.save()
            messages.success(request, f"Opção '{option.text}' atualizada com sucesso.")
            return redirect("system:edit_question", pk=question.pk)
        messages.error(request, "Não foi possível atualizar a opção.")
    else:
        form = SelectOptionForm(instance=option, question=question)

    context = {
        "form": form,
        "option": option,
        "question": question,
        "visa_form_obj": question.form,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "forms/edit_select_option.html", context)


@login_required
@require_http_methods(["POST"])
def delete_select_option(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    option = get_object_or_404(
        SelectOption.objects.select_related("question__form"), pk=pk
    )
    question = option.question
    option_text = option.text
    option.delete()

    messages.success(request, f"Opção '{option_text}' excluída com sucesso.")
    return redirect("system:edit_question", pk=question.pk)
