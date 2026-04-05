import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from system.models import DestinationCountry


class Command(BaseCommand):
    help = "Popula paises de destino a partir de static/paises_destino_ini"

    def add_arguments(self, parser):
        parser.add_argument("--name", help="Nome de um pais especifico para semear")

    def handle(self, *args, **options):
        seed_dir = Path(settings.BASE_DIR) / "static" / "paises_destino_ini"
        if not seed_dir.exists():
            raise CommandError(f"Diretorio de seed nao encontrado: {seed_dir}")

        payload = []
        for seed_path in sorted(seed_dir.glob("*.json")):
            data = json.loads(seed_path.read_text(encoding="utf-8"))
            payload.extend(data if isinstance(data, list) else [data])
        if not payload:
            raise CommandError("Nenhum pais encontrado em static/paises_destino_ini.")

        actor = self._get_actor()
        name_filter = (options.get("name") or "").strip().lower()

        for item in payload:
            country_name = item["nome"].strip()
            if name_filter and country_name.lower() != name_filter:
                continue

            country, _ = DestinationCountry.objects.get_or_create(
                name=country_name,
                defaults={
                    "iso_code": item.get("codigo_iso", ""),
                    "is_active": item.get("ativo", True),
                    "created_by": actor,
                },
            )
            country.iso_code = item.get("codigo_iso", "")
            country.is_active = item.get("ativo", True)
            country.created_by = actor
            country.save()

        self.stdout.write(self.style.SUCCESS("Seed de paises concluida."))

    def _get_actor(self):
        user_model = get_user_model()
        existing = user_model.objects.filter(is_superuser=True).order_by("id").first()
        if existing:
            return existing

        actor, _ = user_model.objects.get_or_create(
            username="seed-system",
            defaults={
                "email": "seed-system@visary.local",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if not actor.is_staff or not actor.is_superuser:
            actor.is_staff = True
            actor.is_superuser = True
            actor.save(update_fields=["is_staff", "is_superuser"])
        return actor
