import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from system.models import ClientRegistrationStep, ClientStepField

FIELD_TYPE_MAP = {
    "texto": "text",
    "data": "date",
    "numero": "number",
    "booleano": "boolean",
    "selecao": "select",
}

DISPLAY_RULE_KEY_MAP = {
    "tipo": "type",
    "mostrar_se": "show_if",
    "campo_trigger": "trigger_field",
    "valor": "value",
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


class Command(BaseCommand):
    help = "Popula etapas de cadastro de cliente a partir de static/etapas_cliente_ini"

    def add_arguments(self, parser):
        parser.add_argument("--name", help="Nome de uma etapa especifica")

    def handle(self, *args, **options):
        steps_dir = Path(settings.BASE_DIR) / "static" / "etapas_cliente_ini"
        if not steps_dir.exists():
            raise CommandError(f"Diretorio nao encontrado: {steps_dir}")

        name_filter = (options.get("name") or "").strip().lower()

        for json_file in sorted(steps_dir.glob("*.json")):
            payload = json.loads(json_file.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                continue

            for step_item in payload:
                step_name = step_item["nome"].strip()
                if name_filter and step_name.lower() != name_filter:
                    continue

                step, _ = ClientRegistrationStep.objects.get_or_create(name=step_name)
                step.description = step_item.get("descricao", "")
                step.order = step_item.get("ordem", 0)
                step.is_active = step_item.get("ativo", True)
                step.boolean_field = step_item.get("campo_booleano", "")
                step.save()

                for field_item in step_item.get("campos", []):
                    field, _ = ClientStepField.objects.get_or_create(
                        step=step,
                        field_name=field_item["nome_campo"],
                    )
                    raw_type = field_item.get("tipo_campo", "texto")
                    field.field_type = FIELD_TYPE_MAP.get(raw_type, raw_type)
                    field.order = field_item.get("ordem", 0)
                    field.is_required = field_item.get("obrigatorio", True)
                    field.is_active = field_item.get("ativo", True)
                    field.display_rule = _translate_display_rule(field_item.get("regra_exibicao"))
                    field.save()

        self.stdout.write(self.style.SUCCESS("Seed de etapas de cliente concluida."))
