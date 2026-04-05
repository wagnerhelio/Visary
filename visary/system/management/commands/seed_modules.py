import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from system.models import Module


class Command(BaseCommand):
    help = "Popula modulos a partir de static/modulos_ini"

    def handle(self, *args, **options):
        seed_dir = Path(settings.BASE_DIR) / "static" / "modulos_ini"
        if not seed_dir.exists():
            raise CommandError(f"Diretorio de seed nao encontrado: {seed_dir}")

        files = sorted(seed_dir.glob("*.json"))
        if not files:
            raise CommandError("Nenhum arquivo de modulo encontrado em static/modulos_ini.")

        for seed_path in files:
            try:
                payload = json.loads(seed_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise CommandError(f"JSON invalido em {seed_path}: {exc}") from exc

            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                module, _ = Module.objects.get_or_create(name=item["nome"])
                module.description = item.get("descricao", "")
                module.order = item["ordem"]
                module.is_active = item.get("ativo", True)
                module.save()

        self.stdout.write(self.style.SUCCESS("Seed de modulos concluida."))
