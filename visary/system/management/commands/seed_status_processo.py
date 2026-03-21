import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from system.models import StatusProcesso


class Command(BaseCommand):
    help = "Popula status de processo a partir de static/status_processo_ini"

    def add_arguments(self, parser):
        parser.add_argument("--nome", help="Nome de um status especifico")

    def handle(self, *args, **options):
        seed_dir = Path(settings.BASE_DIR) / "static" / "status_processo_ini"
        if not seed_dir.exists():
            raise CommandError(f"Diretorio de seed nao encontrado: {seed_dir}")

        payload = []
        for seed_path in sorted(seed_dir.glob("*.json")):
            data = json.loads(seed_path.read_text(encoding="utf-8"))
            payload.extend(data if isinstance(data, list) else [data])
        if not payload:
            raise CommandError("Nenhum status encontrado em static/status_processo_ini.")

        filtro_nome = (options.get("nome") or "").strip().lower()

        for item in payload:
            nome = item["nome"].strip()
            if filtro_nome and nome.lower() != filtro_nome:
                continue

            status, _ = StatusProcesso.objects.get_or_create(nome=nome, tipo_visto=None)
            status.prazo_padrao_dias = item.get("prazo_padrao_dias", 0)
            status.ordem = item.get("ordem", 0)
            status.ativo = item.get("ativo", True)
            status.save()

        self.stdout.write(self.style.SUCCESS("Seed de status de processo concluida."))
