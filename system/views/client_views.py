import json
import logging
import re
from contextlib import suppress
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.db.models import Count, Q, QuerySet
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from system.forms import ConsultancyClientForm
from system.models import (
    ClientRegistrationStep,
    ClientStepField,
    ConsultancyClient,
    FormAnswer,
    Process,
    Reminder,
    Trip,
    TripClient,
    VisaForm,
)
from system.models.financial_models import FinancialRecord, FinancialStatus
from system.services.legacy_markers import extract_legacy_meta, strip_legacy_meta, upsert_legacy_meta
from system.services.cep import fetch_address_by_zip
from system.services.passport_ocr import PassportExtractionError, extract_passport_data_from_document
from system.models import ConsultancyUser

User = get_user_model()

logger = logging.getLogger(__name__)


CLIENT_STEP_FIELD_MAP = {
    "assessor_responsavel": "assigned_advisor",
    "nome": "first_name",
    "sobrenome": "last_name",
    "data_nascimento": "birth_date",
    "nacionalidade": "nationality",
    "telefone": "phone",
    "telefone_secundario": "secondary_phone",
    "senha": "password",
    "confirmar_senha": "confirm_password",
    "parceiro_indicador": "referring_partner",
    "cep": "zip_code",
    "logradouro": "street",
    "numero": "street_number",
    "complemento": "complement",
    "bairro": "district",
    "cidade": "city",
    "uf": "state",
    "tipo_passaporte": "passport_type",
    "tipo_passaporte_outro": "passport_type_other",
    "numero_passaporte": "passport_number",
    "pais_emissor_passaporte": "passport_issuing_country",
    "data_emissao_passaporte": "passport_issue_date",
    "valido_ate_passaporte": "passport_expiry_date",
    "autoridade_passaporte": "passport_authority",
    "cidade_emissao_passaporte": "passport_issuing_city",
    "passaporte_roubado": "passport_stolen",
    "observacoes": "notes",
}

CLIENT_STEP_BOOLEAN_MAP = {
    "etapa_dados_pessoais": "step_personal_data",
    "etapa_endereco": "step_address",
    "etapa_passaporte": "step_passport",
    "etapa_membros": "step_members",
}


def _client_step_form_field_name(field_name: str) -> str:
    return CLIENT_STEP_FIELD_MAP.get(field_name, field_name)


def _client_step_flag(boolean_field: str | None) -> str | None:
    if not boolean_field:
        return boolean_field
    return CLIENT_STEP_BOOLEAN_MAP.get(boolean_field, boolean_field)


class InvalidDependentsError(Exception):
    pass


def _sort_clients_by_family_group(clients):
    return sorted(clients, key=lambda c: (c.full_name, c.pk))


def _apply_client_filters(clients, request, include_advisor=False):
    filters = {
        "name": request.GET.get("name", "").strip(),
        "financial_status": request.GET.get("financial_status", "").strip(),
    }

    if include_advisor:
        filters["advisor"] = request.GET.get("advisor", "").strip()

    if filters["name"]:
        clients = clients.filter(first_name__icontains=filters["name"])
    if include_advisor and filters.get("advisor"):
        with suppress(ValueError, TypeError):
            clients = clients.filter(assigned_advisor_id=int(filters["advisor"]))
    if filters["financial_status"]:
        if filters["financial_status"] == "pendente":
            clients = clients.filter(financial_records__status=FinancialStatus.PENDING).distinct()
        elif filters["financial_status"] == "pago":
            clients = clients.filter(financial_records__status=FinancialStatus.PAID).distinct()
        elif filters["financial_status"] == "cancelado":
            clients = clients.filter(financial_records__status=FinancialStatus.CANCELLED).distinct()
        elif filters["financial_status"] == "sem_registros":
            clients = clients.annotate(
                total_registros=Count("financial_records")
            ).filter(total_registros=0)

    return clients, filters


def _get_client_financial_status(client: ConsultancyClient) -> str:
    records = FinancialRecord.objects.filter(client=client)
    if not records.exists():
        return "Sem registros"
    has_pending = records.filter(status=FinancialStatus.PENDING).exists()
    has_paid = records.filter(status=FinancialStatus.PAID).exists()
    has_cancelled = records.filter(status=FinancialStatus.CANCELLED).exists()
    return "Pendente" if has_pending else "Pago" if has_paid else "Cancelado" if has_cancelled else "Sem registros"


def _get_client_visa_type(trip, client):
    with suppress(TripClient.DoesNotExist):
        trip_client = TripClient.objects.select_related('visa_type__form').get(
            trip=trip, client=client
        )
        if trip_client.visa_type:
            return trip_client.visa_type
    return trip.visa_type


def _get_form_by_visa_type(visa_type, active_only=True):
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


def _get_client_form_status(client: ConsultancyClient) -> dict:
    trips = client.trips.select_related(
        'visa_type__form'
    ).prefetch_related(
        'visa_type__form__questions'
    ).order_by('-planned_departure_date')

    if not trips.exists():
        return {
            "status": "Sem formulário",
            "total_questions": 0,
            "total_answers": 0,
            "completo": False,
        }

    best_status = None
    best_info = None

    for trip in trips:
        client_visa_type = _get_client_visa_type(trip, client)

        if not client_visa_type:
            continue

        form = _get_form_by_visa_type(client_visa_type, active_only=True)

        if not form:
            continue

        total_questions = form.questions.filter(is_active=True).count()
        total_answers = FormAnswer.objects.filter(
            trip=trip,
            client=client
        ).count()

        complete = total_answers == total_questions if total_questions > 0 else False

        info = {
            "total_questions": total_questions,
            "total_answers": total_answers,
            "completo": complete,
        }

        if complete:
            status = "Completo"
        elif total_answers > 0:
            status = "Parcial"
        else:
            status = "Não preenchido"

        info["status"] = status

        if not best_info:
            best_info = info
            best_status = status
        elif status == "Completo" and best_status != "Completo":
            best_info = info
            best_status = status
        elif status == "Parcial" and best_status == "Não preenchido":
            best_info = info
            best_status = status

    if best_info:
        return best_info

    return {
        "status": "Sem formulário",
        "total_questions": 0,
        "total_answers": 0,
        "completo": False,
    }


def _legacy_meta_from_client(client: ConsultancyClient) -> dict:
    meta = extract_legacy_meta(client.notes)
    if not meta.get("imported"):
        return {"imported": False, "status": "", "issues": []}
    return {
        "imported": True,
        "status": meta.get("status", "ok"),
        "issues": meta.get("issues", []),
    }


def list_clients(user: User) -> QuerySet[ConsultancyClient]:
    queryset = ConsultancyClient.objects.select_related(
        "assigned_advisor",
        "created_by",
        "assigned_advisor__profile",
        "referring_partner",
    ).order_by("-created_at")

    if user.is_superuser or user.is_staff:
        return queryset

    consultant = get_user_consultant(user)

    if not consultant:
        return queryset.none()

    consultant_id = consultant.pk
    return queryset.filter(
        Q(assigned_advisor_id=consultant_id)
    ).distinct()


def _list_clients_full_scope(user: User) -> QuerySet[ConsultancyClient]:
    queryset = ConsultancyClient.objects.select_related(
        "assigned_advisor",
        "created_by",
        "assigned_advisor__profile",
        "referring_partner",
    ).order_by("-created_at")
    return queryset


def user_can_manage_all(user: User, consultant: ConsultancyUser | None) -> bool:
    if not consultant:
        return bool(user.is_superuser or user.is_staff)

    profile = consultant.profile
    is_admin_profile = (profile.name or "").strip().lower() == "administrador"
    has_full_crud = (
        profile.can_create
        and profile.can_view
        and profile.can_update
        and profile.can_delete
    )

    return (
        user.is_superuser
        or user.is_staff
        or is_admin_profile
        or has_full_crud
    )


def user_has_module_access(user: User, consultant: ConsultancyUser | None, module_name: str) -> bool:
    if user_can_manage_all(user, consultant):
        return True
    if not consultant:
        return False
    return consultant.profile.modules.filter(name=module_name).exists()


def user_can_edit_client(user: User, consultant: ConsultancyUser | None, client) -> bool:
    if user_can_manage_all(user, consultant):
        return True
    if consultant and getattr(client, "assigned_advisor_id", None) == consultant.pk:
        return True
    created_by_id = getattr(client, "created_by_id", None)
    return created_by_id is not None and created_by_id == getattr(user, "id", None)


def get_user_consultant(user: User) -> ConsultancyUser | None:
    if not user or not user.username:
        return None

    consultant = (
        ConsultancyUser.objects.select_related("profile")
        .filter(email__iexact=user.username.strip(), is_active=True)
        .first()
    )

    if not consultant and user.email:
        consultant = (
            ConsultancyUser.objects.select_related("profile")
            .filter(email__iexact=user.email.strip(), is_active=True)
            .first()
        )

    return consultant


@login_required
def delete_client(request, pk: int):
    if request.method != "POST":
        raise PermissionDenied

    client = get_object_or_404(
        ConsultancyClient.objects.select_related("assigned_advisor"),
        pk=pk,
    )

    consultant = get_user_consultant(request.user)

    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    client.delete()
    messages.success(request, f"{client.full_name} excluído com sucesso.")
    return redirect("system:list_clients_view")


@login_required
def home_clients(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    user_profile = consultant.profile.name if consultant and consultant.profile else ("Administrador" if request.user.is_superuser else None)

    base_qs = ConsultancyClient.objects.select_related(
        "assigned_advisor",
        "created_by",
        "assigned_advisor__profile",
        "referring_partner",
    ).prefetch_related("trips").order_by("-created_at")

    if can_manage_all:
        my_clients = list_clients(request.user)
    elif consultant:
        my_clients = base_qs.filter(
            Q(assigned_advisor=consultant)
        ).distinct()
    else:
        my_clients = base_qs.none()

    my_clients, filters = _apply_client_filters(my_clients, request, include_advisor=False)

    def _build_item(client):
        financial_status = _get_client_financial_status(client)
        form_status = _get_client_form_status(client)
        legacy_meta = _legacy_meta_from_client(client)
        return {
            "client": client,
            "financial_status": financial_status,
            "form_status": form_status["status"],
            "total_questions": form_status["total_questions"],
            "total_answers": form_status["total_answers"],
            "completo": form_status["completo"],
            "can_edit": user_can_edit_client(request.user, consultant, client),
            "legacy_meta": legacy_meta,
        }

    sorted_clients = _sort_clients_by_family_group(my_clients)
    clients_with_status = [_build_item(c) for c in sorted_clients]

    progress_list = []
    for c in my_clients:
        for proc in Process.objects.filter(client=c):
            progress_list.append({
                'client_pk': c.pk,
                'process_pk': proc.pk,
                'progresso': proc.progress_percentage,
            })

    advisors = ConsultancyUser.objects.filter(is_active=True).order_by("name")

    total_clients_kpi = len(clients_with_status)
    total_dependents_kpi = TripClient.objects.filter(
        client_id__in=[item["client"].pk for item in clients_with_status],
        role="dependent",
    ).values("client_id").distinct().count()
    total_pending_kpi = sum(
        1 for item in clients_with_status if item["financial_status"] == "Pendente"
    )
    total_paid_kpi = sum(
        1 for item in clients_with_status if item["financial_status"] == "Pago"
    )
    total_cancelled_kpi = sum(
        1 for item in clients_with_status if item["financial_status"] == "Cancelado"
    )
    total_no_records_kpi = sum(
        1 for item in clients_with_status if item["financial_status"] == "Sem registros"
    )
    clear_client_register_draft = request.session.pop("clear_client_register_draft", False)
    if clear_client_register_draft:
        request.session.modified = True

    return render(request, "client/home_clients.html", {
        "total_clients": total_clients_kpi,
        "total_dependents": total_dependents_kpi,
        "total_financial_pending": total_pending_kpi,
        "total_financial_paid": total_paid_kpi,
        "total_financial_cancelled": total_cancelled_kpi,
        "total_financial_no_records": total_no_records_kpi,
        "clients_with_status": clients_with_status,
        "user_profile": user_profile,
        "pode_delete_clients": can_manage_all,
        "filters_dict": filters,
        "advisors": advisors,
        "progressos": progress_list,
        "clear_client_register_draft": clear_client_register_draft,
    })


@login_required
def list_clients_view(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    clients = _list_clients_full_scope(request.user).prefetch_related("dependents", "trips")

    clients, filters = _apply_client_filters(clients, request, include_advisor=True)

    def _build_item(client):
        financial_status = _get_client_financial_status(client)
        form_status = _get_client_form_status(client)
        legacy_meta = _legacy_meta_from_client(client)
        return {
            "client": client,
            "financial_status": financial_status,
            "form_status": form_status["status"],
            "total_questions": form_status["total_questions"],
            "total_answers": form_status["total_answers"],
            "completo": form_status["completo"],
            "can_edit": user_can_edit_client(request.user, consultant, client),
            "legacy_meta": legacy_meta,
        }

    sorted_clients = _sort_clients_by_family_group(clients)
    clients_with_status = [_build_item(c) for c in sorted_clients]

    progress_list = []
    for c in clients:
        for proc in Process.objects.filter(client=c):
            progress_list.append({
                'client_pk': c.pk,
                'process_pk': proc.pk,
                'progresso': proc.progress_percentage,
            })

    total_clients_kpi = len(clients_with_status)
    total_dependents_kpi = TripClient.objects.filter(
        client_id__in=[item["client"].pk for item in clients_with_status],
        role="dependent",
    ).values("client_id").distinct().count()
    total_pending_kpi = sum(
        1 for item in clients_with_status if item["financial_status"] == "Pendente"
    )
    total_paid_kpi = sum(
        1 for item in clients_with_status if item["financial_status"] == "Pago"
    )
    total_cancelled_kpi = sum(
        1 for item in clients_with_status if item["financial_status"] == "Cancelado"
    )
    total_no_records_kpi = sum(
        1 for item in clients_with_status if item["financial_status"] == "Sem registros"
    )

    return render(request, "client/list_clients.html", {
        "clients_with_status": clients_with_status,
        "advisors": ConsultancyUser.objects.filter(is_active=True).order_by("name"),
        "user_profile": consultant.profile.name if consultant and consultant.profile else None,
        "pode_delete_clients": can_manage_all,
        "filters_dict": filters,
        "progressos": progress_list,
        "total_clients": total_clients_kpi,
        "total_dependents": total_dependents_kpi,
        "total_financial_pending": total_pending_kpi,
        "total_financial_paid": total_paid_kpi,
        "total_financial_cancelled": total_cancelled_kpi,
        "total_financial_no_records": total_no_records_kpi,
    })


def _get_current_step(steps, step_id: str | None) -> ClientRegistrationStep:
    current_step = steps.first()
    if step_id:
        with suppress(ValueError, ClientRegistrationStep.DoesNotExist):
            current_step = steps.get(pk=int(step_id))
    return current_step


def _get_session_temp_data(request) -> dict:
    return request.session.get("client_temp_data", {})


def _serialize_data_for_session(data: dict, preserve_confirm_password: bool = False) -> dict:
    serialized = {}
    for field, value in data.items():
        if field == 'confirm_password' and not preserve_confirm_password:
            continue
        elif hasattr(value, 'pk'):
            serialized[field] = value.pk
        elif hasattr(value, 'id'):
            serialized[field] = value.id
        elif isinstance(value, (date, datetime)):
            serialized[field] = value.isoformat()
        else:
            serialized[field] = value

    return serialized


def _save_session_temp_data(request, data: dict):
    serialized = _serialize_data_for_session(data)
    request.session["client_temp_data"] = serialized
    request.session.modified = True


def _clear_session_temp_data(request):
    if "client_temp_data" in request.session:
        request.session.pop("client_temp_data", None)
    request.session.modified = True


def _convert_field_value(instance, field_name: str, value):
    if not hasattr(instance, field_name):
        return value

    with suppress(AttributeError, TypeError):
        field = instance._meta.get_field(field_name)
        if hasattr(field, 'remote_field') and field.remote_field and value:
            if value == '' or value is None:
                return None
            related_model = field.remote_field.model
            with suppress(related_model.DoesNotExist, ValueError):
                pk_value = int(value) if isinstance(value, str) and value.isdigit() else value
                return related_model.objects.get(pk=pk_value)
        elif isinstance(field, (models.DateField, models.DateTimeField)) and isinstance(value, str):
            with suppress(ValueError, AttributeError):
                if isinstance(field, models.DateTimeField):
                    if 'T' in value or ' ' in value:
                        return datetime.fromisoformat(value.replace('Z', '+00:00'))
                    return datetime.combine(date.fromisoformat(value), datetime.min.time())
                return date.fromisoformat(value)

    return value


def _apply_data_to_client(client, data: dict, excluded_fields: set = None):
    if excluded_fields is None:
        excluded_fields = {'confirm_password'}

    for field_name, value in data.items():
        if field_name in excluded_fields or not hasattr(client, field_name):
            continue

        if field_name == 'primary_client':
            continue

        with suppress(AttributeError, TypeError):
            field = client._meta.get_field(field_name)
            if hasattr(field, 'remote_field') and field.remote_field and (value == '' or value is None):
                continue

        converted_value = _convert_field_value(client, field_name, value)
        setattr(client, field_name, converted_value)


def _add_debug_log(request, message: str, level: str = "info"):
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_msg = f"[{timestamp}] {message}"

    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.log(log_level, log_msg)

    if 'debug_logs_json' not in request.session:
        request.session['debug_logs_json'] = []
    request.session['debug_logs_json'].append({
        'timestamp': timestamp,
        'message': message,
        'level': level
    })
    if len(request.session['debug_logs_json']) > 20:
        request.session['debug_logs_json'] = request.session['debug_logs_json'][-20:]
    request.session.modified = True


def _mask_value_for_log(field_name: str, value) -> str:
    if value is None:
        return ""

    raw = str(value).strip()
    if raw == "":
        return ""

    if field_name in ("password", "confirm_password"):
        return "***"

    if field_name == "cpf":
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 11:
            return f"***.***.***-{digits[-2:]}"
        if len(digits) >= 4:
            return f"***{digits[-4:]}"
        return "***"

    if field_name in ("phone", "secondary_phone"):
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 4:
            return f"***{digits[-4:]}"
        return "***"

    if field_name == "email":
        if "@" in raw:
            local, domain = raw.split("@", 1)
            local_mask = (local[:1] + "***") if local else "***"
            return f"{local_mask}@{domain}"
        return "***"

    if field_name == "zip_code":
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 8:
            return f"{digits[:5]}-***"
        return "***"

    if field_name == "district":
        if len(raw) <= 12:
            return raw
        return f"{raw[:7]}...{raw[-3:]}"

    if field_name == "street_number":
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 3:
            return f"***{digits[-3:]}"
        return "***"

    if field_name == "complement":
        if len(raw) <= 10:
            return raw
        return f"{raw[:6]}..."

    if field_name == "passport_number":
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 3:
            return f"***{digits[-3:]}"
        return "***"

    if field_name == "birth_date":
        parts = raw.split("-")
        if len(parts) == 3 and parts[0].isdigit():
            return parts[0]
        return "***"

    if field_name == "street":
        if len(raw) <= 14:
            return raw
        return f"{raw[:10]}...{raw[-4:]}"

    return raw


def _summarize_fields_for_log(cleaned_data: dict, max_items: int = 10) -> str:
    if not cleaned_data:
        return "no_fields"

    parts: list[str] = []
    for field_name, value in cleaned_data.items():
        if field_name == "confirm_password":
            continue

        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue

        if hasattr(value, "pk"):
            value = getattr(value, "pk")
        elif hasattr(value, "id") and not hasattr(value, "pk"):
            value = getattr(value, "id")

        masked = _mask_value_for_log(field_name, value)
        if masked == "":
            continue

        parts.append(f"{field_name}={masked}")
        if len(parts) >= max_items:
            break

    return ", ".join(parts) if parts else "no_fields"


def _validate_step_summary(current_step, updated_data: dict, form_cleaned_data: dict) -> list[str]:
    warnings: list[str] = []

    if getattr(current_step, "boolean_field", None):
        flag = current_step.boolean_field
        if updated_data.get(flag) is not True:
            warnings.append(f"flag_sessao_nao_setada({flag})")

    zip_code = updated_data.get("zip_code")
    zip_str = str(zip_code).strip() if zip_code is not None else ""
    if zip_str:
        addr_fields = ["street", "district", "city", "state"]
        addr_fields_sent = [f for f in addr_fields if f in (form_cleaned_data or {})]
        if addr_fields_sent:
            missing = [f for f in addr_fields_sent if not str(updated_data.get(f, "")).strip()]
            if missing:
                warnings.append(f"cep_sem_endereco({','.join(missing)})")

    passport_type = updated_data.get("passport_type")
    if str(passport_type).strip().lower() == "outro":
        if not str(updated_data.get("passport_type_other", "")).strip():
            warnings.append("tipo_passaporte_outro_ausente")

    return warnings


def _log_completed_step_summary(request, current_step, form_cleaned_data: dict, updated_data: dict) -> None:
    field_summary = _summarize_fields_for_log(form_cleaned_data)
    warnings = _validate_step_summary(current_step, updated_data, form_cleaned_data)

    completed_flag = None
    if getattr(current_step, "boolean_field", None):
        completed_flag = updated_data.get(current_step.boolean_field) is True

    msg = (
        f"Etapa finalizada (sessao) etapa='{current_step.name}' "
        f"id={current_step.pk} campo_booleano_concluido={completed_flag} campos={field_summary}"
    )

    if warnings:
        logger.warning(msg + f" | avisos={';'.join(warnings)}")
    else:
        logger.info(msg)

    _add_debug_log(request, f"Etapa finalizada: {current_step.name}")


def _create_client_from_session(request) -> ConsultancyClient | None:
    temp_data = _get_session_temp_data(request)
    if not temp_data:
        return None

    try:
        client = ConsultancyClient()
        _apply_data_to_client(client, temp_data)
        return client
    except Exception:
        return None


def _configure_form_fields(form, current_step):
    step_fields_dict = {
        _client_step_form_field_name(field_cfg.field_name): field_cfg
        for field_cfg in ClientStepField.objects.filter(
            step=current_step, is_active=True
        ).order_by("order", "field_name")
    }
    fields_to_remove = []
    for field_name, field in form.fields.items():
        field_cfg = step_fields_dict.get(field_name)
        if field_cfg:
            field.required = field_cfg.is_required
        else:
            fields_to_remove.append(field_name)
    for field_name in fields_to_remove:
        del form.fields[field_name]


def _save_step_to_session(form, current_step, request):
    step_field_names = set(
        _client_step_form_field_name(field_name)
        for field_name in ClientStepField.objects.filter(
            step=current_step, is_active=True
        ).values_list("field_name", flat=True)
    )
    if 'password' in step_field_names:
        step_field_names.add('confirm_password')

    existing_data = _get_session_temp_data(request)
    updated_data = existing_data.copy()

    for field, value in form.cleaned_data.items():
        if field not in step_field_names:
            continue
        if hasattr(value, 'pk'):
            updated_data[field] = value.pk
        else:
            updated_data[field] = value

    if flag_name := _client_step_flag(current_step.boolean_field):
        updated_data[flag_name] = True

    _save_session_temp_data(request, updated_data)
    _log_completed_step_summary(request, current_step, form.cleaned_data, updated_data)


def _advance_to_next_step(current_step, steps, request_path, request):
    if next_step := steps.filter(order__gt=current_step.order).first():
        messages.success(request, f"Etapa '{current_step.name}' concluída!")
        return redirect(f"{request_path}?stage_id={next_step.pk}")

    if _client_step_flag(current_step.boolean_field) == 'step_members':
        messages.success(request, f"Etapa '{current_step.name}' concluída! Você pode adicionar dependentes abaixo.")
        return redirect(f"{request_path}?stage_id={current_step.pk}")

    return None


def _create_dependent_from_db(
    dependent_data: dict,
    primary_client: ConsultancyClient,
    user,
) -> tuple[ConsultancyClient | None, str | None]:
    dependent_name = dependent_data.get('first_name', 'Desconhecido')
    dependent_cpf = dependent_data.get('cpf', '')

    try:
        logger.info(f"Criando dependente: {dependent_name} (cpf: {dependent_cpf}) para cliente principal: {primary_client.first_name}")

        if dependent_cpf:
            cpf_digits = "".join(c for c in dependent_cpf if c.isdigit())
            cpf_fmt = f"{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}" if len(cpf_digits) == 11 else dependent_cpf
            digits_only = cpf_digits
            if existing_client := ConsultancyClient.objects.filter(cpf__in=[digits_only, cpf_fmt]).first():
                if existing_client.pk != primary_client.pk and existing_client.primary_client_id != primary_client.pk:
                    logger.error(f"CPF {dependent_cpf} já está em uso por outro cliente: {existing_client.first_name}")
                    return None, "Este CPF já está cadastrado."

        use_primary_data = dependent_data.get('use_primary_data', False)

        if 'password' in dependent_data and dependent_data.get('password') and 'confirm_password' not in dependent_data:
            dependent_data['confirm_password'] = dependent_data['password']
            logger.info("Adicionando confirm_password aos dados do dependente (usando valor da senha)")

        dependent_form = ConsultancyClientForm(data=dependent_data, instance=None, user=user, primary_client=primary_client, use_primary_data=use_primary_data)
        if not dependent_form.is_valid():
            error_msg = None
            if "cpf" in dependent_form.errors and dependent_form.errors["cpf"]:
                error_msg = dependent_form.errors["cpf"][0]
            elif dependent_form.errors:
                _, errors = next(iter(dependent_form.errors.items()))
                error_msg = errors[0] if errors else None

            logger.error(f"Formulário de dependente inválido para {dependent_name}: {dependent_form.errors}")
            return None, error_msg or "Falha ao validar os dados do dependente."

        dependent = dependent_form.save(commit=False)

        dependent.primary_client_id = primary_client.pk
        dependent.assigned_advisor = primary_client.assigned_advisor
        dependent.referring_partner = primary_client.referring_partner
        dependent.created_by = user

        logger.info(f"Vinculando dependente {dependent_name} ao cliente principal {primary_client.first_name} (ID: {primary_client.pk})")

        data_without_primary = {k: v for k, v in dependent_data.items() if k != 'primary_client'}
        _apply_data_to_client(dependent, data_without_primary)

        if dependent_data.get('use_primary_address', False):
            dependent.zip_code = primary_client.zip_code
            dependent.street = primary_client.street
            dependent.street_number = primary_client.street_number
            dependent.complement = primary_client.complement
            dependent.district = primary_client.district
            dependent.city = primary_client.city
            dependent.state = primary_client.state

        if dependent.primary_client_id != primary_client.pk:
            logger.error("ERRO: primary_client foi sobrescrito! Corrigindo...")
            dependent.primary_client_id = primary_client.pk

        if use_primary_data:
            dependent.email = ""
            dependent.password = ""
        else:
            dependent.email = dependent_data.get("email", "") or ""
            if raw_password := dependent_data.get("password"):
                dependent.set_password(raw_password)

        first_step = ClientRegistrationStep.objects.filter(is_active=True).order_by("order").first()
        if first_step and first_step.boolean_field:
            setattr(dependent, _client_step_flag(first_step.boolean_field), True)

        dependent.save()

        refreshed_dependent = ConsultancyClient.objects.get(pk=dependent.pk)
        if refreshed_dependent.primary_client_id != primary_client.pk:
            logger.error(f"ERRO: Dependente {dependent_name} não está vinculado após salvar! primary_client_id={refreshed_dependent.primary_client_id}")
            return None, "Erro interno ao vincular dependente ao principal."

        logger.info(f"Dependente {dependent_name} salvo com sucesso (ID: {dependent.pk}, primary_client_id: {dependent.primary_client_id})")
        return dependent, None
    except Exception as e:
        logger.error(f"Erro ao salvar dependente {dependent_name}: {str(e)}", exc_info=True)
        return None, str(e)


def _mark_completed_steps(client: ConsultancyClient, temp_data: dict):
    boolean_fields = ['step_personal_data', 'step_address', 'step_passport', 'step_members']
    for boolean_field in boolean_fields:
        if temp_data.get(boolean_field):
            setattr(client, boolean_field, True)


def _stage_is_completed(stage, temp_data: dict) -> bool:
    return bool(
        temp_data.get(stage.boolean_field)
        or temp_data.get(_client_step_flag(stage.boolean_field))
    )


def _process_temp_dependents(request, client: ConsultancyClient) -> int:
    temp_dependents = request.session.get("temp_dependents", [])
    if not temp_dependents:
        logger.info(f"Nenhum dependente temporário encontrado na sessão para cliente {client.full_name}")
        return 0

    logger.info(f"Processando {len(temp_dependents)} dependente(s) temporário(s) para cliente {client.full_name}")
    saved_count = 0
    failed_names: list[str] = []

    for idx, dependent_data in enumerate(temp_dependents):
        name = dependent_data.get('first_name', 'Desconhecido')
        cpf = dependent_data.get('cpf', '')

        logger.info(f"Processando dependente {idx + 1}/{len(temp_dependents)}: {name} (cpf: {cpf})")
        logger.info(f"Dados do dependente: {dependent_data}")

        if not name:
            logger.error(f"Dependente {idx + 1} não tem nome - pulando")
            failed_names.append(f"Dependente {idx + 1} (sem nome)")
            continue

        if not cpf:
            logger.error(f"Dependente {name} não tem CPF - pulando (CPF é obrigatório e único)")
            failed_names.append(f"{name} (sem CPF)")
            continue

        try:
            dependent, error_msg = _create_dependent_from_db(dependent_data, client, request.user)
            if dependent:
                saved_count += 1
                dependent.refresh_from_db()
                if dependent.primary_client_id == client.pk:
                    logger.info(f"Dependente {name} salvo com sucesso (ID: {dependent.pk}, primary_client_id: {dependent.primary_client_id})")
                else:
                    logger.error(f"ERRO: Dependente {name} não está vinculado corretamente! primary_client_id={dependent.primary_client_id}, esperado={client.pk}")
                    dependent.primary_client_id = client.pk
                    dependent.save(update_fields=['primary_client'])
                    logger.info(f"Relacionamento corrigido para dependente {name}")
            else:
                failed_names.append(name)
                logger.error(f"Falha ao salvar dependente: {name}")
                if error_msg:
                    messages.error(request, f"Dependente '{name}': {error_msg}")
                else:
                    messages.error(request, f"Dependente '{name}': Falha ao salvar.")
                _add_debug_log(request, f"Erro ao salvar dependente: {name} ({error_msg})")
        except Exception as e:
            failed_names.append(name)
            logger.error(f"Exceção ao salvar dependente {name}: {str(e)}", exc_info=True)
            _add_debug_log(request, f"Exceção ao salvar dependente {name}: {str(e)}")

    if failed_names:
        logger.warning(f"{len(failed_names)} dependente(s) não foram salvos: {', '.join(failed_names)}")
        raise InvalidDependentsError("Falha ao salvar dependentes. Verifique os erros e tente novamente.")

    request.session.pop("temp_dependents", None)

    logger.info(f"Total de dependentes salvos: {saved_count}/{len(temp_dependents)}")
    return saved_count


def _recover_advisor_from_temp_data(temp_data: dict) -> ConsultancyUser | None:
    if not (advisor_id_temp := temp_data.get('assigned_advisor')):
        return None

    try:
        if isinstance(advisor_id_temp, str) and advisor_id_temp.strip():
            advisor_id_temp = int(advisor_id_temp)
        elif not isinstance(advisor_id_temp, int):
            return None

        return ConsultancyUser.objects.filter(pk=advisor_id_temp, is_active=True).first()
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro ao converter assigned_advisor dos dados temporários: {e}")
        return None


def _set_advisor_with_log(client: ConsultancyClient, advisor: ConsultancyUser, source: str) -> None:
    client.assigned_advisor = advisor
    logger.info(f"Assessor {source}: {advisor.name} (ID: {advisor.pk})")


def _ensure_assigned_advisor(client: ConsultancyClient, temp_data: dict, user) -> None:
    if client.assigned_advisor_id:
        return

    if advisor := _recover_advisor_from_temp_data(temp_data):
        _set_advisor_with_log(client, advisor, "recuperado dos dados temporários")
        return

    if consultant := get_user_consultant(user):
        _set_advisor_with_log(client, consultant, "definido a partir do usuário logado")
        return

    logger.error(f"Não foi possível determinar o assessor. Dados temporários: assigned_advisor={temp_data.get('assigned_advisor')}")
    raise ValueError("Não foi possível determinar o assessor responsável. Por favor, selecione um assessor na primeira etapa.")


def _process_and_log_dependents(request, client: ConsultancyClient) -> int:
    logger.info("Verificando dependentes temporários na sessão antes de processar...")
    temp_dependents_before = request.session.get("temp_dependents", [])
    logger.info(f"Dependentes temporários encontrados na sessão: {len(temp_dependents_before)}")
    if temp_dependents_before:
        logger.info(f"Conteúdo dos dependentes temporários: {temp_dependents_before}")

    saved_count = _process_temp_dependents(request, client)

    if saved_count > 0:
        logger.info(f"{saved_count} dependente(s) vinculado(s) ao cliente {client.full_name}")
        _add_debug_log(request, f"{saved_count} dependente(s) vinculado(s) ao cliente")
    else:
        logger.warning(f"Nenhum dependente foi salvo para o cliente {client.full_name}")
        if temp_dependents_before:
            logger.error(f"Havia {len(temp_dependents_before)} dependente(s) na sessão, mas nenhum foi salvo!")

    return saved_count


def _validate_temp_data(temp_data: dict | None) -> None:
    if not temp_data:
        raise ValueError("Dados não encontrados na sessão. Por favor, inicie o cadastro novamente.")


def _create_and_configure_client(temp_data: dict, user) -> ConsultancyClient:
    client = ConsultancyClient()
    _apply_data_to_client(client, temp_data)
    client.created_by = user
    _ensure_assigned_advisor(client, temp_data, user)
    return client


def _configure_password_and_steps(client: ConsultancyClient, temp_data: dict) -> None:
    if raw_password := temp_data.get('password'):
        client.set_password(raw_password)
    _mark_completed_steps(client, temp_data)


def _save_and_log_client(request, client: ConsultancyClient) -> None:
    with transaction.atomic():
        client.save()
        saved_dependents = _process_and_log_dependents(request, client)

    confirmed_steps = {}
    for boolean_field in ("step_personal_data", "step_address", "step_passport", "step_members"):
        if hasattr(client, boolean_field):
            confirmed_steps[boolean_field] = bool(getattr(client, boolean_field))

    logger.info(
        f"Cliente '{client.full_name}' salvo no banco (ID: {client.pk}) "
        f"dependentes_salvos={saved_dependents} etapas_confirmadas={confirmed_steps}"
    )
    _add_debug_log(request, f"Cliente '{client.full_name}' salvo no banco (ID: {client.pk})")
    request.session.modified = True


def _create_client_from_db(request) -> ConsultancyClient:
    temp_data = _get_session_temp_data(request)
    _validate_temp_data(temp_data)

    client = _create_and_configure_client(temp_data, request.user)
    _configure_password_and_steps(client, temp_data)
    _save_and_log_client(request, client)

    return client


def _get_client_ids_with_dependents(client: ConsultancyClient) -> list:
    client_ids = [client.pk]
    dependents = ConsultancyClient.objects.filter(primary_client=client)
    client_ids.extend(dependents.values_list('pk', flat=True))
    return client_ids


def _create_trip_redirect_with_clients(request, client: ConsultancyClient):
    logger.info(f"Redirecionando para criar viagem com cliente {client.full_name} (ID: {client.pk})")
    client_ids = _get_client_ids_with_dependents(client)
    redirect_url = f"{reverse('system:create_trip')}?clientes={','.join(map(str, client_ids))}"
    logger.info(f"Redirect para criar viagem: {redirect_url}")
    _add_debug_log(request, f"Redirecionando para criar viagem com {len(client_ids)} cliente(s)")
    return redirect(redirect_url)


def _finalize_client_registration(request, client: ConsultancyClient, create_trip: bool = False):
    flag_key = f'cadastro_finalizado_{client.pk}'
    if request.session.get(flag_key, False):
        logger.info(f"Tentativa de finalizar cadastro duplicada para cliente {client.pk} - redirecionando sem mensagem")
        if create_trip:
            client_ids = _get_client_ids_with_dependents(client)
            return redirect(f"{reverse('system:create_trip')}?clientes={','.join(map(str, client_ids))}")
        return redirect("system:home_clients")

    request.session[flag_key] = True
    request.session.modified = True

    num_dependents = ConsultancyClient.objects.filter(primary_client=client).count()

    _add_debug_log(request, f"Cadastro finalizado com sucesso! Cliente: {client.full_name}, Dependentes: {num_dependents}")

    if "client_temp_data" in request.session:
        request.session.pop("client_temp_data", None)
    if "temp_dependents" in request.session:
        request.session.pop("temp_dependents", None)
    request.session["clear_client_register_draft"] = True
    request.session.modified = True

    if num_dependents > 0:
        messages.success(
            request,
            f"Cadastro finalizado com sucesso! Cliente '{client.full_name}' e {num_dependents} dependente(s) foram cadastrados. O cliente foi salvo no sistema e está disponível na lista de clientes."
        )
    else:
        messages.success(
            request,
            f"Cadastro finalizado com sucesso! Cliente '{client.full_name}' foi cadastrado. O cliente foi salvo no sistema e está disponível na lista de clientes."
        )

    request.session.modified = True

    if create_trip:
        return _create_trip_redirect_with_clients(request, client)

    redirect_url_name = "system:home_clients"
    _add_debug_log(request, f"Redirecionando para: {redirect_url_name}")
    logger.info(f"Finalizando cadastro - criando redirect para: {redirect_url_name}")

    redirect_response = redirect(redirect_url_name)

    if hasattr(redirect_response, 'url'):
        logger.info(f"Redirect criado com sucesso - URL: {redirect_response.url}")
        _add_debug_log(request, f"Redirect criado - URL: {redirect_response.url}")
    else:
        logger.warning(f"Redirect criado mas sem atributo 'url' - Tipo: {type(redirect_response)}")
        _add_debug_log(request, f"Redirect criado - Tipo: {type(redirect_response)}", "warning")

    return redirect_response


def _prepare_context(steps, current_step, step_fields, form, client, consultant):
    steps_list = list(steps)
    step_index = next(
        (i for i, s in enumerate(steps_list) if s.pk == current_step.pk), 0
    )
    previous_step = steps_list[step_index - 1] if step_index > 0 else None
    next_step = (
        steps_list[step_index + 1]
        if step_index < len(steps_list) - 1
        else None
    )
    display_fields = [
        {
            "config": step_field,
            "form_field_name": _client_step_form_field_name(step_field.field_name),
        }
        for step_field in step_fields
    ]

    return {
        "form": form,
        "current_stage": current_step,
        "stages": steps_list,
        "previous_stage": previous_step,
        "next_stage": next_step,
        "stage_fields": step_fields,
        "display_fields": display_fields,
        "client": client,
        "user_profile": consultant.profile.name if consultant else None,
    }


def _build_dependent_display_fields(dependent_fields):
    zip_step_ids = {
        field_cfg.step_id
        for field_cfg in dependent_fields
        if _client_step_form_field_name(field_cfg.field_name) == "zip_code"
    }
    return [
        {
            "config": field_cfg,
            "form_field_name": _client_step_form_field_name(field_cfg.field_name),
            "render_with_zip": (
                _client_step_form_field_name(field_cfg.field_name) == "state"
                and field_cfg.step_id in zip_step_ids
            ),
        }
        for field_cfg in dependent_fields
    ]


def _show_form_errors(request, form, step_field_names, prefix="", step_name: str | None = None):
    if "password" in step_field_names:
        step_field_names.add("confirm_password")

    if step_name:
        error_summaries: list[str] = []
        for field_name, errors in form.errors.items():
            if field_name in step_field_names and errors:
                error_summaries.append(f"{field_name}={str(errors[0])[:120]}")
        if error_summaries:
            logger.warning(f"Form invalido (etapa='{step_name}') erros={', '.join(error_summaries)}")

    for field_name, errors in form.errors.items():
        if field_name in step_field_names:
            field_label = form.fields[field_name].label if field_name in form.fields else field_name
            for error in errors:
                messages.error(request, f"{prefix}{field_label}: {error}")


def _get_dependent_advisor_id(request, client, temp_data):
    advisor_id = None

    if hasattr(client, 'assigned_advisor_id') and client.assigned_advisor_id:
        advisor_id = client.assigned_advisor_id
    elif temp_data and (advisor_value := temp_data.get('assigned_advisor')):
        try:
            advisor_id = int(advisor_value) if isinstance(advisor_value, str) else advisor_value
        except (ValueError, TypeError):
            advisor_id = None

    if not advisor_id:
        if consultant := get_user_consultant(request.user):
            advisor_id = consultant.pk

    return advisor_id


def _prepare_initial_dependent_data(request, advisor_id):
    editing_data = request.session.get('editing_dependent_data')
    initial_data = None
    use_primary_data_edit = False

    if editing_data:
        initial_data = editing_data.copy()
        use_primary_data_edit = editing_data.get('use_primary_data', False)
        logger.info(f"Carregando dados do dependente para edição: {initial_data.get('first_name', 'Desconhecido')}")
        if advisor_id and ('assigned_advisor' not in initial_data or not initial_data.get('assigned_advisor')):
            initial_data['assigned_advisor'] = advisor_id
    elif advisor_id:
        initial_data = {'assigned_advisor': advisor_id}

    return initial_data, use_primary_data_edit


def _fill_dependent_address_fields(dependent_form, client, temp_data):
    address_fields = ['zip_code', 'street', 'street_number', 'complement', 'district', 'city', 'state']
    for field in address_fields:
        if field in dependent_form.fields:
            if hasattr(client, field) and (value := getattr(client, field)):
                dependent_form.fields[field].initial = value
            elif temp_data and (value := temp_data.get(field)):
                dependent_form.fields[field].initial = value


def _configure_dependent_form_fields(dependent_form, first_step, steps):
    if not steps:
        _configure_form_fields(dependent_form, first_step)
        return

    dependent_steps = [
        step for step in steps.filter(is_active=True).order_by("order")
        if _client_step_flag(step.boolean_field) != "step_members"
    ]
    dependent_fields_dict = {}
    for step in dependent_steps:
        step_fields = ClientStepField.objects.filter(step=step, is_active=True).exclude(field_name="referring_partner")
        dependent_fields_dict.update({
            _client_step_form_field_name(field_cfg.field_name): field_cfg
            for field_cfg in step_fields
        })

    for field_name, field in dependent_form.fields.items():
        if field_cfg := dependent_fields_dict.get(field_name):
            field.required = field_cfg.is_required
        else:
            field.required = False


def _create_dependent_form(request, client, first_step, steps=None):
    primary_client = client if isinstance(client, ConsultancyClient) and client.is_primary else None

    temp_data = _get_session_temp_data(request)
    advisor_id = _get_dependent_advisor_id(request, client, temp_data)

    initial_data, use_primary_data_edit = _prepare_initial_dependent_data(request, advisor_id)

    dependent_form = ConsultancyClientForm(
        data=None,
        initial=initial_data,
        user=request.user,
        primary_client=primary_client,
        use_primary_data=use_primary_data_edit
    )

    if advisor_id:
        dependent_form.fields["assigned_advisor"].initial = advisor_id

    if "referring_partner" in dependent_form.fields:
        del dependent_form.fields["referring_partner"]

    _fill_dependent_address_fields(dependent_form, client, temp_data)

    _configure_dependent_form_fields(dependent_form, first_step, steps)

    return dependent_form


def _remove_referring_partner(form):
    if "referring_partner" in form.fields:
        del form.fields["referring_partner"]


def _make_password_optional(form):
    if 'password' in form.fields:
        form.fields['password'].required = False
    if 'confirm_password' in form.fields:
        form.fields['confirm_password'].required = False


def _prepare_dependent_post_form(request, first_step, steps=None, primary_client=None):
    use_primary_data = request.POST.get('use_primary_data') == 'on'

    form = ConsultancyClientForm(
        data=request.POST,
        user=request.user,
        primary_client=primary_client,
        use_primary_data=use_primary_data
    )
    _remove_referring_partner(form)

    if use_primary_data:
        _make_password_optional(form)

    _configure_dependent_form_fields(form, first_step, steps)

    if use_primary_data:
        _make_password_optional(form)

    return form


def _save_dependent(form, primary_client, first_step, user, use_primary_data=False):
    dependent = form.save(commit=False)
    dependent.primary_client = primary_client
    dependent.assigned_advisor = primary_client.assigned_advisor
    dependent.referring_partner = primary_client.referring_partner
    if not dependent.created_by_id:
        dependent.created_by = user

    if use_primary_data:
        dependent.email = ""
        dependent.password = ""

    dependent.save()

    if first_step.boolean_field:
        flag_name = _client_step_flag(first_step.boolean_field)
        setattr(dependent, flag_name, True)
        dependent.save(update_fields=[flag_name])


def _store_temp_dependent_in_session(request, dependent_data: dict):
    dependent_name = dependent_data.get('first_name', 'Desconhecido')
    logger.info(f"Armazenando dependente temporário na sessão: {dependent_name}")
    logger.info(f"Dados do dependente antes de serializar: {dependent_data}")

    temp_dependents = request.session.get("temp_dependents", [])
    logger.info(f"Dependentes temporários existentes na sessão: {len(temp_dependents)}")

    serialized = _serialize_data_for_session(dependent_data, preserve_confirm_password=True)
    logger.info(f"Dados serializados: {serialized}")

    temp_dependents.append(serialized)
    request.session["temp_dependents"] = temp_dependents
    request.session.modified = True

    logger.info(f"Dependente {dependent_name} armazenado na sessão. Total na sessão: {len(temp_dependents)}")

    if 'debug_logs' not in request.session:
        request.session['debug_logs'] = []
    request.session['debug_logs'].append(
        f"[{datetime.now().strftime('%H:%M:%S')}] Dependente '{serialized.get('first_name')}' adicionado temporariamente (será salvo ao finalizar)"
    )
    request.session.modified = True


def _process_valid_dependent(request, dependent_post_form, current_step):
    logger.info("Formulário de dependente válido. Armazenando na sessão...")

    dependent_data = dependent_post_form.cleaned_data.copy()

    use_primary_data = request.POST.get('use_primary_data') == 'on'
    dependent_data['use_primary_data'] = use_primary_data
    logger.info(
        "Dependente configurado para %s a conta do cliente principal",
        "usar" if use_primary_data else "não usar",
    )

    use_primary_address = request.POST.get('use_primary_address') == 'on'
    if use_primary_address:
        dependent_data['use_primary_address'] = True
        logger.info("Dependente configurado para usar endereço do cliente principal")

    editing_index = request.session.get('editing_dependent_index')
    if editing_index is not None:
        temp_dependents = request.session.get("temp_dependents", [])
        if 0 <= editing_index < len(temp_dependents):
            serialized = _serialize_data_for_session(dependent_data, preserve_confirm_password=True)
            temp_dependents[editing_index] = serialized
            request.session["temp_dependents"] = temp_dependents
            request.session.pop('editing_dependent_index', None)
            request.session.pop('editing_dependent_data', None)
            request.session.modified = True
            dependent_name = dependent_data.get('first_name', 'Desconhecido')
            messages.success(request, f"{dependent_name} atualizado. Será salvo ao finalizar o cadastro.")
            logger.info(f"Dependente {dependent_name} atualizado com sucesso. Redirecionando...")
            return redirect(f"{request.path}?stage_id={current_step.pk}")

    _store_temp_dependent_in_session(request, dependent_data)
    dependent_name = dependent_data.get('first_name', 'Desconhecido')
    messages.success(request, f"{dependent_name} adicionado. Será salvo ao finalizar o cadastro.")
    logger.info(f"Dependente {dependent_name} adicionado com sucesso. Redirecionando...")
    return redirect(f"{request.path}?stage_id={current_step.pk}")


def _get_primary_client_for_dependent(temp_data, temp_client, use_primary_data):
    primary_client = None

    if temp_data and 'primary_client_id' in temp_data:
        primary_client_id = temp_data['primary_client_id']
        with suppress(ConsultancyClient.DoesNotExist):
            primary_client = ConsultancyClient.objects.get(pk=primary_client_id)
    elif temp_client and isinstance(temp_client, ConsultancyClient) and temp_client.is_primary:
        primary_client = temp_client

    if use_primary_data and not primary_client and temp_client:
        primary_client = temp_client

    return primary_client


def _ensure_advisor_in_form(
    dependent_post_form,
    temp_client,
    temp_data,
    primary_client,
    request,
    first_step,
    steps,
):
    if dependent_post_form.data.get('assigned_advisor'):
        return dependent_post_form

    advisor_id = _get_dependent_advisor_id(request, temp_client, temp_data)

    if not advisor_id:
        return dependent_post_form

    from django.http import QueryDict
    if isinstance(dependent_post_form.data, QueryDict):
        form_data = dependent_post_form.data.copy()
        form_data['assigned_advisor'] = str(advisor_id)
        use_primary_data = request.POST.get('use_primary_data') == 'on'
        dependent_post_form = ConsultancyClientForm(
            data=form_data,
            user=request.user,
            primary_client=primary_client,
            use_primary_data=use_primary_data
        )
        _remove_referring_partner(dependent_post_form)
        _configure_dependent_form_fields(dependent_post_form, first_step, steps)

    return dependent_post_form


def _process_dependent_registration(request, current_step, temp_client, steps):
    if not (first_step := steps.filter(is_active=True).order_by("order").first()):
        return None, None

    temp_data = _get_session_temp_data(request)
    use_primary_data = request.POST.get('use_primary_data') == 'on'
    primary_client = _get_primary_client_for_dependent(temp_data, temp_client, use_primary_data)

    dependent_post_form = _prepare_dependent_post_form(
        request, first_step, steps, primary_client=primary_client
    )

    dependent_post_form = _ensure_advisor_in_form(
        dependent_post_form, temp_client, temp_data, primary_client, request, first_step, steps
    )

    first_step_fields = ClientStepField.objects.filter(
        step=first_step, is_active=True
    ).exclude(field_name="referring_partner").order_by("order", "field_name")

    if dependent_post_form.is_valid():
        temp_dependents = request.session.get("temp_dependents", [])
        editing_index = request.session.get("editing_dependent_index")

        new_cpf = dependent_post_form.cleaned_data.get("cpf", "") or ""
        new_cpf_digits = "".join(c for c in str(new_cpf) if c.isdigit())

        for idx, dep_tmp in enumerate(temp_dependents):
            existing_cpf = (dep_tmp or {}).get("cpf", "") or ""
            existing_cpf_digits = "".join(c for c in str(existing_cpf) if c.isdigit())
            if not existing_cpf_digits:
                continue
            if existing_cpf_digits == new_cpf_digits:
                if editing_index is not None and idx == editing_index:
                    continue
                dependent_post_form.add_error("cpf", "Este CPF já está cadastrado.")
                return None, dependent_post_form

        return _process_valid_dependent(request, dependent_post_form, current_step), None

    logger.error(f"Formulário de dependente inválido: {dependent_post_form.errors}")
    step_field_names = {
        _client_step_form_field_name(field_name)
        for field_name in first_step_fields.values_list("field_name", flat=True)
    }
    _show_form_errors(
        request,
        dependent_post_form,
        step_field_names,
        prefix="Dependente - ",
        step_name=f"Dependente - {current_step.name}",
    )
    return None, dependent_post_form


def _prepare_dependents_context(request, current_step, temp_client, steps, context, dependent_form):
    if not (first_step := steps.filter(is_active=True).order_by("order").first()):
        return

    first_step_fields = ClientStepField.objects.filter(
        step=first_step, is_active=True
    ).exclude(field_name="referring_partner").order_by("order", "field_name")

    if dependent_form is None:
        dependent_form = _create_dependent_form(request, temp_client, first_step, steps)

    temp_dependents = request.session.get("temp_dependents", [])

    dependent_steps = [
        step for step in steps.filter(is_active=True).order_by("order")
        if _client_step_flag(step.boolean_field) != "step_members"
    ]
    dependent_fields = []
    for step in dependent_steps:
        step_fields = ClientStepField.objects.filter(
            step=step, is_active=True
        ).exclude(field_name="referring_partner").order_by("order", "field_name")
        dependent_fields.extend(step_fields)

    editing_data = request.session.get('editing_dependent_data')

    advisor_id = None
    if temp_client and hasattr(temp_client, 'assigned_advisor_id') and temp_client.assigned_advisor_id:
        advisor_id = temp_client.assigned_advisor_id
    else:
        temp_data = _get_session_temp_data(request)
        if temp_data and (advisor_value := temp_data.get('assigned_advisor')):
            try:
                advisor_id = int(advisor_value) if isinstance(advisor_value, str) else advisor_value
            except (ValueError, TypeError):
                advisor_id = None
        if not advisor_id:
            if consultant := get_user_consultant(request.user):
                advisor_id = consultant.pk

    context['first_stage'] = first_step
    context['first_stage_fields'] = first_step_fields
    context['dependent_fields'] = dependent_fields
    context['dependent_display_fields'] = _build_dependent_display_fields(dependent_fields)
    context['dependent_steps'] = dependent_steps
    context['dependent_stages'] = dependent_steps
    context['dependent_form'] = dependent_form
    context['temp_dependents'] = temp_dependents
    context['dependentes'] = []
    context['editing_dependent_data'] = editing_data
    context['advisor_id'] = advisor_id


def _process_registration_cancellation(request):
    _add_debug_log(request, "Cadastro cancelado pelo usuário")

    _clear_session_temp_data(request)
    request.session["clear_client_register_draft"] = True

    if "temp_dependents" in request.session:
        request.session.pop("temp_dependents", None)

    keys_to_remove = [key for key in request.session.keys() if key.startswith('registration_completed_')]
    for key in keys_to_remove:
        request.session.pop(key, None)

    request.session.modified = True
    messages.info(request, "Cadastro cancelado.")
    return redirect("system:home_clients")


def _process_remove_dependent(request, current_step):
    try:
        dependent_index = int(request.POST.get("dependent_index", -1))
    except (ValueError, TypeError):
        dependent_index = -1

    if dependent_index < 0:
        messages.error(request, "Índice de dependente inválido.")
        return redirect(f"{request.path}?stage_id={current_step.pk}")

    temp_dependents = request.session.get("temp_dependents", [])

    if dependent_index >= len(temp_dependents):
        messages.error(request, "Dependente não encontrado.")
        return redirect(f"{request.path}?stage_id={current_step.pk}")

    removed_dependent = temp_dependents[dependent_index]
    dependent_name = removed_dependent.get('first_name', 'Desconhecido')

    temp_dependents.pop(dependent_index)
    request.session["temp_dependents"] = temp_dependents
    request.session.modified = True

    logger.info(f"Dependente temporário removido: {dependent_name} (índice {dependent_index})")
    _add_debug_log(request, f"Dependente '{dependent_name}' removido temporariamente")
    messages.success(request, f"{dependent_name} removido da lista de membros.")

    return redirect(f"{request.path}?stage_id={current_step.pk}")


def _process_edit_dependent(request, current_step):
    try:
        dependent_index = int(request.POST.get("dependent_index", -1))
    except (ValueError, TypeError):
        dependent_index = -1

    if dependent_index < 0:
        messages.error(request, "Índice de dependente inválido.")
        return redirect(f"{request.path}?stage_id={current_step.pk}")

    temp_dependents = request.session.get("temp_dependents", [])

    if dependent_index >= len(temp_dependents):
        messages.error(request, "Dependente não encontrado.")
        return redirect(f"{request.path}?stage_id={current_step.pk}")

    dependent_to_edit = temp_dependents[dependent_index]
    dependent_name = dependent_to_edit.get('first_name', 'Desconhecido')

    request.session['editing_dependent_index'] = dependent_index
    request.session['editing_dependent_data'] = dependent_to_edit
    request.session.modified = True

    logger.info(f"Editando dependente {dependent_name} (índice {dependent_index})")
    messages.info(request, f"Editando {dependent_name}. Modifique os dados e clique em 'Salvar Alterações' para atualizar.")
    return redirect(f"{request.path}?stage_id={current_step.pk}&editing_dependent=true")


def _prepare_initial_form_data(request, temp_client):
    if request.POST:
        return None
    initial_data = {}
    ocr_data = request.session.get("passport_ocr_client", {})
    if ocr_data:
        initial_data.update({k: v for k, v in ocr_data.items() if v})
    if temp_client:
        if temp_data := _get_session_temp_data(request):
            temp = temp_data.copy()
            temp.pop('confirm_password', None)
            initial_data.update({k: v for k, v in temp.items() if v})
    return initial_data or None


def _extract_advisor_id_from_session(initial_data):
    if 'assigned_advisor' not in initial_data:
        return None

    advisor_value = initial_data['assigned_advisor']
    if not advisor_value:
        return None

    if hasattr(advisor_value, 'pk'):
        return advisor_value.pk
    if isinstance(advisor_value, str) and advisor_value.isdigit():
        return int(advisor_value)
    return advisor_value if isinstance(advisor_value, int) else None


def _create_get_form(request, current_step, initial_data):
    form = ConsultancyClientForm(data=initial_data, instance=None, user=request.user)

    advisor_id_session = _extract_advisor_id_from_session(initial_data) if initial_data else None

    if advisor_id_session and initial_data:
        initial_data['assigned_advisor'] = advisor_id_session
        form = ConsultancyClientForm(data=initial_data, instance=None, user=request.user)
        form.fields["assigned_advisor"].initial = advisor_id_session

    _configure_form_fields(form, current_step)
    return form


def _clear_finalization_flags(request):
    step_id = request.GET.get("stage_id")
    if not step_id and request.method == "GET" and not request.GET.get("clients"):
        keys_to_remove = [key for key in request.session.keys() if key.startswith('registration_completed_')]
        for key in keys_to_remove:
            request.session.pop(key, None)


def _prepare_final_context(request, current_step, temp_client, steps, context, dependent_form, has_zip_in_step, has_password_in_step):
    context['has_zip_in_stage'] = has_zip_in_step
    context['has_password_in_stage'] = has_password_in_step

    debug_logs_json = request.session.get('debug_logs_json', [])
    context['debug_logs_json'] = json.dumps(debug_logs_json)

    temp_data = _get_session_temp_data(request)
    context['temp_data'] = temp_data

    if _client_step_flag(current_step.boolean_field) == 'step_members' and temp_client:
        _prepare_dependents_context(
            request, current_step, temp_client, steps, context, dependent_form
        )

    return context


def _create_client_form(request, current_step, initial_data=None):
    initial_dict = {}
    if request.POST:
        temp_data = _get_session_temp_data(request)
        if temp_data and 'assigned_advisor' in temp_data:
            advisor_id = temp_data.get('assigned_advisor')
            if advisor_id and (not request.POST.get('assigned_advisor') or request.POST.get('assigned_advisor') == ''):
                initial_dict['assigned_advisor'] = advisor_id

    form = ConsultancyClientForm(
        data=request.POST or initial_data,
        initial=initial_dict or None,
        instance=None,
        user=request.user
    )
    _configure_form_fields(form, current_step)
    return form


def _validate_previous_step(current_step, steps, request):
    if current_step.order <= 1 or _get_session_temp_data(request):
        return None
    first_step = steps.first()
    messages.error(request, f"Complete a etapa '{first_step.name}' primeiro.")
    return redirect(f"{request.path}?stage_id={first_step.pk}")


def _create_and_validate_client_from_db(request) -> ConsultancyClient:
    logger.info("Criando cliente do banco...")
    client = _create_client_from_db(request)
    logger.info(f"Cliente criado com sucesso: {client.full_name} (ID: {client.pk})")

    if not client.assigned_advisor_id:
        logger.warning("assigned_advisor não definido, tentando definir...")
        if consultant := get_user_consultant(request.user):
            client.assigned_advisor = consultant
            client.save(update_fields=['assigned_advisor'])
            logger.info(f"assigned_advisor definido: {consultant.name}")
        else:
            raise ValueError("Não foi possível determinar o assessor responsável. Por favor, selecione um assessor na primeira etapa.")

    return client


def _process_members_step_finalization(request, current_step, steps, create_trip=False):
    logger.info(f"_process_members_step_finalization chamada - create_trip={create_trip}")

    if temp_data := _get_session_temp_data(request):
        temp_data['step_members'] = True
        _save_session_temp_data(request, temp_data)

        temp_dependents = request.session.get("temp_dependents", [])
        logger.info(
            f"Finalizacao step_members (sessao) - dependentes_temporarios={len(temp_dependents)} "
            f"flag_step_members=True"
        )

        try:
            client = _create_and_validate_client_from_db(request)
            logger.info(f"Finalizando cadastro e redirecionando (create_trip={create_trip})...")
            return _finalize_client_registration(request, client, create_trip)
        except InvalidDependentsError:
            return redirect(f"{request.path}?stage_id={current_step.pk}")
        except Exception as e:
            logger.error(f"Erro ao finalizar cadastro: {str(e)}", exc_info=True)
            messages.error(request, str(e))
            _add_debug_log(request, f"Erro ao finalizar cadastro: {str(e)}", "error")
            first_step = steps.first()
            return redirect(f"{request.path}?stage_id={first_step.pk}")

    first_step = steps.first()
    logger.error("Dados temporários não encontrados na sessão")
    messages.error(request, "Dados não encontrados. Por favor, inicie o cadastro novamente.")
    _add_debug_log(request, "Tentativa de finalizar sem dados temporários na sessão", "error")
    return redirect(f"{request.path}?stage_id={first_step.pk}")


def _process_other_steps_finalization(request, form, current_step, step_field_names, create_trip=False):
    if not form.is_valid():
        _show_form_errors(request, form, step_field_names, step_name=current_step.name)
        return None

    _save_step_to_session(form, current_step, request)

    try:
        client = _create_client_from_db(request)
        redirect_response = _finalize_client_registration(request, client, create_trip)
        _add_debug_log(request, f"Redirect de finalização retornado: {redirect_response}")
        return redirect_response
    except ValueError as e:
        messages.error(request, str(e))
        _add_debug_log(request, f"Erro ao finalizar cadastro: {str(e)}", "error")
        return redirect("system:home_clients")


def _process_finalization(request, form, current_step, steps, step_field_names, dependent_form=None, create_trip=False):
    if _client_step_flag(current_step.boolean_field) == 'step_members':
        redirect_response = _process_members_step_finalization(request, current_step, steps, create_trip)
        _add_debug_log(request, f"Finalização step_members - Redirect retornado: {redirect_response is not None}")
        if redirect_response:
            return redirect_response, None, None
        return None, form, dependent_form

    redirect_response = _process_other_steps_finalization(request, form, current_step, step_field_names, create_trip)
    _add_debug_log(request, f"Finalização outras etapas - Redirect retornado: {redirect_response is not None}")
    if redirect_response:
        return redirect_response, None, None

    return None, form, dependent_form


def _process_advance_step(request, form, current_step, steps):
    if _client_step_flag(current_step.boolean_field) == 'step_members':
        _add_debug_log(request, "Etapa 'Adicionar Membros' - permanecendo na mesma página para adicionar dependentes")
        return redirect(f"{request.path}?stage_id={current_step.pk}"), None, None

    _save_step_to_session(form, current_step, request)

    if redirect_response := _advance_to_next_step(current_step, steps, request.path, request):
        return redirect_response, None, None

    _add_debug_log(request, "Não há próxima etapa após avançar - finalizando cadastro automaticamente")
    try:
        client = _create_client_from_db(request)
        return _finalize_client_registration(request, client), None, None
    except ValueError as e:
        messages.error(request, str(e))
        _add_debug_log(request, f"Erro ao finalizar cadastro: {str(e)}", "error")
        return redirect("system:home_clients"), None, None


def _log_finalize_registration(request, current_step):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"Finalizar cadastro clicado - usuario={request.user.username} etapa={current_step.name} ts={timestamp}")


def _process_post_client_registration(request, current_step, steps, step_field_names):
    action = request.POST.get("action") or request.POST.get("acao", "save")
    form_type = request.POST.get("form_type", "")
    _add_debug_log(request, f"POST recebido - Ação: {action}, Form Type: {form_type}, Etapa: {current_step.name}")

    if action in ("finalize", "finalizar", "finalize_and_create_trip", "finalizar_e_create_trip"):
        _log_finalize_registration(request, current_step)

    if action in ("cancel", "cancelar"):
        return _process_registration_cancellation(request), None, None

    if action == "remove_dependent" and _client_step_flag(current_step.boolean_field) == 'step_members':
        return _process_remove_dependent(request, current_step), None, None

    if action == "edit_dependent":
        if _client_step_flag(current_step.boolean_field) == 'step_members':
            return _process_edit_dependent(request, current_step), None, None
        messages.error(request, "Ação inválida para esta etapa.")
        return redirect(f"{request.path}?stage_id={current_step.pk}"), None, None

    dependent_form = None
    temp_client = _create_client_from_session(request)

    if (
        _client_step_flag(current_step.boolean_field) == 'step_members'
        and temp_client
        and form_type == "dependent"
    ):
        redirect_response, dependent_form_result = _process_dependent_registration(
            request, current_step, temp_client, steps
        )
        if redirect_response:
            return redirect_response, None, None
        if dependent_form_result:
            dependent_form = dependent_form_result

    initial_data = _prepare_initial_form_data(request, temp_client)
    form = _create_client_form(request, current_step, initial_data)

    if redirect_response := _validate_previous_step(current_step, steps, request):
        return redirect_response, None, None

    if (
        _client_step_flag(current_step.boolean_field) == "step_members"
        and form_type == "dependent"
        and dependent_form is not None
        and dependent_form.errors
    ):
        return None, form, dependent_form

    if action in ("finalize", "finalizar", "finalize_and_create_trip", "finalizar_e_create_trip"):
        create_trip = action in ("finalize_and_create_trip", "finalizar_e_create_trip")
        _add_debug_log(request, f"Ação '{action}' detectada - processando finalização (create_trip={create_trip})")
        redirect_result = _process_finalization(request, form, current_step, steps, step_field_names, dependent_form, create_trip)
        return redirect_result

    next_step = steps.filter(order__gt=current_step.order).first()
    if not next_step and _client_step_flag(current_step.boolean_field) != 'step_members':
        _add_debug_log(request, "Última etapa detectada sem botão finalizar - processando finalização automaticamente")
        if form.is_valid():
            _save_step_to_session(form, current_step, request)
            try:
                client = _create_client_from_db(request)
                return _finalize_client_registration(request, client), None, None
            except ValueError as e:
                messages.error(request, str(e))
                _add_debug_log(request, f"Erro ao finalizar cadastro: {str(e)}", "error")
                return redirect("system:home_clients"), None, None

    if form.is_valid():
        return _process_advance_step(request, form, current_step, steps)

    _show_form_errors(request, form, step_field_names, step_name=current_step.name)
    return None, form, dependent_form


@login_required
def register_client_view(request):
    logger.info(f"View register_client_view chamada - Método: {request.method}, URL: {request.path}")

    consultant = get_user_consultant(request.user)
    _clear_finalization_flags(request)

    steps = ClientRegistrationStep.objects.filter(is_active=True).order_by("order", "name")
    if not steps.exists():
        messages.error(request, "Nenhuma etapa configurada. Configure as etapas primeiro.")
        return redirect("system:home_clients")

    step_id = request.GET.get("stage_id")
    current_step = _get_current_step(steps, step_id)

    step_fields = ClientStepField.objects.filter(
        step=current_step, is_active=True
    ).order_by("order", "field_name")

    step_field_names = {_client_step_form_field_name(f.field_name) for f in step_fields}
    has_zip_in_step = 'zip_code' in step_field_names
    has_password_in_step = 'password' in step_field_names

    if request.method == "POST":
        redirect_response, form, dependent_form = _process_post_client_registration(
            request, current_step, steps, step_field_names
        )
        if redirect_response:
            logger.info(f"Redirect recebido: {redirect_response.url if hasattr(redirect_response, 'url') else redirect_response}")
            return redirect_response
    else:
        temp_client = _create_client_from_session(request)
        initial_data = _prepare_initial_form_data(request, temp_client)
        form = _create_get_form(request, current_step, initial_data)
        dependent_form = None

    temp_client = _create_client_from_session(request)
    context = _prepare_context(
        steps, current_step, step_fields, form, temp_client, consultant
    )
    context = _prepare_final_context(
        request, current_step, temp_client, steps, context, dependent_form,
        has_zip_in_step, has_password_in_step
    )

    return render(request, "client/register_client.html", context)


@login_required
def view_client(request, pk: int):
    consultant = get_user_consultant(request.user)
    client = get_object_or_404(
        ConsultancyClient.objects.select_related(
            "assigned_advisor",
            "assigned_advisor__profile",
        ),
        pk=pk,
    )

    can_view = user_can_manage_all(request.user, consultant) or (
        consultant and client.assigned_advisor_id == consultant.pk
        or client.created_by == request.user
    )

    if not can_view:
        raise PermissionDenied

    trips = Trip.objects.filter(
        clients=client
    ).select_related(
        "destination_country",
        "visa_type",
        "assigned_advisor",
    ).prefetch_related("clients").order_by("-planned_departure_date")

    processes = Process.objects.filter(
        client=client
    ).select_related(
        "trip",
        "trip__destination_country",
        "trip__visa_type",
        "assigned_advisor",
    ).prefetch_related("stages", "stages__status").order_by("-created_at")

    financial_records = FinancialRecord.objects.filter(
        client=client
    ).select_related(
        "trip",
        "assigned_advisor",
    ).order_by("-created_at")

    financial_status = _get_client_financial_status(client)

    reminders = Reminder.objects.filter(client=client).select_related("created_by").order_by("completed", "-created_at")

    linked_clients = []
    if client.primary_client:
        principal = ConsultancyClient.objects.select_related("assigned_advisor").get(pk=client.primary_client_id)
        linked_clients.append({"client": principal, "relacao": "Principal"})
        for dep in principal.dependents.select_related("assigned_advisor").exclude(pk=client.pk):
            linked_clients.append({"client": dep, "relacao": "Dependente"})
    else:
        for dep in client.dependents.select_related("assigned_advisor").all():
            linked_clients.append({"client": dep, "relacao": "Dependente"})

    context = {
        "client": client,
        "trips": trips,
        "processes": processes,
        "financial_records": financial_records,
        "financial_status": financial_status,
        "clean_notes": strip_legacy_meta(client.notes),
        "legacy_meta": _legacy_meta_from_client(client),
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": user_can_manage_all(request.user, consultant),
        "can_edit": can_view,
        "reminders": reminders,
        "linked_clients": linked_clients,
    }

    return render(request, "client/view_client.html", context)


@login_required
def edit_client_view(request, pk: int):
    consultant = get_user_consultant(request.user)
    client = get_object_or_404(
        ConsultancyClient.objects.select_related(
            "assigned_advisor",
        ),
        pk=pk,
    )

    can_edit = user_can_manage_all(request.user, consultant) or (
        consultant and client.assigned_advisor_id == consultant.pk
        or client.created_by == request.user
    )

    if not can_edit:
        raise PermissionDenied

    if request.method == "POST":
        legacy_meta = extract_legacy_meta(client.notes)
        form = ConsultancyClientForm(data=request.POST, user=request.user, instance=client)
        form.fields["password"].required = False
        form.fields["confirm_password"].required = False

        if form.is_valid():
            updated_client = form.save()
            if legacy_meta.get("imported"):
                updated_client.notes = upsert_legacy_meta(
                    updated_client.notes,
                    legacy_meta,
                )
                updated_client.save(update_fields=["notes", "updated_at"])
            messages.success(request, f"{updated_client.first_name} atualizado com sucesso.")
            return redirect("system:list_clients_view")
        messages.error(request, "Não foi possível atualizar o cliente. Verifique os campos.")
    else:
        form = ConsultancyClientForm(user=request.user, instance=client)
        form.fields["password"].required = False
        form.fields["password"].widget.attrs["placeholder"] = "Deixe em branco para manter a senha atual"
        form.fields["confirm_password"].required = False
        form.fields["confirm_password"].widget.attrs["placeholder"] = "Deixe em branco para manter a senha atual"
        if client.referring_partner:
            form.fields["referring_partner"].initial = client.referring_partner.pk
        if "notes" in form.fields:
            form.fields["notes"].initial = strip_legacy_meta(client.notes)

    context = {
        "form": form,
        "client": client,
        "legacy_meta": _legacy_meta_from_client(client),
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "client/edit_client.html", context)


@login_required
@require_GET
def api_search_zip(request):
    zip_code = (
        request.GET.get("zip_code", "")
        or request.GET.get("cep", "")
    ).strip()

    if not zip_code:
        return JsonResponse({"error": "Informe um CEP."}, status=400)

    try:
        address = fetch_address_by_zip(zip_code)
        return JsonResponse(address)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_GET
def api_client_data(request):
    client_id = request.GET.get("client_id")

    if not client_id:
        return JsonResponse({"error": "ID do cliente não informado."}, status=400)

    try:
        client = ConsultancyClient.objects.get(pk=client_id)
        base_date = client.created_at.date().isoformat()
        response_data = {
            "base_date": base_date,
            "client": {
                "name": client.full_name,
            },
        }
        return JsonResponse(response_data)
    except ConsultancyClient.DoesNotExist:
        return JsonResponse({"error": "Cliente não encontrado."}, status=404)


def _mask_passport_for_log(passport_number: str | None) -> str:
    if not passport_number:
        return "***"
    cleaned = re.sub(r"\W", "", str(passport_number))
    if len(cleaned) <= 3:
        return "***"
    return f"***{cleaned[-3:]}"


@login_required
@require_http_methods(["POST"])
def api_extract_passport(request):
    document = request.FILES.get("documento")
    if not document:
        return JsonResponse({"success": False, "error": "Envie um documento para extração."}, status=400)

    if document.size > 10 * 1024 * 1024:
        return JsonResponse({"success": False, "error": "Arquivo muito grande. Limite de 10MB."}, status=400)

    target = request.POST.get("target", "client").strip().lower() or "client"
    persist_in_session = request.POST.get("persist_in_session", "false").lower() == "true"

    try:
        extraction = extract_passport_data_from_document(document)
    except PassportExtractionError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    except Exception:
        logger.exception("Falha inesperada ao extrair OCR de passaporte.")
        return JsonResponse({"success": False, "error": "Falha interna ao processar o documento."}, status=500)

    fields = extraction.get("fields", {})
    warnings = extraction.get("warnings", [])
    if persist_in_session:
        request.session[f"passport_ocr_{target}"] = fields
        if target == "client":
            temp_data = request.session.get("client_temp_data", {})
            temp_data.update({k: v for k, v in fields.items() if v})
            request.session["client_temp_data"] = temp_data
        request.session.modified = True

    logger.info(
        "OCR passaporte concluído target=%s numero=%s campos=%s",
        target,
        _mask_passport_for_log(fields.get("passport_number")),
        ",".join(sorted(fields.keys())),
    )
    return JsonResponse({"success": True, "fields": fields, "warnings": warnings})


@login_required
def register_dependent(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    primary_client = get_object_or_404(ConsultancyClient, pk=pk)

    if not can_manage_all and (not consultant or primary_client.assigned_advisor_id != consultant.pk):
        raise PermissionDenied("Você não tem permissão para gerenciar este cliente.")

    first_step = ClientRegistrationStep.objects.filter(is_active=True).order_by("order").first()
    if not first_step:
        messages.error(request, "Nenhuma etapa configurada. Configure as etapas primeiro.")
        return redirect("system:home_clients")

    step_fields = ClientStepField.objects.filter(
        step=first_step, is_active=True
    ).exclude(field_name="referring_partner").order_by("order", "field_name")

    if request.method == "POST":
        if (action := request.POST.get("action") or request.POST.get("acao", "save")) in ("finalize", "finalizar"):
            messages.success(request, "Cadastro de dependentes finalizado.")
            return redirect("system:home_clients")

        steps = ClientRegistrationStep.objects.filter(is_active=True).order_by("order")
        form = _prepare_dependent_post_form(request, first_step, steps, primary_client=primary_client)

        if form.is_valid():
            use_primary_data = request.POST.get('use_primary_data') == 'on'
            _save_dependent(form, primary_client, first_step, request.user, use_primary_data=use_primary_data)
            messages.success(request, f"{form.cleaned_data['first_name']} cadastrado como dependente com sucesso.")
            return redirect("system:register_dependent", pk=primary_client.pk)

        step_field_names = {
            _client_step_form_field_name(field_name)
            for field_name in step_fields.values_list("field_name", flat=True)
        }
        _show_form_errors(
            request,
            form,
            step_field_names,
            step_name=f"Dependente - {first_step.name}",
        )
    else:
        steps = ClientRegistrationStep.objects.filter(is_active=True).order_by("order")
        form = _create_dependent_form(request, primary_client, first_step, steps)

    advisor_id = None
    if primary_client.assigned_advisor:
        advisor_id = primary_client.assigned_advisor.pk
    elif consultant:
        advisor_id = consultant.pk

    context = {
        "primary_client": primary_client,
        "form": form,
        "current_stage": first_step,
        "stage_fields": step_fields,
        "dependents": primary_client.dependents.all().order_by("first_name"),
        "user_profile": consultant.profile.name if consultant else None,
        "advisor_id": advisor_id,
    }

    return render(request, "client/register_dependent.html", context)


@login_required
def add_dependent(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    primary_client = get_object_or_404(ConsultancyClient, pk=pk)

    if not can_manage_all and (not consultant or primary_client.assigned_advisor_id != consultant.pk):
        raise PermissionDenied("Você não tem permissão para gerenciar este cliente.")

    if request.method == "POST":
        if dependent_id := request.POST.get("dependent_id"):
            try:
                dependent = ConsultancyClient.objects.get(pk=dependent_id)
                if dependent.primary_client:
                    messages.error(request, "Este cliente já é dependente de outro cliente.")
                elif dependent.pk == primary_client.pk:
                    messages.error(request, "Um cliente não pode ser dependente de si mesmo.")
                else:
                    dependent.primary_client = primary_client
                    dependent.save()
                    messages.success(request, f"{dependent.first_name} adicionado como dependente.")
                    return redirect("system:edit_client", pk=primary_client.pk)
            except ConsultancyClient.DoesNotExist:
                messages.error(request, "Cliente não encontrado.")

    available_clients = ConsultancyClient.objects.filter(
        primary_client__isnull=True
    ).exclude(pk=primary_client.pk).order_by("first_name")

    context = {
        "primary_client": primary_client,
        "available_clients": available_clients,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "client/add_dependent.html", context)


@login_required
@require_http_methods(["POST"])
def remove_dependent(request, pk: int, dependent_id: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    primary_client = get_object_or_404(ConsultancyClient, pk=pk)
    dependent = get_object_or_404(ConsultancyClient, pk=dependent_id)

    if not can_manage_all and (not consultant or primary_client.assigned_advisor_id != consultant.pk):
        raise PermissionDenied("Você não tem permissão para gerenciar este cliente.")

    if dependent.primary_client != primary_client:
        messages.error(request, "Este cliente não é dependente do cliente selecionado.")
        return redirect("system:edit_client", pk=primary_client.pk)

    dependent_name = dependent.first_name
    dependent.primary_client = None
    dependent.save()

    messages.success(request, f"{dependent_name} removido como dependente.")
    return redirect("system:edit_client", pk=primary_client.pk)


@login_required
@require_http_methods(["POST"])
def create_reminder(request, client_id: int):
    consultant = get_user_consultant(request.user)
    client = get_object_or_404(ConsultancyClient, pk=client_id)

    allowed = user_can_manage_all(request.user, consultant) or (
        consultant and client.assigned_advisor_id == consultant.pk
    )
    if not allowed:
        raise PermissionDenied

    text = (request.POST.get("text") or request.POST.get("texto", "")).strip()
    reminder_date = request.POST.get("reminder_date") or None

    if not text:
        messages.error(request, "O texto do lembrete é obrigatório.")
        return redirect("system:view_client", pk=client_id)

    Reminder.objects.create(
        client=client,
        text=text,
        reminder_date=reminder_date,
        created_by=consultant,
    )
    messages.success(request, "Lembrete adicionado.")
    return redirect("system:view_client", pk=client_id)


@login_required
@require_http_methods(["POST"])
def toggle_reminder(request, pk: int):
    consultant = get_user_consultant(request.user)
    reminder = get_object_or_404(Reminder.objects.select_related("client"), pk=pk)
    client = reminder.client

    allowed = user_can_manage_all(request.user, consultant) or (
        consultant and client.assigned_advisor_id == consultant.pk
    )
    if not allowed:
        raise PermissionDenied

    reminder.completed = not reminder.completed
    reminder.save(update_fields=["completed"])
    return redirect("system:view_client", pk=client.pk)


@login_required
@require_http_methods(["POST"])
def delete_reminder(request, pk: int):
    consultant = get_user_consultant(request.user)
    reminder = get_object_or_404(Reminder.objects.select_related("client"), pk=pk)
    client = reminder.client

    allowed = user_can_manage_all(request.user, consultant) or (
        consultant and client.assigned_advisor_id == consultant.pk
    )
    if not allowed:
        raise PermissionDenied

    reminder.delete()
    messages.success(request, "Lembrete excluído.")
    return redirect("system:view_client", pk=client.pk)
