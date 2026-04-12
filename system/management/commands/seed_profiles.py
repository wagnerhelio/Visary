import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from system.models import Module, Profile


class Command(BaseCommand):
    help = "Popula perfis e vinculos de modulos"

    def handle(self, *args, **options):
        call_command("seed_modules")

        modules_dir = Path(settings.BASE_DIR) / "static" / "modulos_ini"
        profiles_dir = Path(settings.BASE_DIR) / "static" / "perfis_ini"

        if not modules_dir.exists() or not profiles_dir.exists():
            raise CommandError("Diretorios modulos_ini e perfis_ini sao obrigatorios.")

        modules_seed = []
        for path in sorted(modules_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            modules_seed.extend(payload if isinstance(payload, list) else [payload])

        profiles_seed = []
        for path in sorted(profiles_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            profiles_seed.extend(payload if isinstance(payload, list) else [payload])

        if not modules_seed or not profiles_seed:
            raise CommandError("Nao ha dados suficientes em modulos_ini/perfis_ini.")

        modules_by_name = {m.name: m for m in Module.objects.all()}

        for item in profiles_seed:
            profile, _ = Profile.objects.get_or_create(name=item["nome"])
            profile.description = item.get("descricao", "")
            profile.can_create = item.get("pode_criar", False)
            profile.can_view = item.get("pode_visualizar", True)
            profile.can_update = item.get("pode_atualizar", False)
            profile.can_delete = item.get("pode_excluir", False)
            profile.is_active = item.get("ativo", True)
            profile.save()

            allowed = []
            for module_seed in modules_seed:
                if profile.name in module_seed.get("perfis", []):
                    module = modules_by_name.get(module_seed["nome"])
                    if module:
                        allowed.append(module)
            profile.modules.set(allowed)

        self.stdout.write(self.style.SUCCESS("Seed de perfis concluida."))
