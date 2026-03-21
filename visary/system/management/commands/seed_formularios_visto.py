import json
import re
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from system.models import FormularioVisto, OpcaoSelecao, PerguntaFormulario, TipoVisto


class Command(BaseCommand):
    help = "Popula formularios de visto a partir de static/forms_ini"

    def add_arguments(self, parser):
        parser.add_argument("--tipo-visto", help="Nome exato do tipo de visto")
        parser.add_argument("--arquivo", help="Nome do arquivo JSON em static/forms_ini")

    def handle(self, *args, **options):
        call_command("seed_tipos_visto")

        forms_dir = Path(settings.BASE_DIR) / "static" / "forms_ini"
        if not forms_dir.exists():
            raise CommandError(f"Diretorio nao encontrado: {forms_dir}")

        types_by_name = {
            self._normalize(tipo.nome): tipo for tipo in TipoVisto.objects.select_related("pais_destino")
        }

        filtro_tipo = (options.get("tipo_visto") or "").strip()
        filtro_arquivo = (options.get("arquivo") or "").strip()

        files = sorted(forms_dir.glob("*.json"))
        if filtro_arquivo:
            files = [arquivo for arquivo in files if arquivo.name == filtro_arquivo]
            if not files:
                raise CommandError(f"Arquivo nao encontrado em forms_ini: {filtro_arquivo}")

        for json_file in files:
            payload = json.loads(json_file.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                continue

            for form_item in payload:
                tipo_nome = form_item.get("tipo_visto", "").strip()
                if filtro_tipo and tipo_nome != filtro_tipo:
                    continue

                tipo = types_by_name.get(self._normalize(tipo_nome))
                if not tipo:
                    raise CommandError(f"Tipo de visto nao encontrado para formulario: {tipo_nome}")

                formulario, _ = FormularioVisto.objects.get_or_create(tipo_visto=tipo)
                formulario.ativo = True
                formulario.save(update_fields=["ativo", "atualizado_em"])

                for pergunta_item in form_item.get("perguntas", []):
                    pergunta, _ = PerguntaFormulario.objects.get_or_create(
                        formulario=formulario,
                        ordem=pergunta_item["ordem"],
                    )
                    pergunta.pergunta = pergunta_item["pergunta"]
                    pergunta.tipo_campo = pergunta_item["tipo_campo"]
                    pergunta.obrigatorio = pergunta_item.get("obrigatorio", False)
                    pergunta.ativo = pergunta_item.get("ativo", True)
                    pergunta.regra_exibicao = pergunta_item.get("regra_exibicao")
                    pergunta.save()

                    if pergunta.tipo_campo != "selecao":
                        continue

                    for ordem, texto in enumerate(pergunta_item.get("opcoes", []), start=1):
                        opcao, _ = OpcaoSelecao.objects.get_or_create(pergunta=pergunta, ordem=ordem)
                        opcao.texto = texto
                        opcao.ativo = True
                        opcao.save()

        self.stdout.write(self.style.SUCCESS("Seed de formularios de visto concluida."))

    def _normalize(self, value):
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = text.encode("ascii", "ignore").decode("ascii")
        text = text.lower().strip()
        return re.sub(r"[^a-z0-9]+", "", text)
