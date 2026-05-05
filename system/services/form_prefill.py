from decimal import Decimal, InvalidOperation

from system.models import FormAnswer, SelectOption
from system.services.form_prefill_rules import get_client_prefill_field, normalize_text


PASSPORT_TYPE_LABELS = {
    "regular": "Passaporte Comum/Regular",
    "diplomatic": "Passaporte Diplomático",
    "service": "Passaporte de Serviço",
    "other": "Outro",
}


def _join_non_empty(parts, separator):
    return separator.join(str(part).strip() for part in parts if str(part or "").strip())


def _build_street_address(client):
    return _join_non_empty([client.street, client.street_number, client.complement], ", ")


def _build_full_address(client):
    street = _build_street_address(client)
    city_state = _join_non_empty([client.city, client.state], " - ")
    return _join_non_empty([street, client.district, city_state, client.zip_code], ", ")


def _prefill_raw_value(question_text, client):
    field_name = get_client_prefill_field(question_text)
    if not field_name:
        return None

    if field_name == "first_name":
        return client.first_name
    if field_name == "last_name":
        return client.last_name
    if field_name == "cpf":
        return client.cpf
    if field_name == "email":
        return client.email
    if field_name == "phone":
        return client.phone
    if field_name == "secondary_phone":
        return client.secondary_phone
    if field_name == "birth_date":
        return client.birth_date
    if field_name == "nationality":
        return client.nationality
    if field_name == "full_address":
        return _build_full_address(client)
    if field_name == "street_address":
        return _build_street_address(client)
    if field_name == "district":
        return client.district
    if field_name == "zip_code":
        return client.zip_code
    if field_name == "city":
        return client.city
    if field_name == "state":
        return client.state
    if field_name == "city_state":
        return _join_non_empty([client.city, client.state], " - ")
    if field_name == "passport_type":
        return PASSPORT_TYPE_LABELS.get(client.passport_type, client.passport_type)
    if field_name == "passport_number":
        return client.passport_number
    if field_name == "passport_issuing_country":
        return client.passport_issuing_country
    if field_name == "passport_issue_date":
        return client.passport_issue_date
    if field_name == "passport_expiry_date":
        return client.passport_expiry_date
    if field_name == "passport_authority":
        return client.passport_authority
    if field_name == "passport_issuing_city":
        return client.passport_issuing_city
    if field_name == "passport_stolen":
        return "sim" if client.passport_stolen else "nao"
    return None


def _assign_prefill_value(answer, question, raw_value):
    answer.answer_text = ""
    answer.answer_date = None
    answer.answer_number = None
    answer.answer_boolean = None
    answer.answer_select = None

    if question.field_type == "text":
        answer.answer_text = str(raw_value)
        return True
    if question.field_type == "date":
        if hasattr(raw_value, "year"):
            answer.answer_date = raw_value
            return True
        return False
    if question.field_type == "number":
        try:
            answer.answer_number = Decimal(str(raw_value))
            return True
        except (InvalidOperation, ValueError):
            return False
    if question.field_type == "boolean":
        token = normalize_text(raw_value)
        if token in {"sim", "true", "1", "yes"}:
            answer.answer_boolean = True
            return True
        if token in {"nao", "false", "0", "no"}:
            answer.answer_boolean = False
            return True
        return False
    if question.field_type == "select":
        target = normalize_text(raw_value)
        for option in SelectOption.objects.filter(question=question, is_active=True).order_by("order"):
            if normalize_text(option.text) == target:
                answer.answer_select = option
                return True
        return False
    return False


def _answer_has_value(answer):
    return (
        bool(answer.answer_text)
        or answer.answer_date is not None
        or answer.answer_number is not None
        or answer.answer_boolean is not None
        or answer.answer_select_id is not None
    )


def _direct_prefill_values(client):
    return {
        "first_name": client.first_name,
        "last_name": client.last_name,
        "cpf": client.cpf,
        "email": client.email,
        "phone": client.phone,
        "secondary_phone": client.secondary_phone,
        "birth_date": client.birth_date,
        "nationality": client.nationality,
        "full_address": _build_full_address(client),
        "street_address": _build_street_address(client),
        "district": client.district,
        "zip_code": client.zip_code,
        "city": client.city,
        "state": client.state,
        "city_state": _join_non_empty([client.city, client.state], " - "),
    }


def _answer_display_token(answer):
    return normalize_text(answer.get_answer_display())


def _sync_existing_prefill_answers(trip, client, existing_answers):
    updated = False
    direct_values = _direct_prefill_values(client)
    direct_value_tokens = {
        normalize_text(value)
        for value in direct_values.values()
        if value not in (None, "")
    }

    for question_id, answer in list(existing_answers.items()):
        if not _answer_has_value(answer):
            continue

        prefill_field = get_client_prefill_field(answer.question.question)
        if prefill_field:
            raw_value = _prefill_raw_value(answer.question.question, client)
            if raw_value in (None, ""):
                continue
            current_token = _answer_display_token(answer)
            expected_token = normalize_text(raw_value)
            if current_token != expected_token and _assign_prefill_value(
                answer,
                answer.question,
                raw_value,
            ):
                answer.save()
                updated = True
            continue

        if _answer_display_token(answer) in direct_value_tokens:
            answer.delete()
            existing_answers.pop(question_id, None)
            updated = True

    return updated


def prefill_form_answers(trip, client, questions, existing_answers):
    updated = _sync_existing_prefill_answers(trip, client, existing_answers)
    used_fields = {
        get_client_prefill_field(answer.question.question)
        for answer in existing_answers.values()
        if _answer_has_value(answer)
    }
    used_fields.discard(None)
    for question in questions:
        if question.pk in existing_answers:
            continue
        prefill_field = get_client_prefill_field(question.question)
        if not prefill_field or prefill_field in used_fields:
            continue
        if prefill_field == "full_address" and {
            "street_address",
            "district",
            "zip_code",
            "city_state",
        } & used_fields:
            continue
        raw_value = _prefill_raw_value(question.question, client)
        if raw_value in (None, ""):
            continue
        answer = FormAnswer(trip=trip, client=client, question=question)
        if not _assign_prefill_value(answer, question, raw_value):
            continue
        answer.save()
        existing_answers[question.pk] = answer
        used_fields.add(prefill_field)
        updated = True
    return updated, existing_answers
