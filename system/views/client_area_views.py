from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, Value, When
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
from system.services.form_responses import (
    answer_has_value,
    build_question_state,
    is_question_visible,
    process_form_answers,
)


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
    return _get_form_by_visa_type(client_visa_type, active_only=False)


def _get_target_client_for_trip(request, trip, session_client):
    raw_client_id = request.GET.get("client_id") or request.POST.get("client_id")
    if not raw_client_id:
        return session_client
    try:
        target_client_id = int(raw_client_id)
    except (TypeError, ValueError):
        return session_client
    if target_client_id == session_client.pk:
        return session_client
    link = TripClient.objects.filter(
        trip=trip,
        client_id=target_client_id,
        trip_primary_client=session_client,
    ).select_related("client").first()
    return link.client if link else session_client


def _build_member_form_progress(trip, member_client):
    visa_form = _get_client_form(trip, member_client)
    if not visa_form or not visa_form.is_active:
        return {
            "is_complete": False,
            "overview_label": "Formulário indisponível",
            "badge_class": "pendente",
            "current_stage_name": None,
            "total_questions": 0,
            "total_pending_questions": 0,
            "stage_progress": [],
        }

    questions_qs = visa_form.questions.filter(is_active=True).order_by("order", "question")
    questions = list(questions_qs)
    if not questions:
        return {
            "is_complete": True,
            "overview_label": "Sem perguntas pendentes",
            "badge_class": "respondido",
            "current_stage_name": None,
            "total_questions": 0,
            "total_pending_questions": 0,
            "stage_progress": [],
        }

    answers_by_question = {
        answer.question_id: answer
        for answer in FormAnswer.objects.filter(
            trip=trip,
            client=member_client,
            question_id__in=[q.pk for q in questions],
        ).select_related("answer_select")
    }

    stage_items = build_stage_items(visa_form)
    current_stage_name = None
    total_questions = 0
    total_answered = 0
    stage_progress = []
    question_state = build_question_state(questions, {}, answers_by_question)

    for stage_item in stage_items:
        stage_questions = [
            question
            for question in filter_questions_by_stage(questions_qs, stage_item)
            if is_question_visible(question, question_state)
        ]

        answered_count = 0
        for question in stage_questions:
            answer = answers_by_question.get(question.pk)
            if answer and answer_has_value(answer):
                answered_count += 1

        pending_count = max(len(stage_questions) - answered_count, 0)
        is_current = False
        if pending_count > 0 and current_stage_name is None:
            current_stage_name = stage_item["name"]
            is_current = True

        stage_progress.append(
            {
                "name": stage_item["name"],
                "total_questions": len(stage_questions),
                "pending_questions": pending_count,
                "is_current": is_current,
                "is_complete": pending_count == 0,
            }
        )
        total_questions += len(stage_questions)
        total_answered += answered_count

    total_pending = max(total_questions - total_answered, 0)
    if total_pending > 0:
        overview_label = (
            f"Etapa atual: {current_stage_name}"
            if current_stage_name
            else "Formulário pendente"
        )
        return {
            "is_complete": False,
            "overview_label": overview_label,
            "badge_class": "pendente",
            "current_stage_name": current_stage_name,
            "total_questions": total_questions,
            "total_pending_questions": total_pending,
            "stage_progress": stage_progress,
        }

    return {
        "is_complete": True,
        "overview_label": "Formulário concluído",
        "badge_class": "respondido",
        "current_stage_name": None,
        "total_questions": total_questions,
        "total_pending_questions": 0,
        "stage_progress": stage_progress,
    }


def client_dashboard(request):
    client = _get_client_from_session(request)
    if not client:
        messages.error(request, "Você precisa fazer login para acessar esta página.")
        return redirect("system:login")

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

    trip_clients = (
        TripClient.objects.filter(trip__in=trips)
        .select_related("trip", "client")
        .order_by(
            "trip_id",
            Case(
                When(role="primary", then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            "client__first_name",
            "client__last_name",
        )
    )

    members_by_trip_id = {}
    for trip_client in trip_clients:
        progress = _build_member_form_progress(trip_client.trip, trip_client.client)
        members_by_trip_id.setdefault(trip_client.trip_id, []).append(
            {
                "client": trip_client.client,
                "role": trip_client.role,
                "role_label": trip_client.get_role_display(),
                "form_overview_label": progress["overview_label"],
                "form_badge_class": progress["badge_class"],
                "current_stage_name": progress["current_stage_name"],
                "total_questions": progress["total_questions"],
                "total_pending_questions": progress["total_pending_questions"],
                "stage_progress": progress["stage_progress"],
            }
        )

    trip_cards = [
        {
            "trip": trip,
            "members": members_by_trip_id.get(trip.pk, []),
        }
        for trip in trips
    ]

    context = {
        "client": client,
        "trip_cards": trip_cards,
    }

    return render(request, "client_area/dashboard.html", context)


def client_view_form(request, trip_id: int):
    client = _get_client_from_session(request)
    if not client:
        messages.error(request, "Você precisa fazer login para acessar esta página.")
        return redirect("system:login")

    trip = get_object_or_404(
        Trip.objects.select_related("visa_type__form"), pk=trip_id
    )

    target_client = _get_target_client_for_trip(request, trip, client)

    client_in_trip = TripClient.objects.filter(trip=trip, client=target_client).exists()
    dependent_in_trip = (
        TripClient.objects.filter(
            trip=trip,
            client=target_client,
            trip_primary_client=client,
        ).exists()
        if target_client != client
        else False
    )

    if not (client_in_trip or dependent_in_trip):
        raise PermissionDenied("Você não tem permissão para acessar esta viagem.")

    visa_form = _get_client_form(trip, target_client)

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
        trip=trip, client=target_client
    ).select_related("answer_select")

    existing_answers = {r.question_id: r for r in answers_list}

    prefill_form_answers(trip, target_client, questions, existing_answers)

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

    answer_ids = [
        question_id
        for question_id, answer in existing_answers.items()
        if answer_has_value(answer)
    ]

    context = {
        "client": client,
        "form_client": target_client,
        "trip": trip,
        "visa_form_obj": visa_form,
        "questions": stage_questions_list,
        "all_questions": questions,
        "existing_answers": existing_answers,
        "answer_ids": answer_ids,
        "question_state": build_question_state(questions, {}, existing_answers),
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
        return redirect("system:login")

    trip = get_object_or_404(
        Trip.objects.select_related("visa_type__form"), pk=trip_id
    )

    target_client = _get_target_client_for_trip(request, trip, client)
    allowed = (
        TripClient.objects.filter(trip=trip, client=target_client).exists()
        and (
            target_client == client
            or TripClient.objects.filter(
                trip=trip,
                client=target_client,
                trip_primary_client=client,
            ).exists()
        )
    )
    if not allowed:
        raise PermissionDenied("Você não tem permissão para acessar esta viagem.")

    if request.method != "POST":
        return redirect("system:client_view_form", trip_id=trip_id)

    visa_form = _get_client_form(trip, target_client)
    if not visa_form:
        messages.error(request, "Formulário não encontrado.")
        return redirect("system:client_dashboard")

    questions = (
        visa_form.questions.filter(is_active=True)
        .prefetch_related("options")
    )

    existing_answers = {
        r.question_id: r for r in FormAnswer.objects.filter(
            trip=trip, client=target_client
        ).select_related("answer_select")
    }

    stage_items = build_stage_items(visa_form)
    stage_token = request.POST.get("stage_token")
    current_stage = resolve_stage_token(stage_items, stage_token)
    state_questions = list(questions)
    stage_questions = list(filter_questions_by_stage(questions, current_stage))

    saved_count, errors = process_form_answers(
        request.POST,
        trip,
        target_client,
        stage_questions,
        existing_answers,
        state_questions=state_questions,
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
            stage = next_stage["token"].replace(":", "%3A")
            return redirect(f"{reverse('system:client_view_form', args=[trip_id])}?client_id={target_client.pk}&stage={stage}")
        return redirect(f"{reverse('system:client_view_form', args=[trip_id])}?client_id={target_client.pk}")
    elif next_action == "finish":
        return redirect(f"{reverse('system:client_view_form', args=[trip_id])}?client_id={target_client.pk}")
    else:
        base = reverse("system:client_view_form", args=[trip_id])
        if current_stage:
            stage = current_stage["token"].replace(":", "%3A")
            return redirect(f"{base}?client_id={target_client.pk}&stage={stage}")
        return redirect(f"{base}?client_id={target_client.pk}")
