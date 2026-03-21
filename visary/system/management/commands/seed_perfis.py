import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from system.models import Modulo, Perfil


class Command(BaseCommand):
    help = "Popula perfis e vinculos de modulos"

    def handle(self, *args, **options):
        call_command("seed_modulos")

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

        modules_by_name = {module.nome: module for module in Modulo.objects.all()}

        for item in profiles_seed:
            perfil, _ = Perfil.objects.get_or_create(nome=item["nome"])
            perfil.descricao = item.get("descricao", "")
            perfil.pode_criar = item.get("pode_criar", False)
            perfil.pode_visualizar = item.get("pode_visualizar", True)
            perfil.pode_atualizar = item.get("pode_atualizar", False)
            perfil.pode_excluir = item.get("pode_excluir", False)
            perfil.ativo = item.get("ativo", True)
            perfil.save()

            allowed_modules = []
            for module_seed in modules_seed:
                if perfil.nome in module_seed.get("perfis", []):
                    module = modules_by_name.get(module_seed["nome"])
                    if module:
                        allowed_modules.append(module)
            perfil.modulos.set(allowed_modules)

        self.stdout.write(self.style.SUCCESS("Seed de perfis concluida."))
