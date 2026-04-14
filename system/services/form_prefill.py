from decimal import Decimal, InvalidOperation

from system.models import FormAnswer, SelectOption
from system.services.form_prefill_rules import normalize_text, should_prefill_from_client


def _question_is_stage_one(question):
    return bool(question.stage_id and question.stage and question.stage.order == 1)


def _build_full_address(client):
    parts = []
    street_line = " ".join(
        p for p in [client.street, client.street_number] if p
    ).strip()
    if street_line:
        parts.append(street_line)
    if client.complement:
        parts.append(client.complement)
    if client.district:
        parts.append(client.district)
    city_state = " / ".join(p for p in [client.city, client.state] if p).strip()
    if city_state:
        parts.append(city_state)
    if client.zip_code:
        parts.append(f"CEP {client.zip_code}")
    return ", ".join(parts).strip()


def _prefill_raw_value(question_text, client):
    q = normalize_text(question_text)
    if not should_prefill_from_client(q):
        return None

    if q in {"nome", "primeiro nome"}:
        return client.first_name
    if q == "sobrenome":
        return client.last_name
    if q == "nome completo":
        return client.full_name
    if q == "cpf":
        return client.cpf
    if q in {"email", "e mail"}:
        return client.email
    if q in {
        "telefone",
        "telefone primario",
        "telefone principal",
        "telefone celular",
        "telefone residencial",
    }:
        return client.phone
    if q == "telefone secundario":
        return client.secondary_phone
    if "data de nascimento" in q:
        return client.birth_date
    if "nacionalidade" in q:
        return client.nationality

    if "cep" in q:
        return client.zip_code
    if "logradouro" in q:
        return client.street
    if q in {"numero", "numero da casa"}:
        return client.street_number
    if "complemento" in q:
        return client.complement
    if "bairro" in q:
        return client.district
    if "cidade e estado em que reside" in q:
        return " / ".join(p for p in [client.city, client.state] if p)
    if "endereco" in q:
        return _build_full_address(client)

    if "tipo de passaporte" in q:
        return client.passport_type_other or client.passport_type
    if "numero" in q and "passaporte" in q:
        return client.passport_number
    if (
        "pais que emitiu" in q
        or "pais referente" in q
        or "pais emissor" in q
    ):
        return client.passport_issuing_country
    if "data de emissao" in q:
        return client.passport_issue_date
    if "data de validade" in q or "data de expiracao" in q or "valido ate" in q:
        return client.passport_expiry_date
    if "cidade de emissao" in q:
        return client.passport_issuing_city
    if "local de emissao" in q or "autoridade" in q or "orgao emissor" in q:
        return client.passport_authority
    if "roubado" in q and "passaporte" in q:
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
        if not _question_is_stage_one(question):
            continue
        raw_value = _prefill_raw_value(question.question, client)
        if raw_value in (None, ""):
            continue
        answer = FormAnswer(trip=trip, client=client, question=question)
        if not _assign_prefill_value(answer, question, raw_value):
            continue
        answer.save()
        existing_answers[question.pk] = answer
        updated = True
    return updated, existing_answers
