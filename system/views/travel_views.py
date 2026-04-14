import logging
from contextlib import suppress
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_http_methods

from system.forms import DestinationCountryForm, VisaTypeForm, TripForm
from system.models import (
    ConsultancyClient,
    ConsultancyUser,
    DestinationCountry,
    FinancialRecord,
    FinancialStatus,
    FormAnswer,
    Partner,
    Process,
    Trip,
    TripClient,
    VisaForm,
    VisaType,
)
from system.selectors import active_partners_ordered
from system.services.form_prefill import prefill_form_answers
from system.services.form_prefill_rules import should_prefill_from_client
from system.services.form_responses import (
    update_answer_by_type as _update_answer_by_type_svc,
    build_question_state,
    is_question_visible,
    process_form_answers,
)
from system.services.form_stages import (
    build_stage_items,
    filter_questions_by_stage,
    resolve_stage_token,
)
from system.views.client_views import (
    list_clients,
    get_user_consultant,
    user_can_manage_all,
)

logger = logging.getLogger("visary.travel")

_build_question_state = build_question_state
_is_question_visible = is_question_visible


def _clear_registered_trip_flags(request):
    if request.method == "GET":
        keys_to_clean = [
            key for key in request.session.keys()
            if key.startswith('trip_registered_')
        ]
        for key in keys_to_clean:
            request.session.pop(key, None)
        request.session.modified = True


def _get_trips_with_unfilled_forms(trips):
    result = []
    for trip in trips:
        form_obj = _get_form_by_visa_type(trip.visa_type, active_only=True)
        if not form_obj:
            continue
        total_clients = trip.clients.count()
        if total_clients <= 0:
            continue
        clients_with_answers = FormAnswer.objects.filter(
            trip=trip
        ).values_list("client_id", flat=True).distinct().count()
        clients_without_answers = total_clients - clients_with_answers
        if clients_without_answers > 0:
            result.append({
                "trip": trip,
                "total_clients": total_clients,
                "clients_without_answers": clients_without_answers,
            })
    return result


def _filter_messages_for_template(request):
    storage = messages.get_messages(request)
    filtered = []
    trip_message_shown = False
    seen_texts = set()

    for message in storage:
        message_text = str(message)
        if "Viagem cadastrada" in message_text:
            if not trip_message_shown:
                trip_message_shown = True
                filtered.append(message)
        elif message_text not in seen_texts:
            seen_texts.add(message_text)
            filtered.append(message)

    return filtered


@login_required
def home_trips(request):
    _clear_registered_trip_flags(request)

    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    user_clients = list_clients(request.user)
    client_ids = list(user_clients.values_list("pk", flat=True))

    trips = Trip.objects.filter(
        clients__pk__in=client_ids
    ).select_related(
        "destination_country",
        "visa_type__form",
        "assigned_advisor",
    ).prefetch_related("clients").distinct().order_by("-planned_departure_date")

    applied_filters = {}
    trips = _apply_trip_filters(trips, request, applied_filters, include_advisor=False)

    kpis = _build_trip_kpis(trips)
    trips_with_info = _prepare_trip_info(trips, can_manage_all, consultant)

    trips_with_forms = _get_trips_with_unfilled_forms(trips[:10])
    filtered_msgs = _filter_messages_for_template(request)

    countries = DestinationCountry.objects.filter(is_active=True).order_by("name")
    visa_types = VisaType.objects.filter(
        is_active=True
    ).select_related("destination_country").order_by("destination_country__name", "name")

    context = {
        "total_trips": trips.count(),
        "trips": trips[:10],
        "trips_with_info": trips_with_info,
        "trips_unfilled_forms": trips_with_forms,
        "user_profile": consultant.profile.name if consultant else None,
        "filtered_messages": filtered_msgs,
        "can_manage_all": can_manage_all,
        "consultant": consultant,
        "advisors": ConsultancyUser.objects.filter(is_active=True).order_by("name"),
        "countries": countries,
        "visa_types": visa_types,
        "clients": user_clients.order_by("first_name"),
        "applied_filters_dict": applied_filters,
        "partners": Partner.objects.filter(
            is_active=True
        ).order_by("company_name", "contact_name"),
        **kpis,
    }

    return render(request, "travel/home_trips.html", context)


@login_required
def home_destination_countries(request):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied
    can_manage_all = True

    countries = DestinationCountry.objects.all().order_by("name")
    countries, applied_filters = _apply_country_filters(countries, request)
    total_countries = countries.count()

    context = {
        "countries": countries[:10],
        "total_countries": total_countries,
        "user_profile": consultant.profile.name if consultant else "Administrador",
        "can_manage_all": can_manage_all,
        "applied_filters_dict": applied_filters,
    }

    return render(request, "travel/home_destination_countries.html", context)


@login_required
def home_visa_types(request):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied
    can_manage_all = True

    visa_types = VisaType.objects.select_related(
        "destination_country"
    ).order_by("destination_country__name", "name")
    visa_types, applied_filters = _apply_visa_type_filters(visa_types, request)
    total_types = visa_types.count()

    context = {
        "visa_types": visa_types[:10],
        "total_types": total_types,
        "user_profile": consultant.profile.name if consultant else "Administrador",
        "can_manage_all": can_manage_all,
        "applied_filters_dict": applied_filters,
        "countries": DestinationCountry.objects.filter(is_active=True).order_by("name"),
    }

    return render(request, "travel/home_visa_types.html", context)


def _apply_country_filters(countries, request):
    iso_code = (
        request.GET.get("iso_code", "").strip()
        or request.GET.get("codigo_iso", "").strip()
    )
    filters = {
        "search": request.GET.get("search", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "iso_code": iso_code,
    }

    if filters["search"]:
        countries = countries.filter(name__icontains=filters["search"])
    if filters["status"] == "ativo":
        countries = countries.filter(is_active=True)
    elif filters["status"] == "inativo":
        countries = countries.filter(is_active=False)
    if filters["iso_code"]:
        countries = countries.filter(iso_code__icontains=filters["iso_code"])

    return countries, filters


def _apply_visa_type_filters(visa_types, request):
    filters = {
        "search": request.GET.get("search", "").strip(),
        "country": request.GET.get("country", "").strip(),
        "status": request.GET.get("status", "").strip(),
    }

    if filters["search"]:
        visa_types = visa_types.filter(name__icontains=filters["search"])
    if filters["country"]:
        with suppress(ValueError, TypeError):
            visa_types = visa_types.filter(destination_country_id=int(filters["country"]))
    if filters["status"] == "ativo":
        visa_types = visa_types.filter(is_active=True)
    elif filters["status"] == "inativo":
        visa_types = visa_types.filter(is_active=False)

    return visa_types, filters


@login_required
def create_destination_country(request):
    consultant = get_user_consultant(request.user)

    if request.method == "POST":
        form = DestinationCountryForm(data=request.POST, user=request.user)
        if form.is_valid():
            country = form.save(commit=False)
            country.created_by = request.user
            country.save()
            messages.success(request, f"País {form.cleaned_data['name']} cadastrado com sucesso.")
            return redirect("system:home_destination_countries")
        messages.error(request, "Não foi possível cadastrar o país. Verifique os campos.")
    else:
        form = DestinationCountryForm(user=request.user)

    context = {
        "form": form,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "travel/create_destination_country.html", context)


@login_required
def create_visa_type(request):
    consultant = get_user_consultant(request.user)

    if request.method == "POST":
        form = VisaTypeForm(data=request.POST, user=request.user)
        if form.is_valid():
            visa_type = form.save(commit=False)
            visa_type.created_by = request.user
            visa_type.save()
            messages.success(
                request,
                f"Tipo de visto {form.cleaned_data['name']} cadastrado com sucesso.",
            )
            return redirect("system:home_visa_types")
        messages.error(request, "Não foi possível cadastrar o tipo de visto. Verifique os campos.")
    else:
        form = VisaTypeForm(user=request.user)

    context = {
        "form": form,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "travel/create_visa_type.html", context)


def _process_individual_visa_types(trip, selected_clients, separate_trip_member_ids, request):
    members_with_different_visa = []
    selected_clients = list(selected_clients)
    primary_client = _choose_trip_primary_client(selected_clients)

    for client in selected_clients:
        if client.pk in separate_trip_member_ids:
            continue

        client_visa_type = trip.visa_type
        if visa_type_id := (
            request.POST.get(f"visa_type_dependent_{client.pk}")
            or request.POST.get(f"visa_type_client_{client.pk}")
        ):
            with suppress(ValueError, TypeError):
                if vt_obj := VisaType.objects.filter(pk=int(visa_type_id)).first():
                    client_visa_type = vt_obj

        if client_visa_type.pk != trip.visa_type.pk:
            members_with_different_visa.append(client.pk)
        else:
            TripClient.objects.update_or_create(
                trip=trip,
                client=client,
                defaults=_trip_client_defaults(client, client_visa_type, primary_client),
            )

    return members_with_different_visa


def _choose_trip_primary_client(clients):
    for client in clients:
        if client.is_primary:
            return client
    return clients[0] if clients else None


def _trip_client_defaults(client, visa_type, primary_client):
    if not primary_client or client.pk == primary_client.pk:
        return {
            "visa_type": visa_type,
            "role": "primary",
            "trip_primary_client": None,
        }

    return {
        "visa_type": visa_type,
        "role": "dependent",
        "trip_primary_client": primary_client,
    }


def _process_separate_trips(trip, separate_member_ids, request):
    if not separate_member_ids:
        return []

    created_trips = []

    TripClient.objects.filter(
        trip=trip, client_id__in=separate_member_ids
    ).delete()
    trip.clients.remove(*separate_member_ids)

    for client_id in separate_member_ids:
        with suppress(ValueError, TypeError):
            member_client = ConsultancyClient.objects.get(pk=client_id)

            country_id = request.POST.get(f"destination_country_dependent_{client_id}")
            visa_type_id = request.POST.get(f"visa_type_dependent_{client_id}")
            departure_str = request.POST.get(f"departure_date_dependent_{client_id}")
            return_str = request.POST.get(f"return_date_dependent_{client_id}")

            dest_country = trip.destination_country
            if country_id:
                with suppress(ValueError, TypeError):
                    if country_obj := DestinationCountry.objects.filter(pk=int(country_id)).first():
                        dest_country = country_obj

            visa_type = trip.visa_type
            if visa_type_id:
                with suppress(ValueError, TypeError):
                    if vt_obj := VisaType.objects.filter(pk=int(visa_type_id)).first():
                        visa_type = vt_obj

            departure_date = trip.planned_departure_date
            if departure_str:
                if parsed := parse_date(departure_str):
                    departure_date = parsed

            return_date = trip.planned_return_date
            if return_str:
                if parsed := parse_date(return_str):
                    return_date = parsed

            separate_trip = Trip.objects.create(
                assigned_advisor=trip.assigned_advisor,
                destination_country=dest_country,
                visa_type=visa_type,
                planned_departure_date=departure_date,
                planned_return_date=return_date,
                advisory_fee=Decimal('0.00'),
                notes=f"Viagem separada para {member_client.first_name} (membro de {trip})",
                created_by=trip.created_by,
            )
            TripClient.objects.create(
                trip=separate_trip,
                client=member_client,
                visa_type=separate_trip.visa_type,
                role="primary",
                trip_primary_client=None,
            )
            created_trips.append(separate_trip)

    return created_trips


def _organize_trip_members(client_ids_list, trip=None):
    client_objs = ConsultancyClient.objects.filter(
        pk__in=client_ids_list
    ).select_related('primary_client', 'assigned_advisor').order_by('first_name')

    if trip:
        tc_map = {
            tc.client_id: tc
            for tc in TripClient.objects.filter(
                trip=trip, client_id__in=client_ids_list
            )
        }
        members = []
        for client in client_objs:
            tc = tc_map.get(client.pk)
            role = tc.role if tc else "dependent"
            members.append({
                'client': client,
                'role': role,
                'visa_type': tc.visa_type if tc else None,
                'trip_primary_client': tc.trip_primary_client if tc else None,
            })
        members.sort(key=lambda m: (0 if m['role'] == 'primary' else 1, m['client'].first_name))
        return members

    members = []
    for client in client_objs:
        members.append({
            'client': client,
            'role': 'primary' if client.is_primary else 'dependent',
            'visa_type': None,
        })
    members.sort(key=lambda m: (0 if m['role'] == 'primary' else 1, m['client'].first_name))
    return members


def _clear_client_registration_flags(request):
    keys_to_remove = [
        key for key in request.session.keys()
        if key.startswith('cadastro_finalizado_')
    ]
    for key in keys_to_remove:
        request.session.pop(key, None)

    stored_messages = request.session.get('_messages')
    if not stored_messages:
        request.session.modified = True
        return

    filtered = []
    seen_texts = set()

    for msg in stored_messages:
        message_text = str(msg.get('message', '') if isinstance(msg, dict) else msg)
        message_lower = message_text.lower()
        if any(phrase in message_lower for phrase in [
            "cadastro finalizado com sucesso",
            "cadastro finalizado",
            "cliente 'teste_principal'",
        ]):
            continue
        if message_text not in seen_texts:
            seen_texts.add(message_text)
            filtered.append(msg)

    if filtered:
        request.session['_messages'] = filtered
    else:
        request.session.pop('_messages', None)

    request.session.modified = True


def _clear_registration_complete_messages(request):
    phrases_to_remove = [
        "cadastro finalizado com sucesso",
        "cadastro finalizado",
        "cliente 'teste_principal'",
    ]

    if stored_messages := request.session.get('_messages'):
        filtered_session = [
            msg for msg in stored_messages
            if all(
                phrase not in str(msg.get('message', '') if isinstance(msg, dict) else msg).lower()
                for phrase in phrases_to_remove
            )
        ]

        if filtered_session:
            request.session['_messages'] = filtered_session
        else:
            request.session.pop('_messages', None)
        request.session.modified = True

    storage = messages.get_messages(request)
    kept_messages = []
    seen_texts = set()

    for message in storage:
        message_text = str(message)
        message_lower = message_text.lower()
        if any(phrase in message_lower for phrase in phrases_to_remove):
            continue
        if message_text not in seen_texts:
            seen_texts.add(message_text)
            kept_messages.append(message)

    storage.used = True

    for message in kept_messages:
        messages.add_message(
            request, message.level, message.message, extra_tags=message.extra_tags
        )


def _prepare_form_with_clients(request, form, client_ids_str):
    if not client_ids_str:
        return form

    client_ids_list, _ = _prepare_preselected_clients(client_ids_str)
    if client_ids_list:
        clients = ConsultancyClient.objects.filter(pk__in=client_ids_list)
        if clients.exists():
            form.fields["clients"].initial = [c.pk for c in clients]

    return form


def _get_preselected_client_ids_param(request):
    return request.GET.get("clients", "") or request.GET.get("clientes", "")


def _get_clients_and_trip_members(request):
    if request.method == "GET" and (client_ids := _get_preselected_client_ids_param(request)):
        return _prepare_preselected_clients(client_ids)
    return [], []


def _process_create_trip_post(request, form):
    if not form.is_valid():
        messages.error(request, "Não foi possível cadastrar a viagem. Verifique os campos.")
        return None

    action = request.POST.get("action", "save")

    keys_to_remove = [
        key for key in request.session.keys()
        if key.startswith('trip_registered_')
    ]
    for key in keys_to_remove:
        request.session.pop(key, None)
    request.session.modified = True

    trip = form.save()

    selected_clients = form.cleaned_data.get("clients", [])
    members_with_different_visa = _process_individual_visa_types(
        trip, selected_clients, [], request
    )

    separate_trips = _process_separate_trips(trip, members_with_different_visa, request)

    if stored_messages := request.session.get('_messages'):
        filtered = [
            msg for msg in stored_messages
            if "Viagem cadastrada" not in str(
                msg.get('message', '') if isinstance(msg, dict) else msg
            )
        ]
        request.session['_messages'] = filtered or None
        if not filtered:
            request.session.pop('_messages', None)
        request.session.modified = True

    storage = messages.get_messages(request)
    storage.used = True

    total_trips = 1 + len(separate_trips) if separate_trips else 1

    if action == "save_and_create_process":
        return _redirect_after_create_trip_to_process(trip, separate_trips)

    if total_trips > 1:
        messages.success(request, f"{total_trips} viagens cadastradas com sucesso.")
    else:
        messages.success(request, "Viagem cadastrada com sucesso.")

    return redirect("system:home_trips")


def _redirect_after_create_trip_to_process(trip, separate_trips):
    all_trip_ids = [trip.pk]
    if separate_trips:
        all_trip_ids.extend([t.pk for t in separate_trips])

    all_client_ids = set(trip.clients.all().values_list('pk', flat=True))
    for sep_trip in separate_trips:
        all_client_ids.update(sep_trip.clients.all().values_list('pk', flat=True))

    if all_client_ids:
        trips_with_clients = TripClient.objects.filter(
            client_id__in=list(all_client_ids)
        ).values_list("trip_id", flat=True).distinct()
        related_clients = TripClient.objects.filter(
            trip_id__in=trips_with_clients
        ).values_list("client_id", flat=True)
        all_client_ids.update(related_clients)

    if len(all_client_ids) == 1:
        client_id = list(all_client_ids)[0]
        client_obj = ConsultancyClient.objects.get(pk=client_id)
        client_trip = None
        if client_obj in trip.clients.all():
            client_trip = trip
        else:
            for sep_trip in separate_trips:
                if client_obj in sep_trip.clients.all():
                    client_trip = sep_trip
                    break

        if client_trip:
            return redirect(
                f"{reverse('system:create_process')}"
                f"?client_id={client_id}&trip_id={client_trip.pk}"
            )

    primary_client_id = TripClient.objects.filter(
        trip=trip,
        role="primary",
    ).values_list("client_id", flat=True).first()
    if not primary_client_id:
        primary_client_id = trip.clients.values_list("pk", flat=True).first()

    if primary_client_id:
        return redirect(
            f"{reverse('system:create_process')}"
            f"?client_id={primary_client_id}&trip_id={trip.pk}"
        )

    return redirect(f"{reverse('system:create_process')}?trip_id={trip.pk}")


def _prepare_preselected_clients(client_ids_str):
    client_ids_list = []
    with suppress(ValueError, TypeError):
        client_ids_list = [
            int(id_str.strip())
            for id_str in client_ids_str.split(",")
            if id_str.strip()
        ]

    if not client_ids_list:
        return [], []

    trip_members = _organize_trip_members(client_ids_list)
    return list(client_ids_list), trip_members


def _prepare_create_trip_context(form, consultant, preselected_clients, trip_members):
    available_visa_types = VisaType.objects.filter(
        is_active=True
    ).select_related("destination_country").order_by("destination_country__name", "name")

    return {
        "form": form,
        "user_profile": consultant.profile.name if consultant else None,
        "preselected_clients": preselected_clients,
        "trip_members": trip_members,
        "available_visa_types": available_visa_types,
    }


@login_required
def create_trip(request):
    consultant = get_user_consultant(request.user)

    if request.method == "GET" and _get_preselected_client_ids_param(request):
        _clear_client_registration_flags(request)
        request.session.save()
        _clear_client_registration_flags(request)
        _clear_registration_complete_messages(request)

    if request.method == "POST":
        form = TripForm(data=request.POST, user=request.user)
        if redirect_response := _process_create_trip_post(request, form):
            return redirect_response
    else:
        form = TripForm(user=request.user)
        if client_ids := _get_preselected_client_ids_param(request):
            form = _prepare_form_with_clients(request, form, client_ids)

    preselected_clients, trip_members = _get_clients_and_trip_members(request)

    if request.method == "GET" and _get_preselected_client_ids_param(request):
        phrases_to_remove = [
            "cadastro finalizado com sucesso",
            "cadastro finalizado",
            "cliente 'teste_principal'",
        ]
        for _ in range(3):
            _clear_client_registration_flags(request)
            _clear_registration_complete_messages(request)
            if stored := request.session.get('_messages'):
                filtered = [
                    msg for msg in stored
                    if all(
                        phrase not in str(
                            msg.get('message', '') if isinstance(msg, dict) else msg
                        ).lower()
                        for phrase in phrases_to_remove
                    )
                ]
                if filtered:
                    request.session['_messages'] = filtered
                else:
                    request.session.pop('_messages', None)
                request.session.modified = True
            request.session.save()

    context = _prepare_create_trip_context(
        form, consultant, preselected_clients, trip_members
    )
    return render(request, "travel/create_trip.html", context)


@login_required
def list_destination_countries(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    countries = DestinationCountry.objects.all().order_by("name")
    countries, applied_filters = _apply_country_filters(countries, request)

    context = {
        "countries": countries,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "applied_filters_dict": applied_filters,
    }

    return render(request, "travel/list_destination_countries.html", context)


def _clear_duplicate_session_messages(request):
    if not (stored_messages := request.session.get('_messages')):
        return

    filtered = []
    seen_texts = set()
    for msg in stored_messages:
        message_text = str(msg.get('message', '') if isinstance(msg, dict) else msg)
        if message_text not in seen_texts:
            seen_texts.add(message_text)
            filtered.append(msg)

    if filtered:
        request.session['_messages'] = filtered
    else:
        request.session.pop('_messages', None)
    request.session.modified = True

    storage = messages.get_messages(request)
    storage.used = True


@login_required
def edit_destination_country(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    country = get_object_or_404(DestinationCountry, pk=pk)

    if request.method == "POST":
        _clear_duplicate_session_messages(request)

        form = DestinationCountryForm(data=request.POST, instance=country)
        if form.is_valid():
            updated_country = form.save()
            messages.success(request, f"País {updated_country.name} atualizado com sucesso.")
            return redirect("system:list_destination_countries")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label}: {error}")
    else:
        form = DestinationCountryForm(instance=country)

    context = {
        "form": form,
        "country": country,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "travel/edit_destination_country.html", context)


@login_required
def view_destination_country(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    country = get_object_or_404(
        DestinationCountry.objects.select_related("created_by"),
        pk=pk,
    )

    visa_types = VisaType.objects.filter(
        destination_country=country
    ).select_related("destination_country").prefetch_related("form").order_by("name")

    trips = Trip.objects.filter(
        destination_country=country
    ).select_related(
        "visa_type",
        "assigned_advisor",
        "destination_country",
    ).prefetch_related("clients").order_by("-planned_departure_date")

    context = {
        "country": country,
        "visa_types": visa_types,
        "trips": trips,
        "total_visa_types": visa_types.count(),
        "total_trips": trips.count(),
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "can_edit": can_manage_all,
    }

    return render(request, "travel/view_destination_country.html", context)


@login_required
def verify_destination_country_deletion(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    country = get_object_or_404(DestinationCountry, pk=pk)

    trips = Trip.objects.filter(destination_country=country).select_related(
        "visa_type",
        "assigned_advisor",
    ).prefetch_related("clients").order_by("-planned_departure_date")

    visa_types = VisaType.objects.filter(
        destination_country=country
    ).select_related("destination_country").order_by("name")

    trip_clients = TripClient.objects.filter(
        trip__destination_country=country
    ).select_related(
        "client", "trip", "visa_type"
    ).order_by("-trip__planned_departure_date")

    context = {
        "country": country,
        "trips": trips,
        "visa_types": visa_types,
        "trip_clients_list": trip_clients,
        "total_trips": trips.count(),
        "total_visa_types": visa_types.count(),
        "total_trip_clients": trip_clients.count(),
        "can_delete": trips.count() == 0,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
    }

    return render(request, "travel/verify_destination_country_deletion.html", context)


@login_required
@require_http_methods(["POST"])
def delete_destination_country(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    _clear_duplicate_session_messages(request)

    country = get_object_or_404(DestinationCountry, pk=pk)

    trips = Trip.objects.filter(destination_country=country)
    if trips.exists():
        messages.error(
            request,
            f"Não é possível excluir o país {country.name} pois existem "
            f"{trips.count()} viagem(ns) vinculada(s). Exclua as viagens primeiro.",
        )
        return redirect("system:verify_destination_country_deletion", pk=pk)

    country_name = country.name
    country.delete()

    messages.success(request, f"País {country_name} excluído com sucesso.")
    return redirect("system:list_destination_countries")


@login_required
def list_visa_types(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    visa_types = VisaType.objects.select_related(
        "destination_country"
    ).order_by("destination_country__name", "name")
    visa_types, applied_filters = _apply_visa_type_filters(visa_types, request)

    context = {
        "visa_types": visa_types,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "applied_filters_dict": applied_filters,
        "countries": DestinationCountry.objects.filter(is_active=True).order_by("name"),
    }

    return render(request, "travel/list_visa_types.html", context)


@login_required
def view_visa_type(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    visa_type = get_object_or_404(
        VisaType.objects.select_related("destination_country", "created_by"),
        pk=pk,
    )

    form_obj = None
    try:
        form_obj = VisaForm.objects.select_related(
            "visa_type"
        ).prefetch_related("questions").get(visa_type=visa_type)
    except VisaForm.DoesNotExist:
        messages.info(request, "Nenhum formulário disponível para este tipo de visto.")

    trips = Trip.objects.filter(
        visa_type=visa_type
    ).select_related(
        "destination_country",
        "assigned_advisor",
        "visa_type",
    ).prefetch_related("clients").order_by("-planned_departure_date")

    context = {
        "visa_type": visa_type,
        "visa_form_obj": form_obj,
        "trips": trips,
        "total_trips": trips.count(),
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "can_edit": can_manage_all,
    }

    return render(request, "travel/view_visa_type.html", context)


@login_required
def edit_visa_type(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    visa_type = get_object_or_404(
        VisaType.objects.select_related("destination_country"), pk=pk
    )

    if request.method == "POST":
        form = VisaTypeForm(data=request.POST, instance=visa_type)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Tipo de visto {form.cleaned_data['name']} atualizado com sucesso.",
            )
            return redirect("system:list_visa_types")
        messages.error(request, "Não foi possível atualizar o tipo de visto. Verifique os campos.")
    else:
        form = VisaTypeForm(instance=visa_type)
        if visa_type.destination_country:
            form.fields["destination_country"].initial = visa_type.destination_country.pk

    context = {
        "form": form,
        "visa_type": visa_type,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "travel/edit_visa_type.html", context)


@login_required
@require_http_methods(["POST"])
def delete_visa_type(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    visa_type = get_object_or_404(VisaType, pk=pk)
    type_name = visa_type.name
    visa_type.delete()

    messages.success(request, f"Tipo de visto {type_name} excluído com sucesso.")
    return redirect("system:list_visa_types")


def _apply_trip_filters(trips, request, applied_filters, include_advisor=True):
    if include_advisor and (advisor_id := request.GET.get("advisor")):
        with suppress(ValueError, TypeError):
            trips = trips.filter(assigned_advisor_id=int(advisor_id))
            applied_filters["advisor"] = int(advisor_id)

    if country_id := request.GET.get("country"):
        with suppress(ValueError, TypeError):
            trips = trips.filter(destination_country_id=int(country_id))
            applied_filters["country"] = int(country_id)

    if visa_type_id := request.GET.get("visa_type"):
        with suppress(ValueError, TypeError):
            trips = trips.filter(visa_type_id=int(visa_type_id))
            applied_filters["visa_type"] = int(visa_type_id)

    if departure_start := request.GET.get("departure_date_start"):
        with suppress(ValueError, TypeError):
            start_date = datetime.strptime(departure_start, "%Y-%m-%d").date()
            trips = trips.filter(planned_departure_date__gte=start_date)
            applied_filters["departure_date_start"] = departure_start
    if departure_end := request.GET.get("departure_date_end"):
        with suppress(ValueError, TypeError):
            end_date = datetime.strptime(departure_end, "%Y-%m-%d").date()
            trips = trips.filter(planned_departure_date__lte=end_date)
            applied_filters["departure_date_end"] = departure_end

    if return_start := request.GET.get("return_date_start"):
        with suppress(ValueError, TypeError):
            start_date = datetime.strptime(return_start, "%Y-%m-%d").date()
            trips = trips.filter(planned_return_date__gte=start_date)
            applied_filters["return_date_start"] = return_start
    if return_end := request.GET.get("return_date_end"):
        with suppress(ValueError, TypeError):
            end_date = datetime.strptime(return_end, "%Y-%m-%d").date()
            trips = trips.filter(planned_return_date__lte=end_date)
            applied_filters["return_date_end"] = return_end

    if min_fee := request.GET.get("min_fee"):
        with suppress(ValueError, TypeError):
            trips = trips.filter(advisory_fee__gte=float(min_fee))
            applied_filters["min_fee"] = min_fee
    if max_fee := request.GET.get("max_fee"):
        with suppress(ValueError, TypeError):
            trips = trips.filter(advisory_fee__lte=float(max_fee))
            applied_filters["max_fee"] = max_fee

    if client_name := request.GET.get("client"):
        client_name = client_name.strip()
        if client_name:
            trips = trips.filter(
                Q(clients__first_name__icontains=client_name)
                | Q(clients__last_name__icontains=client_name)
            ).distinct()
            applied_filters["client"] = client_name

    if partner_id := request.GET.get("partner_obj"):
        with suppress(ValueError, TypeError):
            trips = trips.filter(
                clients__referring_partner_id=int(partner_id)
            ).distinct()
            applied_filters["partner_obj"] = int(partner_id)

    if creation_start := request.GET.get("creation_date_start"):
        with suppress(ValueError, TypeError):
            start_date = datetime.strptime(creation_start, "%Y-%m-%d").date()
            trips = trips.filter(created_at__date__gte=start_date)
            applied_filters["creation_date_start"] = creation_start
    if creation_end := request.GET.get("creation_date_end"):
        with suppress(ValueError, TypeError):
            end_date = datetime.strptime(creation_end, "%Y-%m-%d").date()
            trips = trips.filter(created_at__date__lte=end_date)
            applied_filters["creation_date_end"] = creation_end

    return trips


def _build_trip_kpis(trips):
    trip_ids = list(trips.values_list("pk", flat=True).distinct())
    base = Trip.objects.filter(pk__in=trip_ids)
    today = date.today()
    upcoming_threshold = today + timedelta(days=30)

    total = base.count()
    completed = base.filter(planned_return_date__lt=today).count()
    upcoming = base.filter(
        planned_departure_date__gte=today,
        planned_departure_date__lte=upcoming_threshold,
    ).count()

    by_visa_type = list(
        base.values("visa_type__name").annotate(
            total=Count("pk")
        ).order_by("-total", "visa_type__name")
    )
    by_country = list(
        base.values("destination_country__name").annotate(
            total=Count("pk")
        ).order_by("-total", "destination_country__name")
    )

    return {
        "total_trips_kpi": total,
        "total_completed_trips": completed,
        "total_upcoming_trips": upcoming,
        "count_by_visa_type": by_visa_type,
        "count_by_country": by_country,
    }


def _prepare_trip_info(trips, can_manage_all, consultant):
    result = []
    for trip in trips:
        form_obj = _get_form_by_visa_type(trip.visa_type, active_only=True)
        has_form = form_obj is not None
        total_clients = trip.clients.count()
        clients_with_answers = 0

        if form_obj and total_clients > 0:
            clients_with_answers = FormAnswer.objects.filter(
                trip=trip
            ).values_list("client_id", flat=True).distinct().count()

        total_processes = Process.objects.filter(trip=trip).count()
        clients_without_process = (
            total_clients - total_processes if total_clients > 0 else 0
        )

        linked_partners = {
            client.referring_partner
            for client in trip.clients.all()
            if client.referring_partner
        }
        can_edit_delete = can_manage_all or (
            consultant and trip.assigned_advisor_id == consultant.pk
        )

        result.append({
            "trip": trip,
            "has_form": has_form,
            "total_clients": total_clients,
            "clients_with_answers": clients_with_answers,
            "clients_without_answers": (
                total_clients - clients_with_answers if has_form else 0
            ),
            "total_processes": total_processes,
            "clients_without_process": clients_without_process,
            "can_edit_delete": can_edit_delete,
            "linked_partners": list(linked_partners),
        })

    return result


def _process_form_answers(request, trip, client, questions, existing_answers=None):
    return process_form_answers(
        request.POST, trip, client, questions, existing_answers
    )


def _get_client_visa_type(trip, client):
    with suppress(TripClient.DoesNotExist):
        trip_client = TripClient.objects.select_related(
            'visa_type__form'
        ).get(trip=trip, client=client)
        if trip_client.visa_type:
            return trip_client.visa_type
    return trip.visa_type


def _get_form_by_visa_type(visa_type, active_only=True):
    if not visa_type or not hasattr(visa_type, 'pk') or not visa_type.pk:
        return None

    try:
        if active_only:
            return VisaForm.objects.select_related('visa_type').get(
                visa_type_id=visa_type.pk, is_active=True,
            )
        return VisaForm.objects.select_related('visa_type').get(
            visa_type_id=visa_type.pk,
        )
    except VisaForm.DoesNotExist:
        return None


def _get_form_data(trip, client, stage_token=None):
    visa_type = _get_client_visa_type(trip, client)

    if not visa_type:
        return None, None, None, None, None, None

    form_obj = _get_form_by_visa_type(visa_type, active_only=True)

    if not form_obj:
        return None, None, None, None, None, None

    questions = (
        form_obj.questions.filter(is_active=True)
        .prefetch_related("options")
        .order_by("order", "question")
    )

    answers_list = FormAnswer.objects.filter(
        trip=trip, client=client
    ).select_related("answer_select")

    existing_answers = {a.question_id: a for a in answers_list}

    prefill_form_answers(trip, client, questions, existing_answers)

    stage_items = build_stage_items(form_obj)
    current_stage = resolve_stage_token(stage_items, stage_token)
    stage_questions = filter_questions_by_stage(questions, current_stage)

    return (
        form_obj, questions, existing_answers,
        stage_items, current_stage, list(stage_questions),
    )


def _update_form_answer(answer, question, value):
    _update_answer_by_type_svc(answer, question, value)


@login_required
def list_trips(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    trips = Trip.objects.select_related(
        "destination_country",
        "visa_type__form",
        "assigned_advisor",
    ).prefetch_related(
        "clients", "clients__referring_partner"
    ).order_by("-planned_departure_date")

    applied_filters = {}
    trips = _apply_trip_filters(trips, request, applied_filters)
    kpis = _build_trip_kpis(trips)

    trips_with_info = _prepare_trip_info(trips, can_manage_all, consultant)

    advisors = ConsultancyUser.objects.filter(is_active=True).order_by("name")
    countries = DestinationCountry.objects.filter(is_active=True).order_by("name")
    visa_types = VisaType.objects.filter(
        is_active=True
    ).select_related("destination_country").order_by("destination_country__name", "name")
    clients = ConsultancyClient.objects.order_by("first_name")
    partners = active_partners_ordered()

    context = {
        "trips_with_info": trips_with_info,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "is_admin": can_manage_all,
        "advisors": advisors,
        "countries": countries,
        "visa_types": visa_types,
        "clients": clients,
        "partners": partners,
        "applied_filters_dict": applied_filters,
        **kpis,
    }

    return render(request, "travel/list_trips.html", context)


@login_required
def view_trip(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    trip = get_object_or_404(
        Trip.objects.select_related(
            "destination_country",
            "visa_type",
            "visa_type__form",
            "assigned_advisor",
        ).prefetch_related("clients"),
        pk=pk,
    )

    trip_clients_qs = TripClient.objects.filter(
        trip=trip
    ).select_related(
        "client", "client__assigned_advisor", "trip_primary_client", "visa_type"
    ).order_by(
        models.Case(
            models.When(role="primary", then=0),
            default=1,
            output_field=models.IntegerField(),
        ),
        "client__first_name",
    )

    processes = Process.objects.filter(
        trip=trip
    ).select_related(
        "client",
        "assigned_advisor",
    ).prefetch_related("stages", "stages__status").order_by("-created_at")

    clients_with_info = []
    for tc in trip_clients_qs:
        client = tc.client
        client_visa_type = _get_client_visa_type(trip, client)
        form_obj = _get_form_by_visa_type(client_visa_type, active_only=False)

        has_answer = False
        total_questions = 0
        total_answers = 0

        if form_obj and form_obj.is_active:
            questions = form_obj.questions.filter(is_active=True)
            total_questions = questions.count()
            if total_questions > 0:
                answers = FormAnswer.objects.filter(trip=trip, client=client)
                total_answers = answers.count()
                has_answer = total_answers > 0

        clients_with_info.append({
            "client": client,
            "visa_type": client_visa_type,
            "visa_form_obj": form_obj,
            "has_answer": has_answer,
            "total_questions": total_questions,
            "total_answers": total_answers,
            "complete": (
                has_answer and total_answers == total_questions
                if total_questions > 0 else False
            ),
            "role": tc.role,
            "trip_primary_client": tc.trip_primary_client,
        })

    financial_records = FinancialRecord.objects.filter(
        trip=trip
    ).select_related(
        "client",
        "assigned_advisor",
    ).order_by("-created_at")

    can_edit = can_manage_all or (
        consultant and trip.assigned_advisor_id == consultant.pk
    )

    roles_by_client = {
        item["client"].pk: item["role"] for item in clients_with_info
    }

    context = {
        "trip": trip,
        "clients_with_info": clients_with_info,
        "processes": processes,
        "financial_records": financial_records,
        "roles_by_client": roles_by_client,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "can_edit": can_edit,
    }

    return render(request, "travel/view_trip.html", context)


@login_required
def edit_trip(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    trip = get_object_or_404(
        Trip.objects.select_related(
            "destination_country", "visa_type", "assigned_advisor"
        ),
        pk=pk,
    )

    if not can_manage_all and (
        not consultant or trip.assigned_advisor_id != consultant.pk
    ):
        raise PermissionDenied("Você não tem permissão para editar esta viagem.")

    if request.method == "POST":
        form = TripForm(data=request.POST, user=request.user, instance=trip)
        if form.is_valid():
            form.save()
            messages.success(request, "Viagem atualizada com sucesso.")
            return redirect("system:list_trips")
        messages.error(request, "Não foi possível atualizar a viagem. Verifique os campos.")
    else:
        form = TripForm(user=request.user, instance=trip)

    context = {
        "form": form,
        "trip": trip,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "travel/edit_trip.html", context)


@login_required
@require_http_methods(["POST"])
def delete_trip(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    trip = get_object_or_404(
        Trip.objects.select_related("assigned_advisor"),
        pk=pk,
    )

    if not can_manage_all and (
        not consultant or trip.assigned_advisor_id != consultant.pk
    ):
        raise PermissionDenied("Você não tem permissão para excluir esta viagem.")

    country_name = trip.destination_country.name
    departure_str = trip.planned_departure_date.strftime("%d/%m/%Y")
    trip.delete()

    messages.success(
        request,
        f"Viagem para {country_name} ({departure_str}) excluída com sucesso.",
    )
    return redirect("system:list_trips")


@login_required
@require_GET
def api_visa_types(request):
    country_id = (
        request.GET.get("country", "")
        or request.GET.get("pais_id", "")
        or request.GET.get("pais", "")
    ).strip()

    if not country_id:
        return JsonResponse({"error": "Informe um país."}, status=400)

    with suppress(ValueError, TypeError):
        visa_types = VisaType.objects.filter(
            destination_country_id=int(country_id),
            is_active=True,
        ).order_by("name")

        data = [{"id": vt.id, "name": vt.name} for vt in visa_types]
        return JsonResponse(data, safe=False)
    return JsonResponse({"error": "País inválido."}, status=400)


@login_required
@require_GET
def api_client_dependents(request):
    client_id = request.GET.get("client_id", "").strip()
    if not client_id:
        return JsonResponse([], safe=False)
    with suppress(ValueError, TypeError):
        client = ConsultancyClient.objects.get(pk=int(client_id))
        dependents = ConsultancyClient.objects.filter(
            primary_client=client
        ).order_by("first_name")
        data = [{"id": d.pk, "name": d.full_name} for d in dependents]
        return JsonResponse(data, safe=False)
    return JsonResponse([], safe=False)


@login_required
@require_GET
def api_client_trips(request):
    client_id = request.GET.get("client_id", "").strip()
    if not client_id:
        return JsonResponse([], safe=False)
    with suppress(ValueError, TypeError):
        trips = Trip.objects.filter(
            clients__id=int(client_id)
        ).select_related(
            "destination_country", "visa_type"
        ).order_by("-planned_departure_date").distinct()
        data = [
            {
                "id": t.pk,
                "label": (
                    f"{t.destination_country.name} - "
                    f"{t.visa_type.name if t.visa_type else 'Sem visto'} - "
                    f"{t.planned_departure_date.strftime('%d/%m/%Y') if t.planned_departure_date else 'Sem data'}"
                ),
            }
            for t in trips
        ]
        return JsonResponse(data, safe=False)
    return JsonResponse([], safe=False)


@login_required
def list_trip_forms(request, trip_id: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    trip = get_object_or_404(
        Trip.objects.select_related(
            "destination_country", "visa_type__form", "assigned_advisor"
        ),
        pk=trip_id,
    )

    clients_with_info = []
    for client in trip.clients.all():
        client_visa_type = _get_client_visa_type(trip, client)
        form_obj = _get_form_by_visa_type(client_visa_type, active_only=False)

        has_answer = False
        total_questions = 0
        total_answers = 0

        if form_obj and form_obj.is_active:
            questions = form_obj.questions.filter(is_active=True)
            total_questions = questions.count()
            if total_questions > 0:
                answers = FormAnswer.objects.filter(trip=trip, client=client)
                total_answers = answers.count()
                has_answer = total_answers > 0

        clients_with_info.append({
            "client": client,
            "visa_type": client_visa_type,
            "visa_form_obj": form_obj,
            "has_answer": has_answer,
            "total_questions": total_questions,
            "total_answers": total_answers,
            "complete": (
                has_answer and total_answers == total_questions
                if total_questions > 0 else False
            ),
        })

    context = {
        "trip": trip,
        "clients_with_info": clients_with_info,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
    }

    return render(request, "travel/list_trip_forms.html", context)


@login_required
def edit_client_form(request, trip_id: int, client_id: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    trip = get_object_or_404(
        Trip.objects.select_related("visa_type__form"),
        pk=trip_id,
    )

    if not can_manage_all and (
        not consultant or trip.assigned_advisor_id != consultant.pk
    ):
        raise PermissionDenied("Você não tem permissão para acessar esta viagem.")

    client = get_object_or_404(ConsultancyClient, pk=client_id)

    if client not in trip.clients.all():
        raise PermissionDenied("Este cliente não está vinculado a esta viagem.")

    stage_token = request.GET.get("stage")
    (
        form_obj, all_questions, existing_answers,
        stage_items, current_stage, questions,
    ) = _get_form_data(trip, client, stage_token)

    if not form_obj:
        messages.warning(
            request,
            "Este tipo de visto não possui um formulário cadastrado ou o formulário está inativo.",
        )
        return redirect("system:list_trip_forms", trip_id=trip_id)

    trip_client_link = TripClient.objects.select_related("trip_primary_client").filter(
        trip=trip,
        client=client,
    ).first()
    is_trip_dependent = bool(trip_client_link and trip_client_link.role == "dependent")
    trip_primary_client = (
        trip_client_link.trip_primary_client
        if trip_client_link and trip_client_link.role == "dependent"
        else None
    )

    if request.method == "POST":
        if request.POST.get("action") == "replicate_primary":
            copied, skipped, primary_client = _copy_form_answers_from_primary_client(
                trip,
                client,
                form_obj,
            )
            if primary_client is None:
                messages.error(
                    request,
                    "Não foi possível replicar: este cliente não está como dependente com principal definido na viagem.",
                )
            elif copied == 0 and skipped == 0:
                messages.info(
                    request,
                    f"O cliente principal {primary_client.full_name} ainda não possui respostas para replicar.",
                )
            else:
                messages.success(
                    request,
                    f"Replicação concluída a partir de {primary_client.full_name}: {copied} campo(s) preenchido(s) e {skipped} preservado(s).",
                )

            stage_param = (
                f"?stage={current_stage['token'].replace(':', '%3A')}"
                if current_stage
                else ""
            )
            return redirect(
                f"{reverse('system:edit_client_form', args=[trip_id, client_id])}{stage_param}"
            )

        saved_answers, errors = _process_form_answers(
            request, trip, client, questions, existing_answers
        )

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            messages.success(
                request,
                f"Etapa '{current_stage['name'] if current_stage else 'Atual'}' salva com sucesso!",
            )
            next_action = request.POST.get("next_action")
            if next_action == "next" and current_stage:
                next_stage = _find_next_stage(stage_items, current_stage)
                if next_stage:
                    return redirect(
                        f"{reverse('system:edit_client_form', args=[trip_id, client_id])}"
                        f"?stage={next_stage['token'].replace(':', '%3A')}"
                    )
                return redirect("system:list_trip_forms", trip_id=trip_id)
            elif next_action == "finish":
                return redirect("system:list_trip_forms", trip_id=trip_id)
            else:
                stage_param = (
                    f"?stage={current_stage['token'].replace(':', '%3A')}"
                    if current_stage else ""
                )
                return redirect(
                    f"{reverse('system:edit_client_form', args=[trip_id, client_id])}"
                    f"{stage_param}"
                )

    client_visa_type = _get_client_visa_type(trip, client)

    stage_index = _find_stage_index(stage_items, current_stage)
    next_stage = stage_items[stage_index + 1] if stage_index + 1 < len(stage_items) else None
    prev_stage = stage_items[stage_index - 1] if stage_index > 0 else None

    context = {
        "trip": trip,
        "client": client,
        "client_visa_type": client_visa_type,
        "visa_form_obj": form_obj,
        "questions": questions,
        "all_questions": all_questions,
        "existing_answers": existing_answers,
        "answer_ids": list(existing_answers.keys()),
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "stage_items": stage_items,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "prev_stage": prev_stage,
        "stage_index": stage_index,
        "is_trip_dependent": is_trip_dependent,
        "trip_primary_client": trip_primary_client,
    }

    return render(request, "travel/edit_client_form.html", context)


def _find_stage_index(stage_items, current_stage):
    if current_stage and stage_items:
        for i, item in enumerate(stage_items):
            if item["token"] == current_stage["token"]:
                return i
    return 0


def _find_next_stage(stage_items, current_stage):
    for i, item in enumerate(stage_items):
        if item["token"] == current_stage["token"] and i + 1 < len(stage_items):
            return stage_items[i + 1]
    return None


def _form_answer_is_empty(answer):
    return (
        not answer.answer_text
        and answer.answer_date is None
        and answer.answer_number is None
        and answer.answer_boolean is None
        and answer.answer_select_id is None
    )


def _question_can_replicate_from_primary(question):
    if question.stage_id and question.stage and question.stage.order == 1:
        return False
    return not should_prefill_from_client(question.question)


def _copy_form_answers_from_primary_client(trip, target_client, form_obj):
    trip_client = TripClient.objects.select_related("trip_primary_client").filter(
        trip=trip,
        client=target_client,
    ).first()
    if not trip_client or trip_client.role != "dependent" or not trip_client.trip_primary_client:
        return 0, 0, None

    primary_client = trip_client.trip_primary_client
    questions = list(
        form_obj.questions.filter(is_active=True)
        .select_related("stage")
        .order_by("order")
    )
    question_ids = [
        question.pk
        for question in questions
        if _question_can_replicate_from_primary(question)
    ]

    source_answers = FormAnswer.objects.filter(
        trip=trip,
        client=primary_client,
        question_id__in=question_ids,
    ).order_by("question_id")
    target_answers = {
        answer.question_id: answer
        for answer in FormAnswer.objects.filter(
            trip=trip,
            client=target_client,
            question_id__in=question_ids,
        )
    }

    copied = 0
    skipped = 0
    for source in source_answers:
        target = target_answers.get(source.question_id)
        if target and not _form_answer_is_empty(target):
            skipped += 1
            continue

        if target is None:
            target = FormAnswer(
                trip=trip,
                client=target_client,
                question_id=source.question_id,
            )
            target_answers[source.question_id] = target

        target.answer_text = source.answer_text
        target.answer_date = source.answer_date
        target.answer_number = source.answer_number
        target.answer_boolean = source.answer_boolean
        target.answer_select = source.answer_select
        target.save()
        copied += 1

    return copied, skipped, primary_client


@login_required
def view_client_form(request, trip_id: int, client_id: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    trip = get_object_or_404(
        Trip.objects.select_related(
            "visa_type__form", "destination_country", "assigned_advisor"
        ),
        pk=trip_id,
    )

    client = get_object_or_404(ConsultancyClient, pk=client_id)

    if client not in trip.clients.all():
        raise PermissionDenied("Este cliente não está vinculado a esta viagem.")

    stage_token = request.GET.get("stage")
    (
        form_obj, all_questions, existing_answers,
        stage_items, current_stage, questions,
    ) = _get_form_data(trip, client, stage_token)

    if not form_obj:
        messages.warning(
            request,
            "Este tipo de visto não possui um formulário cadastrado ou o formulário está inativo.",
        )
        return redirect("system:list_trip_forms", trip_id=trip_id)

    client_visa_type = _get_client_visa_type(trip, client)

    stage_index = _find_stage_index(stage_items, current_stage)
    next_stage = stage_items[stage_index + 1] if stage_index + 1 < len(stage_items) else None
    prev_stage = stage_items[stage_index - 1] if stage_index > 0 else None

    context = {
        "trip": trip,
        "client": client,
        "client_visa_type": client_visa_type,
        "visa_form_obj": form_obj,
        "questions": questions,
        "all_questions": all_questions,
        "existing_answers": existing_answers,
        "answer_ids": list(existing_answers.keys()),
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "stage_items": stage_items,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "prev_stage": prev_stage,
        "stage_index": stage_index,
    }

    return render(request, "travel/view_client_form.html", context)


@login_required
@require_http_methods(["POST"])
def delete_form_answers(request, trip_id: int, client_id: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    trip = get_object_or_404(
        Trip.objects.select_related("assigned_advisor"),
        pk=trip_id,
    )

    if not can_manage_all:
        raise PermissionDenied("Apenas administradores podem excluir respostas de formulários.")

    client = get_object_or_404(ConsultancyClient, pk=client_id)

    if client not in trip.clients.all():
        raise PermissionDenied("Este cliente não está vinculado a esta viagem.")

    deleted_count = FormAnswer.objects.filter(
        trip=trip, client=client
    ).delete()[0]

    messages.success(
        request,
        f"Todas as respostas do formulário do cliente {client.full_name} "
        f"foram excluídas com sucesso. ({deleted_count} resposta(s) removida(s))",
    )

    return redirect("system:list_trip_forms", trip_id=trip_id)


@login_required
@require_http_methods(["POST"])
def switch_trip_principal(request, pk: int, client_id: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    trip = get_object_or_404(Trip, pk=pk)

    if not can_manage_all and (
        not consultant or trip.assigned_advisor_id != consultant.pk
    ):
        raise PermissionDenied

    new_primary = get_object_or_404(ConsultancyClient, pk=client_id)

    tc_new = TripClient.objects.filter(trip=trip, client=new_primary).first()
    if not tc_new:
        messages.error(request, "Cliente não está vinculado a esta viagem.")
        return redirect("system:view_trip", pk=pk)

    if tc_new.role == "primary":
        messages.info(
            request,
            f"{new_primary.first_name} já é o principal desta viagem.",
        )
        return redirect("system:view_trip", pk=pk)

    with transaction.atomic():
        tc_old_primary = TripClient.objects.filter(
            trip=trip, role="primary"
        ).select_related("client").first()

        if tc_old_primary:
            old_primary = tc_old_primary.client

            tc_old_primary.role = "dependent"
            tc_old_primary.trip_primary_client = new_primary
            tc_old_primary.save(
                update_fields=["role", "trip_primary_client", "updated_at"]
            )

            try:
                fin_old = FinancialRecord.objects.select_for_update().get(
                    trip=trip, client=old_primary
                )
                fin_new, created = FinancialRecord.objects.select_for_update().get_or_create(
                    trip=trip,
                    client=new_primary,
                    defaults={
                        "assigned_advisor": trip.assigned_advisor,
                        "amount": fin_old.amount,
                        "status": fin_old.status,
                        "created_by": trip.created_by,
                    },
                )
                if not created:
                    fin_new.amount = fin_old.amount
                    fin_new.status = fin_old.status
                    if fin_old.payment_date:
                        fin_new.payment_date = fin_old.payment_date
                    fin_new.save(
                        update_fields=["amount", "status", "payment_date", "updated_at"]
                    )

                fin_old.amount = 0
                fin_old.save(update_fields=["amount", "updated_at"])

                logger.info(
                    "Financeiro transferido: viagem pk=%s, de '%s' (pk=%s) para '%s' (pk=%s)",
                    trip.pk, old_primary.first_name, old_primary.pk,
                    new_primary.first_name, new_primary.pk,
                )
            except FinancialRecord.DoesNotExist:
                pass

        tc_new.role = "primary"
        tc_new.trip_primary_client = None
        tc_new.save(update_fields=["role", "trip_primary_client", "updated_at"])

        TripClient.objects.filter(
            trip=trip, role="dependent"
        ).update(trip_primary_client=new_primary)

    messages.success(
        request,
        f"{new_primary.first_name} agora é o cliente principal desta viagem.",
    )
    return redirect("system:view_trip", pk=pk)
