import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from system.models import CampoEtapaCliente, EtapaCadastroCliente


class Command(BaseCommand):
    help = "Popula etapas de cadastro de cliente a partir de static/etapas_cliente_ini"

    def add_arguments(self, parser):
        parser.add_argument("--nome", help="Nome de uma etapa especifica")

    def handle(self, *args, **options):
        steps_dir = Path(settings.BASE_DIR) / "static" / "etapas_cliente_ini"
        if not steps_dir.exists():
            raise CommandError(f"Diretorio nao encontrado: {steps_dir}")

        filtro_nome = (options.get("nome") or "").strip().lower()

        for json_file in sorted(steps_dir.glob("*.json")):
            payload = json.loads(json_file.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                continue

            for step_item in payload:
                nome = step_item["nome"].strip()
                if filtro_nome and nome.lower() != filtro_nome:
                    continue

                etapa, _ = EtapaCadastroCliente.objects.get_or_create(nome=nome)
                etapa.descricao = step_item.get("descricao", "")
                etapa.ordem = step_item.get("ordem", 0)
                etapa.ativo = step_item.get("ativo", True)
                etapa.campo_booleano = step_item.get("campo_booleano", "")
                etapa.save()

                for field_item in step_item.get("campos", []):
                    campo, _ = CampoEtapaCliente.objects.get_or_create(
                        etapa=etapa,
                        nome_campo=field_item["nome_campo"],
                    )
                    campo.tipo_campo = field_item.get("tipo_campo", "texto")
                    campo.ordem = field_item.get("ordem", 0)
                    campo.obrigatorio = field_item.get("obrigatorio", True)
                    campo.ativo = field_item.get("ativo", True)
                    campo.regra_exibicao = field_item.get("regra_exibicao")
                    campo.save()

        self.stdout.write(self.style.SUCCESS("Seed de etapas de cliente concluida."))
