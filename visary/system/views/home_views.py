from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import render

from system.models import (
    TripClient,
    VisaForm,
    DestinationCountry,
    Partner,
    Process,
    FormAnswer,
    Trip,
)
from system.models.financial_models import FinancialRecord, FinancialStatus
from system.views.client_views import (
    _get_client_financial_status,
    _get_client_form_status,
    list_clients,
    get_user_consultant,
    user_can_edit_client,
    user_can_manage_all,
)


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


def _build_period_dates(filters):
    year_start = _parse_positive_int(filters.get("financial_year_start"))
    year_end = _parse_positive_int(filters.get("financial_year_end"))
    month_start = _parse_positive_int(filters.get("financial_month_start"))
    month_end = _parse_positive_int(filters.get("financial_month_end"))

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


def _filter_financial_by_period(financial_qs, filters):
    start_date, end_date = _build_period_dates(filters)
    period_basis = filters.get("financial_period_basis", "entrada")

    if period_basis == "baixa":
        financial_qs = financial_qs.exclude(payment_date__isnull=True)
        if start_date:
            financial_qs = financial_qs.filter(payment_date__gte=start_date)
        if end_date:
            financial_qs = financial_qs.filter(payment_date__lte=end_date)
        return financial_qs

    if start_date:
        financial_qs = financial_qs.filter(created_at__date__gte=start_date)
    if end_date:
        financial_qs = financial_qs.filter(created_at__date__lte=end_date)
    return financial_qs


def _available_financial_years():
    years = set(FinancialRecord.objects.values_list("created_at__year", flat=True))
    years.update(
        FinancialRecord.objects.exclude(payment_date__isnull=True).values_list(
            "payment_date__year", flat=True
        )
    )
    return sorted([year for year in years if year], reverse=True)


def _get_client_visa_type(trip, client):
    from contextlib import suppress

    with suppress(TripClient.DoesNotExist):
        trip_client = TripClient.objects.select_related(
            "visa_type__form"
        ).get(trip=trip, client=client)
        if trip_client.visa_type:
            return trip_client.visa_type
    return trip.visa_type


def _get_form_by_visa_type(visa_type, active_only=True):
    if not visa_type or not hasattr(visa_type, "pk") or not visa_type.pk:
        return None
    try:
        if active_only:
            return VisaForm.objects.select_related("visa_type").get(
                visa_type_id=visa_type.pk, is_active=True
            )
        return VisaForm.objects.select_related("visa_type").get(
            visa_type_id=visa_type.pk
        )
    except VisaForm.DoesNotExist:
        return None


def _build_client_item(request, consultant, client):
    financial_status = _get_client_financial_status(client)
    form_status = _get_client_form_status(client)
    return {
        "client": client,
        "financial_status": financial_status,
        "form_status": form_status["status"],
        "total_questions": form_status["total_questions"],
        "total_answers": form_status["total_answers"],
        "can_edit": user_can_edit_client(
            request.user, consultant, client
        ),
    }


def _apply_form_status_filter(client_items, form_filter):
    if not form_filter:
        return client_items
    return [
        item
        for item in client_items
        if item["form_status"]
        .lower()
        .replace("ã", "a")
        .replace("á", "a")
        .replace("ç", "c")
        .replace(" ", "-")
        == form_filter
    ]


def _build_display_processes(processes_qs, limit):
    recent_ids = list(
        processes_qs.values_list("pk", flat=True)[:limit]
    )
    unfinished_ids = list(
        processes_qs.filter(
            Q(stages__completed=False) | Q(stages__isnull=True)
        )
        .values_list("pk", flat=True)
        .distinct()
    )
    display_ids = _select_priority_items(
        unfinished_ids, recent_ids, limit
    )
    display_list = list(processes_qs.filter(pk__in=display_ids))
    order_map = {pk: idx for idx, pk in enumerate(display_ids)}
    display_list.sort(
        key=lambda p: order_map.get(p.pk, limit + 1)
    )
    return display_list


def _build_dashboard_trips(trips_qs, today, proximity_days, limit):
    recent_ids = list(
        trips_qs.order_by("-created_at")
        .values_list("pk", flat=True)[:limit]
    )
    upcoming_ids = list(
        trips_qs.filter(
            planned_departure_date__gte=today,
            planned_departure_date__lte=today + timedelta(days=proximity_days),
        )
        .order_by("planned_departure_date")
        .values_list("pk", flat=True)
    )
    dashboard_ids = _select_priority_items(
        upcoming_ids, recent_ids, limit
    )
    dashboard_list = list(trips_qs.filter(pk__in=dashboard_ids))
    order_map = {pk: idx for idx, pk in enumerate(dashboard_ids)}
    dashboard_list.sort(
        key=lambda t: order_map.get(t.pk, limit + 1)
    )
    return dashboard_list


def _build_form_candidates(trips_qs, client_ids):
    candidates = []

    for trip in trips_qs.order_by("-created_at")[:50]:
        trip_clients = trip.clients.filter(pk__in=client_ids)
        if not trip_clients.exists():
            continue

        role_map = {
            tc.client_id: tc.role
            for tc in TripClient.objects.filter(trip=trip)
        }
        sorted_clients = sorted(
            trip_clients,
            key=lambda c: (
                0 if role_map.get(c.pk) == "primary" else 1,
                c.pk,
            ),
        )

        for client in sorted_clients:
            visa_type = _get_client_visa_type(trip, client)
            if not visa_type:
                continue
            form = _get_form_by_visa_type(visa_type, active_only=True)
            if not form:
                continue

            total_questions = form.questions.filter(is_active=True).count()
            total_answers = FormAnswer.objects.filter(
                trip=trip, client=client
            ).count()
            is_complete = (
                total_answers == total_questions
                if total_questions > 0
                else False
            )
            if is_complete:
                status_slug = "complete"
            elif total_answers == 0:
                status_slug = "nao-preenchido"
            else:
                status_slug = "parcial"

            candidates.append({
                "key": (trip.pk, client.pk),
                "trip": trip,
                "client_info": {
                    "client": client,
                    "visa_type": visa_type,
                    "visa_form_obj": form,
                    "total_questions": total_questions,
                    "total_answers": total_answers,
                    "complete": is_complete,
                    "status_slug": status_slug,
                },
            })

    return candidates


def _build_form_display(candidates, form_filter, limit):
    sorted_recent = sorted(
        candidates,
        key=lambda item: item["trip"].created_at,
        reverse=True,
    )
    incomplete_keys = [
        item["key"]
        for item in candidates
        if item["client_info"]["status_slug"] in {"parcial", "nao-preenchido"}
    ]
    recent_keys = [item["key"] for item in sorted_recent]
    display_keys = _select_priority_items(
        incomplete_keys, recent_keys, limit
    )
    candidate_map = {item["key"]: item for item in candidates}
    display = [
        candidate_map[key]
        for key in display_keys
        if key in candidate_map
    ]

    if form_filter:
        display = [
            item
            for item in display
            if item["client_info"]["status_slug"] == form_filter
        ]

    return display


def _build_visa_type_filter(display_processes, form_items, dashboard_trips):
    seen = set()
    visa_types = []

    for process in display_processes:
        vt = process.trip.visa_type
        if vt and vt.pk not in seen:
            seen.add(vt.pk)
            visa_types.append({"pk": vt.pk, "name": vt.name})

    for item in form_items:
        vt = item["client_info"]["visa_type"]
        if vt and hasattr(vt, "pk") and vt.pk not in seen:
            seen.add(vt.pk)
            visa_types.append({"pk": vt.pk, "name": vt.name})

    for trip in dashboard_trips:
        vt = trip.visa_type
        if vt and vt.pk not in seen:
            seen.add(vt.pk)
            visa_types.append({"pk": vt.pk, "name": vt.name})

    visa_types.sort(key=lambda x: x["name"].lower())
    return visa_types


def _compute_financial_kpis(panel_filters, selected_client_id, selected_visa_id, selected_financial_status):
    financial_qs = FinancialRecord.objects.all()

    if selected_client_id:
        related_ids = {selected_client_id}
        trip_ids = (
            TripClient.objects.filter(client_id=selected_client_id)
            .values_list("trip_id", flat=True)
            .distinct()
        )
        related_ids.update(
            TripClient.objects.filter(trip_id__in=trip_ids)
            .values_list("client_id", flat=True)
        )
        financial_qs = financial_qs.filter(client_id__in=related_ids)

    if selected_visa_id:
        financial_qs = financial_qs.filter(
            trip__visa_type_id=selected_visa_id
        )

    financial_qs = _filter_financial_by_period(financial_qs, panel_filters)

    if selected_financial_status and selected_financial_status != "sem_registros":
        financial_qs = financial_qs.filter(status=selected_financial_status)
    elif selected_financial_status == "sem_registros":
        financial_qs = financial_qs.none()

    total = financial_qs.aggregate(Sum("amount"))["amount__sum"] or 0
    paid = (
        financial_qs.filter(status=FinancialStatus.PAID)
        .aggregate(Sum("amount"))["amount__sum"]
        or 0
    )
    pending = (
        financial_qs.filter(status=FinancialStatus.PENDING)
        .aggregate(Sum("amount"))["amount__sum"]
        or 0
    )
    return total, paid, pending


@login_required
def home(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)
    is_admin = can_manage_all
    dashboard_limit = 10
    trip_proximity_days = 30
    today = date.today()

    panel_filters = {
        "client": request.GET.get("client", "").strip(),
        "visa_type": request.GET.get("visa_type", "").strip(),
        "visa_form_obj": request.GET.get("visa_form_obj", "").strip(),
        "financial": request.GET.get("financial", "").strip(),
        "financial_period_basis": request.GET.get("financial_period_basis", "entrada").strip() or "entrada",
        "financial_year_start": request.GET.get("financial_year_start", "").strip(),
        "financial_year_end": request.GET.get("financial_year_end", "").strip(),
        "financial_month_start": request.GET.get("financial_month_start", "").strip(),
        "financial_month_end": request.GET.get("financial_month_end", "").strip(),
    }

    selected_client_id = _parse_positive_int(panel_filters["client"])
    selected_visa_id = _parse_positive_int(panel_filters["visa_type"])
    selected_financial_status = panel_filters["financial"]
    if selected_financial_status == "sem-registros":
        selected_financial_status = "sem_registros"

    user_clients = list_clients(request.user)
    filter_base_clients = user_clients

    if selected_client_id:
        client_ids_set = {selected_client_id}
        client_trip_ids = (
            TripClient.objects.filter(client_id=selected_client_id)
            .values_list("trip_id", flat=True)
            .distinct()
        )
        client_ids_set.update(
            TripClient.objects.filter(trip_id__in=client_trip_ids)
            .values_list("client_id", flat=True)
        )
        user_clients = user_clients.filter(pk__in=client_ids_set)

    if selected_visa_id:
        user_clients = user_clients.filter(
            trips__visa_type_id=selected_visa_id
        ).distinct()

    if is_admin and selected_financial_status:
        filtered_financial = FinancialRecord.objects.exclude(
            client__isnull=True
        )
        filtered_financial = _filter_financial_by_period(
            filtered_financial, panel_filters
        )
        if selected_visa_id:
            filtered_financial = filtered_financial.filter(
                trip__visa_type_id=selected_visa_id
            )
        if selected_financial_status != "sem_registros":
            filtered_financial = filtered_financial.filter(
                status=selected_financial_status
            )
            user_clients = user_clients.filter(
                pk__in=filtered_financial.values("client_id")
            ).distinct()
        else:
            user_clients = user_clients.exclude(
                pk__in=filtered_financial.values("client_id")
            ).distinct()

    client_ids = list(user_clients.values_list("pk", flat=True))

    clients_qs = (
        user_clients.select_related(
            "assigned_advisor", "created_by", "referring_partner"
        )
        .prefetch_related("trips")
        .order_by("-created_at")
    )

    processes_qs = (
        Process.objects.filter(client__pk__in=client_ids)
        .select_related(
            "trip",
            "trip__destination_country",
            "trip__visa_type",
            "client",
            "assigned_advisor",
        )
        .prefetch_related("stages")
        .order_by("-created_at")
    )

    trips_qs = (
        Trip.objects.filter(clients__pk__in=client_ids)
        .select_related(
            "destination_country", "visa_type", "assigned_advisor"
        )
        .prefetch_related("clients")
        .distinct()
        .order_by("-planned_departure_date")
    )

    if selected_visa_id:
        processes_qs = processes_qs.filter(
            trip__visa_type_id=selected_visa_id
        )
        trips_qs = trips_qs.filter(visa_type_id=selected_visa_id)

    total_clients = user_clients.count()
    total_dependents = (
        TripClient.objects.filter(
            client_id__in=client_ids, role="dependent"
        )
        .values("client_id")
        .distinct()
        .count()
    )
    total_trips = trips_qs.count()
    total_upcoming_trips = trips_qs.filter(
        planned_departure_date__gte=today,
        planned_departure_date__lte=today + timedelta(days=trip_proximity_days),
    ).count()
    total_completed_trips = trips_qs.filter(
        planned_return_date__lt=today
    ).count()
    total_processes = processes_qs.count()
    total_ongoing_processes = (
        processes_qs.filter(
            Q(stages__completed=False) | Q(stages__isnull=True)
        )
        .distinct()
        .count()
    )
    total_completed_processes = max(
        total_processes - total_ongoing_processes, 0
    )
    total_forms = (
        FormAnswer.objects.filter(client__pk__in=client_ids)
        .values("trip", "client")
        .distinct()
        .count()
    )

    if is_admin:
        total_partners = Partner.objects.count()
        total_countries = DestinationCountry.objects.count()
        total_amount, paid_amount, pending_amount = _compute_financial_kpis(
            panel_filters,
            selected_client_id,
            selected_visa_id,
            selected_financial_status,
        )
    else:
        total_partners = 0
        total_countries = 0
        total_amount = 0
        paid_amount = 0
        pending_amount = 0

    clients_with_status = [
        _build_client_item(request, consultant, c)
        for c in clients_qs[:dashboard_limit]
    ]
    clients_with_status = _apply_form_status_filter(
        clients_with_status, panel_filters["visa_form_obj"]
    )

    display_processes = _build_display_processes(
        processes_qs, dashboard_limit
    )
    dashboard_trips = _build_dashboard_trips(
        trips_qs, today, trip_proximity_days, dashboard_limit
    )

    form_candidates = _build_form_candidates(trips_qs, client_ids)
    forms_display = _build_form_display(
        form_candidates, panel_filters["visa_form_obj"], dashboard_limit
    )

    pending_forms = [
        item
        for item in forms_display
        if item["client_info"]["status_slug"] in {"parcial", "nao-preenchido"}
    ]
    completed_forms = [
        item
        for item in forms_display
        if item["client_info"]["status_slug"] == "complete"
    ]
    total_pending_forms = len(pending_forms)
    total_completed_forms = len(completed_forms)
    total_monitored_forms = total_pending_forms + total_completed_forms

    if panel_filters["visa_form_obj"]:
        total_forms = total_pending_forms + total_completed_forms

    client_filter_options = [
        {
            "pk": client.pk,
            "name": client.full_name,
            "principal_pk": None,
        }
        for client in user_clients.order_by("first_name")
    ]

    visa_type_filter_options = _build_visa_type_filter(
        display_processes,
        pending_forms + completed_forms,
        dashboard_trips,
    )

    financial_years = _available_financial_years() if is_admin else []
    financial_months = [
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

    context = {
        "is_admin": is_admin,
        "consultant": consultant,
        "clients_with_status": clients_with_status,
        "processes": display_processes,
        "dashboard_trips": dashboard_trips,
        "total_clients": total_clients,
        "total_dependents": total_dependents,
        "total_trips": total_trips,
        "total_upcoming_trips": total_upcoming_trips,
        "total_completed_trips": total_completed_trips,
        "total_processes": total_processes,
        "total_ongoing_processes": total_ongoing_processes,
        "total_completed_processes": total_completed_processes,
        "total_countries": total_countries,
        "total_partners": total_partners,
        "total_forms": total_forms,
        "total_monitored_forms": total_monitored_forms,
        "total_pending_forms": total_pending_forms,
        "total_completed_forms": total_completed_forms,
        "pending_forms": pending_forms,
        "completed_forms": completed_forms,
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "pending_amount": pending_amount,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "client_filter_options": client_filter_options,
        "visa_filter_options": visa_type_filter_options,
        "panel_filters": panel_filters,
        "financial_years": financial_years,
        "financial_months": financial_months,
        "dashboard_limit": dashboard_limit,
        "trip_proximity_days": trip_proximity_days,
    }

    return render(request, "home/home.html", context)
