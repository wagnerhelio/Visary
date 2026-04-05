from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from system.models import (
    ConsultancyClient,
    FormAnswer,
    Trip,
    TripClient,
)
from system.views.travel_views import _get_form_by_visa_type, _get_client_visa_type
from system.services.form_stages import build_stage_items, filter_questions_by_stage, resolve_stage_token
from system.services.form_prefill import prefill_form_answers
from system.services.form_responses import build_question_state, is_question_visible, process_form_answers


def _get_client_from_session(request):
    client_id = request.session.get("client_id")
    if not client_id:
        return None
    try:
        return ConsultancyClient.objects.get(pk=client_id)
    except ConsultancyClient.DoesNotExist:
        return None


def _get_client_form(trip, client):
    client_visa_type = _get_client_visa_type(trip, client)
    return _get_form_by_visa_type(client_visa_type, only_active=False)


def client_dashboard(request):
    client = _get_client_from_session(request)
    if not client:
        messages.error(request, "Você precisa fazer login para acessar esta página.")
        return redirect("login")

    own_trip_ids = TripClient.objects.filter(
        client=client
    ).values_list("trip_id", flat=True)

    dependent_trip_ids = TripClient.objects.filter(
        trip_primary_client=client
    ).values_list("trip_id", flat=True)

    all_trip_ids = set(own_trip_ids) | set(dependent_trip_ids)

    trips = (
        Trip.objects.filter(pk__in=all_trip_ids)
        .select_related("destination_country", "visa_type", "assigned_advisor")
        .prefetch_related("visa_type__form", "clients")
        .distinct()
        .order_by("-planned_departure_date")
    )

    context = {
        "client": client,
        "trips": trips,
    }

    return render(request, "client_area/dashboard.html", context)


def client_view_form(request, trip_id: int):
    client = _get_client_from_session(request)
    if not client:
        messages.error(request, "Você precisa fazer login para acessar esta página.")
        return redirect("login")

    trip = get_object_or_404(
        Trip.objects.select_related("visa_type__form"), pk=trip_id
    )

    client_in_trip = TripClient.objects.filter(trip=trip, client=client).exists()
    dependent_in_trip = TripClient.objects.filter(
        trip=trip, trip_primary_client=client
    ).exists() if not client_in_trip else False

    if not (client_in_trip or dependent_in_trip):
        raise PermissionDenied("Você não tem permissão para acessar esta viagem.")

    visa_form = _get_client_form(trip, client)

    if not visa_form or not visa_form.is_active:
        messages.warning(
            request,
            "Este tipo de visto ainda não possui um formulário cadastrado ou o formulário está inativo.",
        )
        return redirect("system:client_dashboard")

    questions = (
        visa_form.questions.filter(is_active=True)
        .prefetch_related("options")
        .order_by("order", "question")
    )

    answers_list = FormAnswer.objects.filter(
        trip=trip, client=client
    ).select_related("answer_select")

    existing_answers = {r.question_id: r for r in answers_list}

    prefill_form_answers(trip, client, questions, existing_answers)

    stage_items = build_stage_items(visa_form)
    stage_token = request.GET.get("stage")
    current_stage = resolve_stage_token(stage_items, stage_token)
    stage_questions = filter_questions_by_stage(questions, current_stage)
    stage_questions_list = list(stage_questions)

    stage_index = 0
    if current_stage and stage_items:
        for i, item in enumerate(stage_items):
            if item["token"] == current_stage["token"]:
                stage_index = i
                break

    next_stage = stage_items[stage_index + 1] if stage_index + 1 < len(stage_items) else None
    prev_stage = stage_items[stage_index - 1] if stage_index > 0 else None

    answer_ids = list(existing_answers.keys())

    context = {
        "client": client,
        "trip": trip,
        "visa_form_obj": visa_form,
        "questions": stage_questions_list,
        "all_questions": questions,
        "existing_answers": existing_answers,
        "answer_ids": answer_ids,
        "stage_items": stage_items,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "prev_stage": prev_stage,
        "stage_index": stage_index,
    }

    return render(request, "client_area/view_form.html", context)


def client_save_answer(request, trip_id: int):
    client = _get_client_from_session(request)
    if not client:
        messages.error(request, "Você precisa fazer login para acessar esta página.")
        return redirect("login")

    trip = get_object_or_404(
        Trip.objects.select_related("visa_type__form"), pk=trip_id
    )

    if client not in trip.clients.all():
        raise PermissionDenied("Você não tem permissão para acessar esta viagem.")

    if request.method != "POST":
        return redirect("system:client_view_form", trip_id=trip_id)

    visa_form = _get_client_form(trip, client)
    if not visa_form:
        messages.error(request, "Formulário não encontrado.")
        return redirect("system:client_dashboard")

    questions = (
        visa_form.questions.filter(is_active=True)
        .prefetch_related("options")
    )

    existing_answers = {
        r.question_id: r for r in FormAnswer.objects.filter(
            trip=trip, client=client
        ).select_related("answer_select")
    }

    stage_items = build_stage_items(visa_form)
    stage_token = request.POST.get("stage_token")
    current_stage = resolve_stage_token(stage_items, stage_token)
    stage_questions = list(filter_questions_by_stage(questions, current_stage))

    saved_count, errors = process_form_answers(
        request.POST, trip, client, stage_questions, existing_answers
    )

    if errors:
        for error in errors:
            messages.error(request, error)
    else:
        messages.success(
            request,
            f"Etapa '{current_stage['name'] if current_stage else 'Atual'}' salva com sucesso! {saved_count} resposta(s) registrada(s).",
        )

    next_action = request.POST.get("next_action")
    if next_action == "next" and current_stage:
        next_stage = None
        for i, item in enumerate(stage_items):
            if item["token"] == current_stage["token"] and i + 1 < len(stage_items):
                next_stage = stage_items[i + 1]
                break
        if next_stage:
            return redirect(f"{reverse('system:client_view_form', args=[trip_id])}?stage={next_stage['token'].replace(':', '%3A')}")
        return redirect("system:client_view_form", trip_id=trip_id)
    elif next_action == "finish":
        return redirect("system:client_view_form", trip_id=trip_id)
    else:
        stage_param = f"?stage={current_stage['token'].replace(':', '%3A')}" if current_stage else ""
        return redirect(f"{reverse('system:client_view_form', args=[trip_id])}{stage_param}")
