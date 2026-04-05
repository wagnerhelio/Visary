import logging
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_date

from system.models import FormAnswer, SelectOption

logger = logging.getLogger("visary.forms")


def clear_answer_fields(answer):
    answer.answer_text = ""
    answer.answer_date = None
    answer.answer_number = None
    answer.answer_boolean = None
    answer.answer_select = None


def update_answer_by_type(answer, question, value):
    clear_answer_fields(answer)
    field_type = question.field_type

    if field_type == "text":
        answer.answer_text = value or ""
    elif field_type == "date":
        if value:
            parsed = parse_date(value)
            if parsed is None:
                raise ValueError(
                    f"Data inválida para a pergunta '{question.question}'. Use o formato AAAA-MM-DD."
                )
            answer.answer_date = parsed
    elif field_type == "number":
        if value:
            try:
                answer.answer_number = Decimal(value)
            except (InvalidOperation, ValueError) as e:
                raise ValueError(
                    f"Valor numérico inválido para a pergunta '{question.question}'."
                ) from e
    elif field_type == "boolean":
        answer.answer_boolean = (value == "sim") if value else None
    elif field_type == "select":
        if value:
            try:
                option_id = int(value)
                answer.answer_select = SelectOption.objects.get(pk=option_id, question=question)
            except (ValueError, SelectOption.DoesNotExist) as e:
                raise ValueError(
                    f"Opção inválida para a pergunta '{question.question}'."
                ) from e


def build_question_state(questions, post_dict, existing_answers):
    state = {}
    for q in questions:
        if q.field_type == "boolean":
            val = post_dict.get(f"question_{q.pk}", "")
            if val in ("sim", "nao"):
                state[q.order] = val
            elif q.pk in existing_answers:
                r = existing_answers[q.pk]
                if r.answer_boolean is True:
                    state[q.order] = "sim"
                elif r.answer_boolean is False:
                    state[q.order] = "nao"
        elif q.field_type == "select":
            val = post_dict.get(f"question_{q.pk}", "")
            if val:
                try:
                    option = SelectOption.objects.filter(pk=int(val), question=q).first()
                    state[q.order] = option.text if option else val
                except ValueError:
                    state[q.order] = val
            elif q.pk in existing_answers:
                r = existing_answers[q.pk]
                if r.answer_select_id:
                    state[q.order] = r.answer_select.text
        else:
            val = post_dict.get(f"question_{q.pk}", "")
            if not val and q.pk in existing_answers:
                val = existing_answers[q.pk].answer_text or ""
            state[q.order] = val
    return state


def is_question_visible(question, state):
    rule = question.display_rule
    if not rule:
        return True
    if rule.get("type") != "show_if":
        return True
    target_order = rule.get("question_order")
    expected_values = rule.get("value")
    if target_order is None or expected_values is None:
        return True
    if isinstance(expected_values, list):
        return state.get(target_order) in expected_values
    return state.get(target_order) == expected_values


def process_form_answers(post_dict, trip, client, questions, existing_answers=None):
    saved_count = 0
    errors = []
    existing_answers = existing_answers or {}
    state = build_question_state(questions, post_dict, existing_answers)

    with transaction.atomic():
        for question in questions:
            field_name = f"question_{question.pk}"
            value = post_dict.get(field_name)

            if question.is_required and not value and is_question_visible(question, state):
                errors.append(f"A pergunta '{question.question}' é obrigatória.")
                continue

            sid = transaction.savepoint()
            try:
                answer, _ = FormAnswer.objects.get_or_create(
                    trip=trip, client=client, question=question, defaults={}
                )
                update_answer_by_type(answer, question, value)
                answer.save()
                saved_count += 1
                transaction.savepoint_commit(sid)
            except IntegrityError:
                transaction.savepoint_rollback(sid)
                sid2 = transaction.savepoint()
                try:
                    answer = FormAnswer.objects.get(trip=trip, client=client, question=question)
                    update_answer_by_type(answer, question, value)
                    answer.save()
                    saved_count += 1
                    transaction.savepoint_commit(sid2)
                except Exception as e:
                    transaction.savepoint_rollback(sid2)
                    logger.exception(
                        "Erro ao salvar resposta (pergunta pk=%s, viagem pk=%s, cliente pk=%s)",
                        question.pk, trip.pk, client.pk,
                    )
                    errors.append(str(e))
            except ValueError as e:
                transaction.savepoint_rollback(sid)
                errors.append(str(e))

    return saved_count, errors
