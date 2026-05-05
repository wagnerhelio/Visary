import json
import re
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from system.models import (
    FormQuestion,
    SelectOption,
    VisaForm,
    VisaFormStage,
    VisaType,
)

DISPLAY_RULE_KEY_MAP = {
    "tipo": "type",
    "mostrar_se": "show_if",
    "pergunta_ordem": "question_order",
    "valor": "value",
    "campo_trigger": "trigger_field",
}


def _translate_display_rule(rule):
    if not rule or not isinstance(rule, dict):
        return rule
    translated = {}
    for key, val in rule.items():
        new_key = DISPLAY_RULE_KEY_MAP.get(key, key)
        if new_key == "type" and isinstance(val, str):
            val = DISPLAY_RULE_KEY_MAP.get(val, val)
        translated[new_key] = val
    return translated


FIELD_TYPE_MAP = {
    "texto": "text",
    "data": "date",
    "numero": "number",
    "booleano": "boolean",
    "selecao": "select",
}


class Command(BaseCommand):
    help = "Popula formularios de visto a partir de static/forms_ini"

    def add_arguments(self, parser):
        parser.add_argument("--visa-type", help="Nome exato do tipo de visto")
        parser.add_argument("--file", help="Nome do arquivo JSON em static/forms_ini")

    def handle(self, *args, **options):
        call_command("seed_visa_types")

        forms_dir = Path(settings.BASE_DIR) / "static" / "forms_ini"
        if not forms_dir.exists():
            raise CommandError(f"Diretorio nao encontrado: {forms_dir}")

        types_by_name = {
            self._normalize(vt.name): vt
            for vt in VisaType.objects.select_related("destination_country")
        }

        type_filter = (options.get("visa_type") or "").strip()
        file_filter = (options.get("file") or "").strip()

        files = sorted(forms_dir.glob("*.json"))
        if file_filter:
            files = [f for f in files if f.name == file_filter]
            if not files:
                raise CommandError(f"Arquivo nao encontrado em forms_ini: {file_filter}")

        for json_file in files:
            payload = json.loads(json_file.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                continue

            for form_item in payload:
                vt_name = form_item.get("tipo_visto", "").strip()
                if type_filter and vt_name != type_filter:
                    continue

                visa_type = types_by_name.get(self._normalize(vt_name))
                if not visa_type:
                    raise CommandError(f"Tipo de visto nao encontrado para formulario: {vt_name}")

                form, _ = VisaForm.objects.get_or_create(visa_type=visa_type)
                form.is_active = True
                form.save(update_fields=["is_active", "updated_at"])

                self._sync_stages(form, form_item, json_file)
                stage_map = {
                    s.order: s
                    for s in VisaFormStage.objects.filter(form=form, is_active=True)
                }
                self._sync_questions(form, form_item, stage_map, json_file)

        self.stdout.write(self.style.SUCCESS("Seed de formularios de visto concluida."))

    def _sync_stages(self, form, form_item, json_file):
        stages = form_item.get("etapas")
        if not isinstance(stages, list) or not stages:
            raise CommandError(
                f"Formulario sem matriz de etapas em {json_file.name}: "
                f"{form_item.get('tipo_visto', '')}"
            )

        active_orders = set()
        for stage_item in stages:
            try:
                order = int(stage_item.get("ordem", stage_item.get("order")))
            except (TypeError, ValueError) as exc:
                raise CommandError(
                    f"Etapa com ordem invalida em {json_file.name}: {stage_item}"
                ) from exc

            name = str(stage_item.get("nome", stage_item.get("name", ""))).strip()
            if not name:
                raise CommandError(
                    f"Etapa sem nome em {json_file.name}, ordem {order}."
                )

            is_active = stage_item.get("ativo", stage_item.get("is_active", True))
            stage, created = VisaFormStage.objects.get_or_create(
                form=form,
                order=order,
                defaults={"name": name},
            )
            changed_fields = []
            if not created and stage.name != name:
                stage.name = name
                changed_fields.append("name")
            if stage.is_active != is_active:
                stage.is_active = is_active
                changed_fields.append("is_active")
            if changed_fields:
                changed_fields.append("updated_at")
                stage.save(update_fields=changed_fields)
            if is_active:
                active_orders.add(order)

        VisaFormStage.objects.filter(form=form).exclude(
            order__in=active_orders
        ).update(is_active=False)

    def _sync_questions(self, form, form_item, stage_map, json_file):
        existing_questions = list(
            FormQuestion.objects.filter(form=form).order_by("order", "pk")
        )
        questions_by_text = {}
        for existing_question in existing_questions:
            questions_by_text.setdefault(
                self._normalize(existing_question.question), []
            ).append(existing_question)

        temporary_order_start = (
            max([q.order for q in existing_questions], default=0) + 10000
        )
        for offset, existing_question in enumerate(existing_questions, start=1):
            existing_question.order = temporary_order_start + offset
            existing_question.save(update_fields=["order", "updated_at"])

        active_question_pks = set()
        for q_item in form_item.get("perguntas", []):
            stage_order = q_item.get("etapa")
            if stage_order:
                try:
                    stage_order = int(stage_order)
                except (TypeError, ValueError) as exc:
                    raise CommandError(
                        f"Pergunta {q_item.get('ordem')} tem etapa invalida "
                        f"em {json_file.name}: {q_item.get('etapa')}"
                    ) from exc
            stage_obj = stage_map.get(stage_order) if stage_order else None
            if stage_order and not stage_obj:
                raise CommandError(
                    f"Pergunta {q_item.get('ordem')} referencia etapa inexistente "
                    f"{stage_order} em {json_file.name}."
                )

            raw_type = q_item["tipo_campo"]
            field_type = FIELD_TYPE_MAP.get(raw_type, raw_type)

            question_key = self._normalize(q_item["pergunta"])
            question_matches = questions_by_text.get(question_key, [])
            question = question_matches.pop(0) if question_matches else None
            if question is None:
                question = FormQuestion(form=form, order=q_item["ordem"])

            question.order = q_item["ordem"]
            question.question = q_item["pergunta"]
            question.field_type = field_type
            question.is_required = q_item.get("obrigatorio", False)
            question.is_active = q_item.get("ativo", True)
            display_rule = _translate_display_rule(q_item.get("regra_exibicao"))
            ref_id = q_item.get("ref_id")
            if ref_id:
                if isinstance(display_rule, dict):
                    display_rule = {**display_rule, "ref_id": str(ref_id)}
                else:
                    display_rule = {"ref_id": str(ref_id)}
            question.display_rule = display_rule
            question.stage = stage_obj
            question.save()
            active_question_pks.add(question.pk)

            if field_type != "select":
                SelectOption.objects.filter(question=question).update(is_active=False)
                continue

            active_option_orders = set()
            for order, text in enumerate(q_item.get("opcoes", []), start=1):
                option, _ = SelectOption.objects.get_or_create(
                    question=question, order=order
                )
                option.text = text
                option.is_active = True
                option.save()
                active_option_orders.add(order)

            SelectOption.objects.filter(question=question).exclude(
                order__in=active_option_orders
            ).update(is_active=False)

        FormQuestion.objects.filter(form=form).exclude(
            pk__in=active_question_pks
        ).update(is_active=False)

    def _normalize(self, value):
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = text.encode("ascii", "ignore").decode("ascii")
        text = text.lower().strip()
        return re.sub(r"[^a-z0-9]+", "", text)
