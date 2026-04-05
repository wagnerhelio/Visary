import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from system.models import ProcessStatus


class Command(BaseCommand):
    help = "Popula status de processo a partir de static/status_processo_ini"

    def add_arguments(self, parser):
        parser.add_argument("--name", help="Nome de um status especifico")

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

        name_filter = (options.get("name") or "").strip().lower()

        for item in payload:
            status_name = item["nome"].strip()
            if name_filter and status_name.lower() != name_filter:
                continue

            status_obj, _ = ProcessStatus.objects.get_or_create(
                name=status_name, visa_type=None
            )
            status_obj.default_deadline_days = item.get("prazo_padrao_dias", 0)
            status_obj.order = item.get("ordem", 0)
            status_obj.is_active = item.get("ativo", True)
            status_obj.save()

        self.stdout.write(self.style.SUCCESS("Seed de status de processo concluida."))
