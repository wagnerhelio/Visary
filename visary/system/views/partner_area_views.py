from contextlib import suppress
from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Q, Count, Sum
from django.shortcuts import redirect, render

from system.models import ConsultancyClient, TripClient, VisaForm, Process, FormAnswer, Trip
from system.models.financial_models import FinancialRecord, FinancialStatus


def _get_partner_from_session(request):
    partner_id = request.session.get("partner_id")
    if not partner_id:
        return None
    try:
        return type("Partner", (), {"pk": partner_id, "name": request.session.get("partner_name", "")})()
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


def _select_priority_items(priority_items, secondary_items, limit):
    selected = []
    seen = set()
    for item in priority_items:
        if item in seen:
            continue
        seen.add(item)
        selected.append(item)
        if len(selected) >= limit:
            return selected
    for item in secondary_items:
        if item in seen:
            continue
        seen.add(item)
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _get_client_financial_status(client):
    record = FinancialRecord.objects.filter(client=client).order_by("-created_at").first()
    if not record:
        return None
    return record.get_status_display()


def _get_client_form_status(client):
    total_questions = 0
    total_answers = 0
    trip_clients = TripClient.objects.filter(client=client).select_related("trip")
    for tc in trip_clients:
        visa_type = tc.visa_type or tc.trip.visa_type
        if not visa_type:
            continue
        visa_form = (
            VisaForm.objects.filter(visa_type=visa_type, is_active=True)
            .annotate(total=Count("questions", filter=Q(questions__is_active=True)))
            .first()
        )
        if visa_form:
            total_questions += visa_form.total
            total_answers += FormAnswer.objects.filter(
                trip=tc.trip, client=client
            ).count()
    if total_questions == 0:
        status = "Sem formulario"
    elif total_answers == 0:
        status = "Nao preenchido"
    elif total_answers >= total_questions:
        status = "Completo"
    else:
        status = "Parcial"
    return {"status": status, "total_questions": total_questions, "total_answers": total_answers}


def _get_client_visa_type(trip, client):
    with suppress(TripClient.DoesNotExist):
        trip_client = TripClient.objects.select_related("visa_type__form").get(
            trip=trip, client=client
        )
        if trip_client.visa_type:
            return trip_client.visa_type
    return trip.visa_type


def _get_form_by_visa_type(visa_type, only_active=True):
    if not visa_type or not hasattr(visa_type, "pk") or not visa_type.pk:
        return None
    try:
        if only_active:
            return VisaForm.objects.select_related("visa_type").get(
                visa_type_id=visa_type.pk, is_active=True
            )
        return VisaForm.objects.select_related("visa_type").get(visa_type_id=visa_type.pk)
    except VisaForm.DoesNotExist:
        return None


def partner_dashboard(request):
    partner = _get_partner_from_session(request)
    if not partner:
        messages.error(request, "Voce precisa fazer login para acessar a area do parceiro.")
        return redirect("login")

    dashboard_limit = 10
    near_trip_days = 30
    today = date.today()

    panel_filters = {
        "client": request.GET.get("client", "").strip(),
        "visa_type": request.GET.get("visa_type", "").strip(),
        "visa_form_obj": request.GET.get("visa_form_obj", "").strip(),
    }

    selected_client_id = _parse_positive_int(panel_filters["client"])
    selected_visa_id = _parse_positive_int(panel_filters["visa_type"])

    clients_base = ConsultancyClient.objects.filter(referring_partner_id=partner.pk)

    if selected_client_id:
        client_ids = {selected_client_id}
        trips_of_client = TripClient.objects.filter(
            client_id=selected_client_id
        ).values_list("trip_id", flat=True).distinct()
        client_ids.update(
            TripClient.objects.filter(trip_id__in=trips_of_client).values_list("client_id", flat=True)
        )
        clients_base = clients_base.filter(pk__in=client_ids)

    if selected_visa_id:
        clients_base = clients_base.filter(trips__visa_type_id=selected_visa_id).distinct()

    client_ids_list = list(clients_base.values_list("pk", flat=True))

    clients_qs = (
        clients_base.select_related("assigned_advisor", "created_by", "referring_partner")
        .prefetch_related("trips")
        .order_by("-created_at")
    )

    processes_qs = (
        Process.objects.filter(client__pk__in=client_ids_list)
        .select_related("trip", "trip__destination_country", "trip__visa_type", "client", "assigned_advisor")
        .prefetch_related("stages")
        .order_by("-created_at")
    )

    trips_qs = (
        Trip.objects.filter(clients__pk__in=client_ids_list)
        .select_related("destination_country", "visa_type", "assigned_advisor")
        .prefetch_related("clients")
        .distinct()
        .order_by("-planned_departure_date")
    )

    if selected_visa_id:
        processes_qs = processes_qs.filter(trip__visa_type_id=selected_visa_id)
        trips_qs = trips_qs.filter(visa_type_id=selected_visa_id)

    total_clients = clients_base.count()
    total_dependents = TripClient.objects.filter(
        client_id__in=client_ids_list, role="dependent"
    ).values("client_id").distinct().count()
    total_trips = trips_qs.count()
    total_near_trips = trips_qs.filter(
        planned_departure_date__gte=today,
        planned_departure_date__lte=today + timedelta(days=near_trip_days),
    ).count()
    total_completed_trips = trips_qs.filter(planned_return_date__lt=today).count()
    total_processes = processes_qs.count()
    total_ongoing_processes = (
        processes_qs.filter(Q(stages__completed=False) | Q(stages__isnull=True)).distinct().count()
    )
    total_completed_processes = max(total_processes - total_ongoing_processes, 0)
    total_forms = (
        FormAnswer.objects.filter(client__pk__in=client_ids_list)
        .values("trip", "client")
        .distinct()
        .count()
    )

    def build_client_item(client):
        financial_status = _get_client_financial_status(client)
        form_status = _get_client_form_status(client)
        return {
            "client": client,
            "financial_status": financial_status,
            "form_status": form_status["status"],
            "total_questions": form_status["total_questions"],
            "total_answers": form_status["total_answers"],
        }

    clients_with_status = [build_client_item(c) for c in clients_qs[:dashboard_limit]]

    if panel_filters["visa_form_obj"]:
        clients_with_status = [
            item
            for item in clients_with_status
            if item["form_status"].lower().replace("ã", "a")
            .replace("á", "a")
            .replace("ç", "c")
            .replace(" ", "-")
            == panel_filters["visa_form_obj"]
        ]

    recent_process_ids = list(processes_qs.values_list("pk", flat=True)[:dashboard_limit])
    unfinished_process_ids = list(
        processes_qs.filter(Q(stages__completed=False) | Q(stages__isnull=True))
        .values_list("pk", flat=True)
        .distinct()
    )
    display_process_ids = _select_priority_items(
        unfinished_process_ids, recent_process_ids, dashboard_limit
    )
    processes_display = list(processes_qs.filter(pk__in=display_process_ids))
    process_order = {pk: idx for idx, pk in enumerate(display_process_ids)}
    processes_display.sort(key=lambda p: process_order.get(p.pk, dashboard_limit + 1))

    recent_trip_ids = list(trips_qs.order_by("-created_at").values_list("pk", flat=True)[:dashboard_limit])
    near_trip_ids = list(
        trips_qs.filter(
            planned_departure_date__gte=today,
            planned_departure_date__lte=today + timedelta(days=near_trip_days),
        )
        .order_by("planned_departure_date")
        .values_list("pk", flat=True)
    )
    dashboard_trip_ids = _select_priority_items(
        near_trip_ids, recent_trip_ids, dashboard_limit
    )
    trips_dashboard = list(trips_qs.filter(pk__in=dashboard_trip_ids))
    trip_order = {pk: idx for idx, pk in enumerate(dashboard_trip_ids)}
    trips_dashboard.sort(key=lambda t: trip_order.get(t.pk, dashboard_limit + 1))

    form_candidates = []
    for trip in trips_qs.order_by("-created_at")[:50]:
        trip_clients = trip.clients.filter(pk__in=client_ids_list)
        if not trip_clients.exists():
            continue

        tc_map = {
            tc.client_id: tc.role
            for tc in TripClient.objects.filter(trip=trip)
        }
        sorted_clients = sorted(
            trip_clients,
            key=lambda c: (0 if tc_map.get(c.pk) == "primary" else 1, c.pk),
        )

        for client in sorted_clients:
            client_visa_type = _get_client_visa_type(trip, client)
            if not client_visa_type:
                continue
            visa_form = _get_form_by_visa_type(client_visa_type, only_active=True)
            if not visa_form:
                continue

            total_questions = visa_form.questions.filter(is_active=True).count()
            total_answers = FormAnswer.objects.filter(
                trip=trip, client=client
            ).count()
            is_complete = total_answers == total_questions if total_questions > 0 else False
            if is_complete:
                status_slug = "complete"
            elif total_answers == 0:
                status_slug = "nao-preenchido"
            else:
                status_slug = "parcial"

            form_candidates.append(
                {
                    "key": (trip.pk, client.pk),
                    "trip": trip,
                    "client_info": {
                        "client": client,
                        "visa_type": client_visa_type,
                        "visa_form_obj": visa_form,
                        "total_questions": total_questions,
                        "total_answers": total_answers,
                        "complete": is_complete,
                        "status_slug": status_slug,
                    },
                }
            )

    recent_forms = sorted(form_candidates, key=lambda item: item["trip"].created_at, reverse=True)
    incomplete_form_keys = [
        item["key"]
        for item in form_candidates
        if item["client_info"]["status_slug"] in {"parcial", "nao-preenchido"}
    ]
    recent_form_keys = [item["key"] for item in recent_forms]
    display_form_keys = _select_priority_items(
        incomplete_form_keys, recent_form_keys, dashboard_limit
    )
    form_map = {item["key"]: item for item in form_candidates}
    forms_display = [
        form_map[key]
        for key in display_form_keys
        if key in form_map
    ]

    if panel_filters["visa_form_obj"]:
        forms_display = [
            item for item in forms_display
            if item["client_info"]["status_slug"] == panel_filters["visa_form_obj"]
        ]

    pending_forms = [
        item for item in forms_display
        if item["client_info"]["status_slug"] in {"parcial", "nao-preenchido"}
    ]
    filled_forms = [
        item for item in forms_display
        if item["client_info"]["status_slug"] == "complete"
    ]
    total_pending_forms = len(pending_forms)
    total_filled_forms = len(filled_forms)
    total_monitored_forms = total_pending_forms + total_filled_forms

    if panel_filters["visa_form_obj"]:
        total_forms = total_pending_forms + total_filled_forms

    filter_clients = [
        {
            "pk": client.pk,
            "name": client.full_name,
            "principal_pk": None,
        }
        for client in clients_base.order_by("first_name")
    ]

    seen_visas = set()
    filter_visas = []
    for p in processes_display:
        tv = p.trip.visa_type
        if tv and tv.pk not in seen_visas:
            seen_visas.add(tv.pk)
            filter_visas.append({"pk": tv.pk, "name": tv.name})
    for item in pending_forms + filled_forms:
        tv = item["client_info"]["visa_type"]
        if tv and hasattr(tv, "pk") and tv.pk not in seen_visas:
            seen_visas.add(tv.pk)
            filter_visas.append({"pk": tv.pk, "name": tv.name})
    for trip in trips_dashboard:
        tv = trip.visa_type
        if tv and tv.pk not in seen_visas:
            seen_visas.add(tv.pk)
            filter_visas.append({"pk": tv.pk, "name": tv.name})
    filter_visas.sort(key=lambda x: x["name"].lower())

    partner_name_val = request.session.get("partner_name", "Parceiro")

    context = {
        "partner_name": partner_name_val,
        "clients_with_status": clients_with_status,
        "processes": processes_display,
        "dashboard_trips": trips_dashboard,
        "total_clients": total_clients,
        "total_dependents": total_dependents,
        "total_trips": total_trips,
        "total_upcoming_trips": total_near_trips,
        "total_completed_trips": total_completed_trips,
        "total_processes": total_processes,
        "total_ongoing_processes": total_ongoing_processes,
        "total_completed_processes": total_completed_processes,
        "total_forms": total_forms,
        "total_monitored_forms": total_monitored_forms,
        "total_pending_forms": total_pending_forms,
        "total_completed_forms": total_filled_forms,
        "pending_forms": pending_forms,
        "completed_forms": filled_forms,
        "client_filter_options": filter_clients,
        "visa_filter_options": filter_visas,
        "panel_filters": panel_filters,
        "dashboard_limit": dashboard_limit,
        "trip_proximity_days": near_trip_days,
    }

    return render(request, "partner_area/dashboard.html", context)


def partner_view_client(request, client_id: int):
    from django.shortcuts import get_object_or_404
    from django.db.models import Prefetch

    partner = _get_partner_from_session(request)
    if not partner:
        messages.error(request, "Voce precisa fazer login para acessar a area do parceiro.")
        return redirect("login")

    client = get_object_or_404(
        ConsultancyClient.objects.select_related(
            "assigned_advisor", "referring_partner"
        ),
        pk=client_id,
        referring_partner_id=partner.pk,
    )

    client_trips = list(
        TripClient.objects.filter(client=client)
        .select_related(
            "trip",
            "trip__destination_country",
            "trip__visa_type",
            "trip__assigned_advisor",
            "visa_type",
        )
        .order_by("-trip__planned_departure_date")
    )

    processes = (
        Process.objects.filter(client=client)
        .select_related("trip", "trip__destination_country", "trip__visa_type")
        .prefetch_related(Prefetch("stages"))
        .order_by("-created_at")
    )

    visa_type_ids = {
        item.visa_type_id or item.trip.visa_type_id for item in client_trips
    }
    visa_forms = VisaForm.objects.filter(
        is_active=True,
        visa_type_id__in=visa_type_ids,
    ).annotate(total_questions_count=Count("questions", filter=Q(questions__is_active=True)))
    form_by_type = {vf.visa_type_id: vf for vf in visa_forms}

    answers_by_trip = {
        item["trip_id"]: item["total"]
        for item in FormAnswer.objects.filter(
            client=client,
            trip_id__in=[item.trip_id for item in client_trips],
        )
        .values("trip_id")
        .annotate(total=Count("id"))
    }

    forms_summary = []
    for item in client_trips:
        visa_type = item.visa_type or item.trip.visa_type
        visa_form = form_by_type.get(visa_type.pk)
        total_questions = visa_form.total_questions_count if visa_form else 0
        total_answers = answers_by_trip.get(item.trip_id, 0)

        if total_questions == 0:
            status = "Nao aplicavel"
        elif total_answers == 0:
            status = "Nao preenchido"
        elif total_answers >= total_questions:
            status = "Completo"
        else:
            status = "Parcial"

        forms_summary.append(
            {
                "trip": item.trip,
                "visa_type": visa_type,
                "status": status,
                "total_answers": total_answers,
                "total_questions": total_questions,
            }
        )

    partner_name_val = request.session.get("partner_name", "Parceiro")

    context = {
        "partner_name": partner_name_val,
        "client": client,
        "client_trips": client_trips,
        "processes": processes,
        "forms_summary": forms_summary,
        "today": date.today(),
    }
    return render(request, "partner_area/view_client.html", context)


def partner_logout_view(request):
    if "partner_id" in request.session:
        partner_name = request.session.get("partner_name", "Parceiro")
        messages.success(request, f"Ate logo, {partner_name}!")
        request.session.flush()
    return redirect("login")
