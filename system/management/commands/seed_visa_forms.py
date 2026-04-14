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
from system.services.form_prefill_rules import should_prefill_from_client

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

STAGES_MAP = {
    "B1 / B2 (Turismo, Neg\u00f3cios ou Estudos Recreativos)": [
        (1, "Dados Pessoais"),
        (2, "Dados da Viagem"),
        (3, "Contato Brasil"),
        (4, "Passaporte"),
        (5, "Contato EUA / Acompanhante"),
        (6, "Parente nos EUA"),
        (7, "Dados do C\u00f4njuge"),
        (8, "Dados dos Pais"),
        (9, "Ocupa\u00e7\u00e3o Atual"),
        (10, "Empregos Anteriores"),
        (11, "Informa\u00e7\u00f5es Educacionais"),
        (12, "Idioma e Experi\u00eancia"),
        (13, "Perguntas de Seguran\u00e7a"),
        (14, "Coment\u00e1rios Adicionais"),
        (15, "Agendamento"),
    ],
    "F1 (visto oficial de estudante)": [
        (1, "Dados Pessoais"),
        (2, "Endere\u00e7o Brasil"),
        (3, "Contato Brasil"),
        (4, "Dados da Viagem"),
        (5, "Redes Sociais"),
        (6, "Custeio da Viagem"),
        (7, "Dados da Escola"),
        (8, "Acompanhantes"),
        (9, "Empregos e Estudos Anteriores"),
        (10, "Coment\u00e1rios Adicionais"),
        (11, "Contato nos EUA (1)"),
        (12, "Contato nos EUA (2)"),
        (13, "Agendamento"),
        (14, "Declara\u00e7\u00e3o"),
    ],
    "J1 (visto de interc\u00e2mbio)": [
        (1, "Dados Pessoais"),
        (2, "Endere\u00e7o Brasil"),
        (3, "Contato Brasil"),
        (4, "Dados da Viagem"),
        (5, "Redes Sociais"),
        (6, "Custeio da Viagem"),
        (7, "Dados da Escola"),
        (8, "Acompanhantes"),
        (9, "Empregos e Estudos Anteriores"),
        (10, "Coment\u00e1rios Adicionais"),
        (11, "Contato nos EUA (1)"),
        (12, "Contato nos EUA (2)"),
        (13, "Agendamento"),
        (14, "Declara\u00e7\u00e3o"),
    ],
    "Estudante - Study Permit": [
        (1, "Dados Pessoais"),
        (2, "C\u00f4njuge / Estado Civil"),
        (3, "Perguntas de Seguran\u00e7a"),
        (4, "Passaporte"),
        (5, "Contato Brasil"),
        (6, "Dados da Viagem e Escola"),
        (7, "Estudos Anteriores"),
        (8, "Ocupa\u00e7\u00e3o Atual"),
        (9, "Ocupa\u00e7\u00f5es Anteriores"),
        (10, "Sa\u00fade"),
        (11, "Detalhes de Seguran\u00e7a"),
        (12, "Dados da M\u00e3e"),
        (13, "Dados do Pai"),
        (14, "Dados dos Filhos"),
        (15, "Viagem e Idiomas"),
    ],
    "Temporary Resident Visa - TRV": [
        (1, "Dados Pessoais"),
        (2, "C\u00f4njuge"),
        (3, "Perguntas de Seguran\u00e7a"),
        (4, "Passaporte"),
        (5, "Contato Brasil"),
        (6, "Dados da Viagem"),
        (7, "Estudos Anteriores"),
        (8, "Ocupa\u00e7\u00e3o Atual"),
        (9, "Atividade \u00daltimos 10 Anos"),
        (10, "Ocupa\u00e7\u00f5es Anteriores"),
        (11, "Sa\u00fade e Vistos"),
        (12, "Visto Negado Outro Pa\u00eds"),
        (13, "Detalhes de Seguran\u00e7a"),
        (14, "Dados da M\u00e3e"),
        (15, "Dados do Pai"),
        (16, "Dados dos Filhos"),
        (17, "Viagem e Idiomas"),
    ],
    "Visto de Estudante": [
        (1, "Aplica\u00e7\u00e3o"),
        (2, "Dados Pessoais"),
        (3, "C\u00f4njuge"),
        (4, "Documentos de Identidade"),
        (5, "Endere\u00e7o Brasil"),
        (6, "Fam\u00edlia no Brasil"),
        (7, "Parentes"),
        (8, "Vistos Anteriores"),
        (9, "Dados da Viagem"),
        (10, "Estudos e Passaporte"),
        (11, "Dados da Escola"),
        (12, "Contato Emergencial"),
        (13, "Ingl\u00eas"),
        (14, "Estudos de Ingl\u00eas"),
        (15, "Trabalho Atual"),
        (16, "Custeio"),
        (17, "Renda e Fundos"),
        (18, "Sa\u00fade"),
        (19, "Sa\u00fade Detalhada"),
        (20, "Criminal e Imigra\u00e7\u00e3o"),
        (21, "Militar"),
        (22, "Declara\u00e7\u00f5es"),
        (23, "Pagamento"),
    ],
    "Visto de Visitante": [
        (1, "Dados Pessoais"),
        (2, "C\u00f4njuge"),
        (3, "Endere\u00e7o Brasil"),
        (4, "Passaporte"),
        (5, "Perguntas de Seguran\u00e7a"),
        (6, "Passaporte e Nacionalidade"),
        (7, "Ocupa\u00e7\u00e3o Atual"),
        (8, "Custeio da Viagem"),
        (9, "Dados da Viagem"),
        (10, "Visitas Anteriores"),
        (11, "Estudos"),
        (12, "Fam\u00edlia no Brasil"),
        (13, "Filhos"),
        (14, "Viagens Anteriores"),
        (15, "Sa\u00fade"),
        (16, "Sa\u00fade Detalhada"),
        (17, "Respons\u00e1vel Legal (1)"),
        (18, "Respons\u00e1vel Legal (2)"),
        (19, "Declara\u00e7\u00f5es"),
    ],
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

                self._sync_stages(form, vt_name)
                stage_map = {
                    s.order: s for s in VisaFormStage.objects.filter(form=form)
                }
                self._sync_questions(form, form_item, stage_map)

        self.stdout.write(self.style.SUCCESS("Seed de formularios de visto concluida."))

    def _sync_stages(self, form, visa_type_name):
        stages = STAGES_MAP.get(visa_type_name, [])
        for order, name in stages:
            stage, created = VisaFormStage.objects.get_or_create(
                form=form,
                order=order,
                defaults={"name": name},
            )
            if not created and stage.name != name:
                stage.name = name
                stage.save(update_fields=["name"])

    def _sync_questions(self, form, form_item, stage_map):
        for q_item in form_item.get("perguntas", []):
            stage_order = q_item.get("etapa")
            if should_prefill_from_client(q_item.get("pergunta", "")):
                stage_order = 1
            stage_obj = stage_map.get(stage_order) if stage_order else None

            raw_type = q_item["tipo_campo"]
            field_type = FIELD_TYPE_MAP.get(raw_type, raw_type)

            question, _ = FormQuestion.objects.get_or_create(
                form=form,
                order=q_item["ordem"],
            )
            question.question = q_item["pergunta"]
            question.field_type = field_type
            question.is_required = q_item.get("obrigatorio", False)
            question.is_active = q_item.get("ativo", True)
            question.display_rule = _translate_display_rule(q_item.get("regra_exibicao"))
            question.stage = stage_obj
            question.save()

            if field_type != "select":
                continue

            for order, text in enumerate(q_item.get("opcoes", []), start=1):
                option, _ = SelectOption.objects.get_or_create(
                    question=question, order=order
                )
                option.text = text
                option.is_active = True
                option.save()

    def _normalize(self, value):
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = text.encode("ascii", "ignore").decode("ascii")
        text = text.lower().strip()
        return re.sub(r"[^a-z0-9]+", "", text)
