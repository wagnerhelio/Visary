import re
import unicodedata
from decimal import Decimal, InvalidOperation

from system.models import FormAnswer, SelectOption


def normalize_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _prefill_raw_value(question, client):
    q = normalize_text(question.question)
    values = [
        ("cpf", client.cpf),
        ("email", client.email),
        ("telefone secundario", client.secondary_phone),
        ("telefone", client.phone),
        ("cep", client.zip_code),
        ("logradouro", client.street),
        ("endereco", client.street),
        ("numero", client.street_number),
        ("complemento", client.complement),
        ("bairro", client.district),
        ("cidade emissao", client.passport_issuing_city),
        ("cidade", client.city),
        ("estado", client.state),
        ("uf", client.state),
        ("data de nascimento", client.birth_date),
        ("nacionalidade", client.nationality),
        ("sobrenome", client.last_name),
        ("nome completo", client.full_name),
        ("nome", client.first_name),
        ("tipo de passaporte", client.passport_type_other or client.passport_type),
        ("numero do passaporte", client.passport_number),
        ("pais emissor", client.passport_issuing_country),
        ("data emissao", client.passport_issue_date),
        ("data validade", client.passport_expiry_date),
        ("valido ate", client.passport_expiry_date),
        ("autoridade", client.passport_authority),
        ("orgao emissor", client.passport_authority),
    ]
    for key, value in values:
        if key in q and value not in (None, ""):
            return value
    if "passaporte roubado" in q:
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


def prefill_form_answers(trip, client, questions, existing_answers):
    updated = False
    for question in questions:
        if question.pk in existing_answers:
            continue
        raw_value = _prefill_raw_value(question, client)
        if raw_value in (None, ""):
            continue
        answer = FormAnswer(trip=trip, client=client, question=question)
        if not _assign_prefill_value(answer, question, raw_value):
            continue
        answer.save()
        existing_answers[question.pk] = answer
        updated = True
    return updated, existing_answers
