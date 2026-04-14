from decimal import Decimal, InvalidOperation

from system.models import FormAnswer, SelectOption
from system.services.form_prefill_rules import get_client_prefill_field, normalize_text


def _question_is_stage_one(question):
    return bool(question.stage_id and question.stage and question.stage.order == 1)


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


def prefill_form_answers(trip, client, questions, existing_answers):
    updated = False
    used_fields = {
        get_client_prefill_field(answer.question.question)
        for answer in existing_answers.values()
        if _answer_has_value(answer)
    }
    used_fields.discard(None)
    for question in questions:
        if question.pk in existing_answers:
            continue
        if not _question_is_stage_one(question):
            continue
        prefill_field = get_client_prefill_field(question.question)
        if not prefill_field or prefill_field in used_fields:
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
