import json
import re
import unicodedata
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from system.models import DestinationCountry, VisaType


class Command(BaseCommand):
    help = "Popula tipos de visto a partir de static/tipos_visto_ini"

    def add_arguments(self, parser):
        parser.add_argument("--name", help="Nome de um tipo de visto especifico")

    def handle(self, *args, **options):
        call_command("seed_countries")

        seed_dir = Path(settings.BASE_DIR) / "static" / "tipos_visto_ini"
        if not seed_dir.exists():
            raise CommandError(f"Diretorio de seed nao encontrado: {seed_dir}")

        payload = []
        for seed_path in sorted(seed_dir.glob("*.json")):
            data = json.loads(seed_path.read_text(encoding="utf-8"))
            payload.extend(data if isinstance(data, list) else [data])
        if not payload:
            raise CommandError("Nenhum tipo de visto encontrado em static/tipos_visto_ini.")

        actor = self._get_actor()
        countries = {
            self._normalize(c.name): c for c in DestinationCountry.objects.all()
        }
        name_filter = (options.get("name") or "").strip()

        for item in payload:
            vt_name = item["nome"].strip()
            if name_filter and vt_name != name_filter:
                continue

            country_name = item["pais"].strip()
            country = countries.get(self._normalize(country_name))
            if not country:
                raise CommandError(f"Pais nao encontrado: {country_name}")

            visa_type, _ = VisaType.objects.get_or_create(
                destination_country=country,
                name=vt_name,
                defaults={
                    "description": item.get("descricao", ""),
                    "is_active": item.get("ativo", True),
                    "created_by": actor,
                },
            )
            visa_type.description = item.get("descricao", "")
            visa_type.is_active = item.get("ativo", True)
            visa_type.created_by = actor
            visa_type.save()

        self.stdout.write(self.style.SUCCESS("Seed de tipos de visto concluida."))

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

    def _normalize(self, value):
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = text.encode("ascii", "ignore").decode("ascii")
        text = text.lower().strip()
        return re.sub(r"[^a-z0-9]+", "", text)
