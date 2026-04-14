import logging
from contextlib import suppress
from datetime import timedelta

from django.contrib import messages
from django.utils.dateparse import parse_date
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from system.forms import ProcessForm
from system.forms.process_forms import get_available_statuses_for_trip
from system.models import (
    ConsultancyClient,
    TripClient,
    ProcessStage,
    Process,
    ProcessStatus,
    Trip,
)
from system.models import ConsultancyUser
from system.views.client_views import list_clients, get_user_consultant, user_can_manage_all


logger = logging.getLogger(__name__)


def _apply_process_filters(processes, request, include_advisor=True):
    filters = {
        "client": request.GET.get("client", "").strip(),
        "trip": request.GET.get("trip", "").strip(),
    }
    if include_advisor:
        filters["advisor"] = request.GET.get("advisor", "").strip()

    if filters["client"]:
        processes = processes.filter(client__first_name__icontains=filters["client"])
    if filters["trip"]:
        processes = processes.filter(
            Q(trip__destination_country__name__icontains=filters["trip"])
            | Q(trip__visa_type__name__icontains=filters["trip"])
        )
    if include_advisor and filters.get("advisor"):
        with suppress(ValueError, TypeError):
            processes = processes.filter(assigned_advisor_id=int(filters["advisor"]))

    return processes, filters


def _sort_processes_by_family_group(processes, trip=None):
    if trip:
        trip_client_map = {
            cv.client_id: cv.role
            for cv in TripClient.objects.filter(trip=trip)
        }
        return sorted(
            processes,
            key=lambda p: (0 if trip_client_map.get(p.client_id) == "primary" else 1, p.client.full_name, p.pk),
        )
    return sorted(processes, key=lambda p: (p.client.full_name, p.pk))


@login_required
def home_processes(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    from system.views.client_views import list_clients
    user_clients = list_clients(request.user)
    client_ids = list(user_clients.values_list("pk", flat=True))

    processes = Process.objects.filter(
        client__pk__in=client_ids
    ).select_related(
        "trip",
        "trip__destination_country",
        "trip__visa_type",
        "client",
        "assigned_advisor",
    ).prefetch_related("stages", "stages__status").distinct()

    processes, applied_filters = _apply_process_filters(processes, request, include_advisor=False)

    sorted_processes = _sort_processes_by_family_group(processes)

    limited_processes = sorted_processes[:10]
    total_completed_processes = sum(1 for p in sorted_processes if p.progress_percentage >= 100)
    total_pending_processes = sum(1 for p in sorted_processes if p.progress_percentage < 100)

    context = {
        "processes": limited_processes,
        "total_processes": processes.count(),
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "consultant": consultant,
        "clients": user_clients.order_by("first_name"),
        "applied_filters": applied_filters,
        "total_completed_processes": total_completed_processes,
        "total_pending_processes": total_pending_processes,
    }

    return render(request, "process/home_processes.html", context)


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


def _clear_trip_session_messages(request):
    if stored_messages := request.session.get('_messages'):
        filtered = [
            msg for msg in stored_messages
            if "viagens cadastradas" not in str(msg.get('message', '') if isinstance(msg, dict) else msg).lower()
            and "viagem cadastrada" not in str(msg.get('message', '') if isinstance(msg, dict) else msg).lower()
        ]
        if filtered:
            request.session['_messages'] = filtered
        else:
            request.session.pop('_messages', None)
        request.session.modified = True

    storage = messages.get_messages(request)
    storage.used = True


def _update_process_stages(process: Process, request, stage_id: int | None = None) -> int:
    stages_updated = 0

    if stage_id:
        try:
            stage = process.stages.get(pk=stage_id)
            prev_deadline = stage.deadline_days
            stage_id_str = str(stage.pk)

            completed_val_bool = request.POST.get(f"stage_{stage_id_str}_completed_val_bool") == "on"
            deadline_days_str = request.POST.get(f"stage_{stage_id_str}_deadline", "").strip()
            completion_date_str = request.POST.get(f"stage_{stage_id_str}_date", "").strip() or None
            notes = request.POST.get(f"stage_{stage_id_str}_notes", "").strip()

            stage.completed = completed_val_bool
            stage.notes = notes or ""

            if deadline_days_str:
                try:
                    stage.deadline_days = int(deadline_days_str)
                except ValueError:
                    messages.error(request, "Prazo (dias) inválido. Informe um número inteiro >= 0.")
                    stage.deadline_days = prev_deadline
                    return 0
            else:
                stage.deadline_days = 0

            if completion_date_str:
                try:
                    stage.completion_date = parse_date(completion_date_str)
                except (ValueError, TypeError):
                    stage.completion_date = None
            else:
                if not completed_val_bool:
                    stage.completion_date = None

            stage.save(update_fields=["completed", "deadline_days", "completion_date", "notes", "updated_at"])

            stage.refresh_from_db()
            stages_updated = 1
        except ProcessStage.DoesNotExist:
            logger.warning(f"Etapa {stage_id} não encontrada no processo {process.pk}")
            return 0
        except Exception as e:
            logger.error(f"Erro ao atualizar etapa {stage_id}: {e}", exc_info=True)
            return 0
    else:
        process_stages_list = list(process.stages.all())
        logger.debug("Processando %s etapa(s) do processo %s", len(process_stages_list), process.pk)

        for stage in process_stages_list:
            stage_id_str = str(stage.pk)

            completed_val = request.POST.get(f"stage_{stage_id_str}_completed_val_bool", "")
            completed_val_bool = completed_val == "on"
            deadline_str = request.POST.get(f"stage_{stage_id_str}_deadline", "").strip()
            completion_date_str = request.POST.get(f"stage_{stage_id_str}_date", "").strip() or None
            notes = request.POST.get(f"stage_{stage_id_str}_notes", "").strip()

            was_completed = stage.completed
            prev_deadline = stage.deadline_days
            prev_completion_date = stage.completion_date
            prev_notes = stage.notes

            stage.completed = completed_val_bool
            stage.notes = notes or ""

            try:
                if deadline_str:
                    stage.deadline_days = int(deadline_str)
                else:
                    stage.deadline_days = 0
            except ValueError:
                messages.error(request, "Prazo (dias) inválido. Informe um número inteiro >= 0.")
                stage.deadline_days = prev_deadline
                continue

            if completion_date_str:
                try:
                    stage.completion_date = parse_date(completion_date_str)
                except (ValueError, TypeError):
                    stage.completion_date = None
            else:
                if not completed_val_bool:
                    stage.completion_date = None

            has_changed = (
                stage.completed != was_completed or
                stage.deadline_days != prev_deadline or
                stage.completion_date != prev_completion_date or
                stage.notes != prev_notes
            )

            fields_present = any([
                f"stage_{stage_id_str}_completed_val_bool" in request.POST,
                f"stage_{stage_id_str}_deadline" in request.POST,
                f"stage_{stage_id_str}_date" in request.POST,
                f"stage_{stage_id_str}_notes" in request.POST,
            ])

            if has_changed or fields_present:
                try:
                    stage.save(update_fields=["completed", "deadline_days", "completion_date", "notes", "updated_at"])
                    stage.refresh_from_db()
                    stages_updated += 1
                    logger.debug(
                        "Etapa %s (%s) salva - completed_val_bool=%s prazo=%s data=%s",
                        stage_id_str,
                        stage.status.name,
                        completed_val_bool,
                        stage.deadline_days,
                        stage.completion_date,
                    )
                except Exception as e:
                    logger.error(f"Erro ao salvar etapa {stage_id_str}: {e}", exc_info=True)

    return stages_updated


def _create_stages_if_needed(process: Process):
    if process.stages.exists():
        return

    for status in get_available_statuses_for_trip(process.trip_id):
        deadline = max(status.default_deadline_days, 0)

        ProcessStage.objects.get_or_create(
            process=process,
            status=status,
            defaults={
                'deadline_days': deadline,
                'order': status.order,
            }
        )


def _calculate_stage_completion_dates(process: Process, stages):
    base_date = process.client.created_at.date()
    stages_with_dates = []
    for stage in stages:
        completion_date = None
        if stage.deadline_days and stage.deadline_days > 0:
            completion_date = base_date + timedelta(days=stage.deadline_days)

        stages_with_dates.append({
            'stage': stage,
            'completion_date': completion_date,
        })
    return stages_with_dates


def _get_next_client_same_trip(trip: Trip, current_client: ConsultancyClient) -> dict | None:
    trip_clients = trip.clients.all()
    related_client_ids = set(trip_clients.values_list('pk', flat=True))
    trips_with_clients = TripClient.objects.filter(
        client_id__in=related_client_ids
    ).values_list("trip_id", flat=True).distinct()
    related_client_ids.update(
        TripClient.objects.filter(trip_id__in=trips_with_clients).values_list("client_id", flat=True)
    )

    related_client_ids.discard(current_client.pk)

    if not related_client_ids:
        return None

    for client_id in related_client_ids:
        related_client = ConsultancyClient.objects.get(pk=client_id)
        existing_process = Process.objects.filter(
            trip=trip,
            client=related_client
        ).exists()

        if not existing_process:
            return {
                'client_id': related_client.pk,
                'trip_id': trip.pk,
            }

    return None


def _get_next_client_separate_trip(client: ConsultancyClient, current_trip: Trip) -> dict | None:
    related_client_ids = {client.pk}
    client_trips = TripClient.objects.filter(
        client=client
    ).values_list("trip_id", flat=True).distinct()
    related_client_ids.update(
        TripClient.objects.filter(trip_id__in=client_trips).values_list("client_id", flat=True)
    )

    related_client_ids.discard(client.pk)

    if not related_client_ids:
        return None

    related_trips = Trip.objects.filter(
        clients__pk__in=related_client_ids
    ).distinct().exclude(pk=current_trip.pk)

    for related_trip in related_trips:
        related_trip_clients = related_trip.clients.filter(
            pk__in=related_client_ids
        )

        for related_client in related_trip_clients:
            existing_process = Process.objects.filter(
                trip=related_trip,
                client=related_client
            ).exists()

            if not existing_process:
                return {
                    'client_id': related_client.pk,
                    'trip_id': related_trip.pk,
                }

    return None


def _redirect_to_next_client(request, process: Process, next_client_info: dict, specific_message: str = None) -> HttpResponseRedirect:
    try:
        next_client = ConsultancyClient.objects.get(pk=next_client_info['client_id'])
        msg = specific_message or f"Processo criado para {process.client.full_name}. Criando processo para {next_client.full_name}..."
    except ConsultancyClient.DoesNotExist:
        msg = f"Processo criado para {process.client.full_name}. Criando próximo processo..."

    messages.info(request, msg)
    return redirect(
        f"{reverse('system:create_process')}?client_id={next_client_info['client_id']}&trip_id={next_client_info['trip_id']}"
    )


def _process_next_client(request, process: Process) -> HttpResponseRedirect | None:
    if same_trip_info := _get_next_client_same_trip(process.trip, process.client):
        return _redirect_to_next_client(request, process, same_trip_info)

    if separate_trip_info := _get_next_client_separate_trip(process.client, process.trip):
        msg = f"Processo criado para {process.client.full_name}. Criando processo em viagem separada..."
        return _redirect_to_next_client(request, process, separate_trip_info, msg)

    return None


def _process_create_post(request, client_id, trip_id) -> HttpResponseRedirect | None:
    _clear_duplicate_session_messages(request)
    storage = messages.get_messages(request)
    storage.used = True

    form = ProcessForm(request.POST, user=request.user, client_id=client_id, trip_id=trip_id)
    if not form.is_valid():
        messages.error(request, "Não foi possível cadastrar o processo. Verifique os campos.")
        return None

    process = form.save()

    if redirect_response := _process_next_client(request, process):
        return redirect_response

    messages.success(request, f"Todos os processos foram criados com sucesso! Processo criado para {process.client.full_name}.")
    return redirect("system:home_processes")


def _determine_preselected_client(client_id, trip_id) -> bool:
    if client_id:
        return True

    if not trip_id:
        return False

    with suppress(Trip.DoesNotExist):
        trip = Trip.objects.get(pk=trip_id)
        return trip.clients.count() == 1

    return False


def _resolve_client_id_for_trip(client_id, trip_id):
    if client_id or not trip_id:
        return client_id

    with suppress(ValueError, TypeError):
        trip_id_int = int(trip_id)
        primary_client_id = TripClient.objects.filter(
            trip_id=trip_id_int,
            role="primary",
        ).values_list("client_id", flat=True).first()
        if primary_client_id:
            return str(primary_client_id)

        first_client_id = Trip.objects.filter(pk=trip_id_int).values_list(
            "clients__pk", flat=True
        ).first()
        if first_client_id:
            return str(first_client_id)

    return client_id


def _get_available_trip_stages(trip_id) -> list:
    if not trip_id:
        return []

    return get_available_statuses_for_trip(trip_id)


def _prepare_create_process_context(consultant, form, client_id, trip_id) -> dict:
    available_stages = _get_available_trip_stages(trip_id) if trip_id else []

    return {
        "form": form,
        "user_profile": consultant.profile.name if consultant else None,
        "preselected_client": _determine_preselected_client(client_id, trip_id),
        "preselected_trip": bool(trip_id),
        "available_stages": available_stages,
    }


@login_required
def create_process(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if request.method == "GET":
        _clear_trip_session_messages(request)

    client_id = request.GET.get("client_id")
    trip_id = request.GET.get("trip_id")
    client_id = _resolve_client_id_for_trip(client_id, trip_id)

    if request.method == "POST":
        if redirect_response := _process_create_post(request, client_id, trip_id):
            return redirect_response
        form = ProcessForm(request.POST, user=request.user, client_id=client_id, trip_id=trip_id)
    else:
        form = ProcessForm(user=request.user, client_id=client_id, trip_id=trip_id)

    context = _prepare_create_process_context(consultant, form, client_id, trip_id)
    return render(request, "process/create_process.html", context)


@login_required
def view_process(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    process = get_object_or_404(
        Process.objects.select_related(
            "trip",
            "trip__destination_country",
            "trip__visa_type",
            "client",
            "assigned_advisor",
        ).prefetch_related("stages", "stages__status"),
        pk=pk
    )

    pode_visualizar = True

    stages = process.stages.select_related("status").order_by("order", "status__name").all()

    stages_with_dates = _calculate_stage_completion_dates(process, stages)
    base_date = process.client.created_at.date()

    context = {
        "process_obj": process,
        "stages_with_dates": stages_with_dates,
        "base_date": base_date,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "can_edit": can_manage_all or (consultant and process.assigned_advisor_id == consultant.pk),
    }

    return render(request, "process/view_process.html", context)


@login_required
def edit_process(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    process = get_object_or_404(
        Process.objects.select_related(
            "trip",
            "trip__destination_country",
            "trip__visa_type",
            "client",
            "assigned_advisor",
        ).prefetch_related("stages", "stages__status"),
        pk=pk
    )

    if not can_manage_all and (not consultant or process.assigned_advisor_id != consultant.pk):
        raise PermissionDenied("Você não tem permissão para editar este processo.")

    if request.method == "POST":
        logger.debug("POST edit_process %s com campos: %s", process.pk, list(request.POST.keys()))

        if "change_advisor" in request.POST:
            if can_manage_all:
                try:
                    new_advisor_id = int(request.POST.get("assigned_advisor"))
                    new_advisor = ConsultancyUser.objects.get(pk=new_advisor_id, is_active=True)
                    process.assigned_advisor = new_advisor
                    process.save(update_fields=["assigned_advisor"])
                    messages.success(request, f"Assessor responsável alterado para {new_advisor.name}.")
                except (ValueError, TypeError, ConsultancyUser.DoesNotExist):
                    messages.error(request, "Erro ao alterar o assessor responsável. Verifique os dados.")
            else:
                messages.error(request, "Você não tem permissão para alterar o assessor responsável.")
            return redirect("system:edit_process", pk=process.pk)

        if "save_stage" in request.POST:
            try:
                stage_id = int(request.POST.get("save_stage"))
                if not process.stages.filter(pk=stage_id).exists():
                    messages.error(request, f"Etapa {stage_id} não encontrada no processo.")
                else:
                    stages_updated = _update_process_stages(process, request, stage_id=stage_id)
                    if stages_updated > 0:
                        messages.success(request, "Etapa salva com sucesso.")
                    else:
                        messages.error(request, "Erro ao salvar a etapa. Verifique se os dados foram preenchidos corretamente.")
            except (ValueError, TypeError) as e:
                messages.error(request, f"Erro ao processar a solicitação: {str(e)}")
            except Exception as e:
                logger.error(f"Erro ao salvar etapa: {e}", exc_info=True)
                messages.error(request, f"Erro ao salvar a etapa: {str(e)}")
            return redirect("system:edit_process", pk=process.pk)

        if "salvar_tudo" in request.POST:
            try:
                post_keys = [k for k in request.POST.keys() if k.startswith('stage_')]
                logger.info(f"Salvando todas as etapas. POST com {len(post_keys)} campos de etapa.")
                stages_updated = _update_process_stages(process, request)

                if stages_updated > 0:
                    messages.success(request, f"{stages_updated} etapa(s) atualizada(s) com sucesso.")
                else:
                    messages.warning(request, "Nenhuma etapa foi atualizada. Verifique se há etapas no processo e se os dados foram preenchidos.")
            except Exception as e:
                logger.error(f"Erro ao salvar todas as etapas: {e}", exc_info=True)
                messages.error(request, f"Erro ao salvar as etapas: {str(e)}")
            return redirect("system:edit_process", pk=process.pk)

    stages = process.stages.select_related("status").order_by("order", "status__name").all()

    _create_stages_if_needed(process)

    stages = process.stages.select_related("status").order_by("order", "status__name").all()

    stages_with_dates = _calculate_stage_completion_dates(process, stages)
    base_date = process.client.created_at.date()

    available_stages = _get_available_stages_to_add(process)

    available_advisors = ConsultancyUser.objects.filter(is_active=True).order_by("name")

    context = {
        "process_obj": process,
        "stages_with_dates": stages_with_dates,
        "base_date": base_date,
        "available_stages": available_stages,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "available_advisors": available_advisors,
    }

    return render(request, "process/edit_process.html", context)


@login_required
@require_http_methods(["POST"])
def delete_process(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied("Você não tem permissão para excluir processos.")

    process = get_object_or_404(Process, pk=pk)
    client_name = process.client.full_name
    process.delete()

    messages.success(request, f"Processo de {client_name} excluído com sucesso.")
    return redirect("system:list_processes")


@login_required
@require_http_methods(["POST"])
def remove_process_stage(request, process_pk: int, stage_pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    process = get_object_or_404(
        Process.objects.select_related("assigned_advisor"),
        pk=process_pk
    )

    if not can_manage_all and (not consultant or process.assigned_advisor_id != consultant.pk):
        raise PermissionDenied("Você não tem permissão para remover etapas deste processo.")

    stage = get_object_or_404(
        ProcessStage.objects.filter(process=process),
        pk=stage_pk
    )

    stage_name = stage.status.name
    stage.delete()

    messages.success(request, f"Etapa '{stage_name}' removida do processo com sucesso.")
    return redirect("system:edit_process", pk=process.pk)


def _get_available_stages_to_add(process: Process):
    status_ids_existentes = set(
        process.stages.values_list('status_id', flat=True)
    )

    return [
        status
        for status in get_available_statuses_for_trip(process.trip_id)
        if status.pk not in status_ids_existentes
    ]


@login_required
@require_http_methods(["POST"])
def add_process_stage(request, process_pk: int, status_pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    process = get_object_or_404(
        Process.objects.select_related("assigned_advisor", "trip"),
        pk=process_pk
    )

    if not can_manage_all and (not consultant or process.assigned_advisor_id != consultant.pk):
        raise PermissionDenied("Você não tem permissão para adicionar etapas a este processo.")

    status = next(
        (
            available_status
            for available_status in get_available_statuses_for_trip(process.trip_id)
            if available_status.pk == status_pk
        ),
        None,
    )

    if status is None:
        messages.error(request, "Etapa indisponível para esta viagem.")
        return redirect("system:edit_process", pk=process.pk)

    if ProcessStage.objects.filter(process=process, status=status).exists():
        messages.error(request, f"Etapa '{status.name}' já existe neste processo.")
        return redirect("system:edit_process", pk=process.pk)

    deadline = max(status.default_deadline_days or 0, 0)

    ProcessStage.objects.create(
        process=process,
        status=status,
        deadline_days=deadline,
        order=status.order,
    )

    messages.success(request, f"Etapa '{status.name}' adicionada ao processo com sucesso.")
    return redirect("system:edit_process", pk=process.pk)


@login_required
def list_processes(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    processes = Process.objects.select_related(
        "trip",
        "trip__destination_country",
        "trip__visa_type",
        "client",
        "assigned_advisor",
    ).prefetch_related("stages", "stages__status").distinct()

    processes, applied_filters = _apply_process_filters(processes, request, include_advisor=True)

    sorted_processes = _sort_processes_by_family_group(processes)
    total_completed_processes = sum(1 for p in sorted_processes if p.progress_percentage >= 100)
    total_pending_processes = sum(1 for p in sorted_processes if p.progress_percentage < 100)

    advisors = ConsultancyUser.objects.filter(is_active=True).order_by("name")
    clients = ConsultancyClient.objects.order_by("first_name")

    context = {
        "processes": sorted_processes,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "consultant": consultant,
        "applied_filters": applied_filters,
        "clients": clients,
        "advisors": advisors,
        "total_processes": len(sorted_processes),
        "total_completed_processes": total_completed_processes,
        "total_pending_processes": total_pending_processes,
    }

    return render(request, "process/list_processes.html", context)


@login_required
@require_GET
def api_process_status(request):
    trip_id = request.GET.get("trip_id")

    if not trip_id:
        return JsonResponse({"error": "ID da viagem não fornecido."}, status=400)

    try:
        status_list = [
            {
                "id": status.pk,
                "name": status.name,
                "default_deadline_days": status.default_deadline_days,
                "ordem": status.order,
            }
            for status in get_available_statuses_for_trip(trip_id)
        ]

        return JsonResponse(status_list, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_GET
def api_client_info(request):
    client_id = request.GET.get("client_id")

    if not client_id:
        return JsonResponse({"error": "ID do cliente não fornecido."}, status=400)

    try:
        client = ConsultancyClient.objects.get(pk=client_id)
        created_at = client.created_at.isoformat()
        return JsonResponse({"created_at": created_at})
    except ConsultancyClient.DoesNotExist:
        return JsonResponse({"error": "Cliente não encontrado."}, status=404)


@login_required
@require_GET
def api_process_status_deadline(request):
    status_id = request.GET.get("status_id")

    if not status_id:
        return JsonResponse({"error": "ID do status não fornecido."}, status=400)

    try:
        status = ProcessStatus.objects.get(pk=status_id, is_active=True)
        return JsonResponse({
            "default_deadline_days": status.default_deadline_days,
        })
    except ProcessStatus.DoesNotExist:
        return JsonResponse({"error": "Status não encontrado."}, status=404)


@login_required
@require_GET
def api_trip_clients(request):
    trip_id = request.GET.get("trip_id")

    if not trip_id:
        return JsonResponse({"error": "ID da viagem não fornecido."}, status=400)

    try:
        trip = Trip.objects.get(pk=trip_id)
        trip_clients_qs = TripClient.objects.filter(
            trip=trip
        ).select_related("client")

        client_ids = set(trip_clients_qs.values_list("client_id", flat=True))
        related_trips = TripClient.objects.filter(
            client_id__in=client_ids
        ).values_list("trip_id", flat=True).distinct()
        client_ids.update(
            TripClient.objects.filter(trip_id__in=related_trips).values_list("client_id", flat=True)
        )

        trip_client_map = {cv.client_id: cv.role for cv in trip_clients_qs}
        clients = ConsultancyClient.objects.filter(pk__in=client_ids).order_by("first_name")

        sorted_clients = sorted(
            clients,
            key=lambda c: (0 if trip_client_map.get(c.pk) == "primary" else 1, c.full_name),
        )

        clients_list = [
            {
                "id": client.pk,
                "name": client.full_name,
                "is_principal": trip_client_map.get(client.pk) == "primary",
            }
            for client in sorted_clients
        ]

        return JsonResponse(clients_list, safe=False)
    except Trip.DoesNotExist:
        return JsonResponse({"error": "Viagem não encontrada."}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
