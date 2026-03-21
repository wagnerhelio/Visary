import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from system.models import PaisDestino


class Command(BaseCommand):
    help = "Popula paises de destino a partir de static/paises_destino_ini"

    def add_arguments(self, parser):
        parser.add_argument("--nome", help="Nome de um pais especifico para semear")

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
        filtro_nome = (options.get("nome") or "").strip().lower()

        for item in payload:
            nome = item["nome"].strip()
            if filtro_nome and nome.lower() != filtro_nome:
                continue

            pais, _ = PaisDestino.objects.get_or_create(
                nome=nome,
                defaults={
                    "codigo_iso": item.get("codigo_iso", ""),
                    "ativo": item.get("ativo", True),
                    "criado_por": actor,
                },
            )
            pais.codigo_iso = item.get("codigo_iso", "")
            pais.ativo = item.get("ativo", True)
            pais.criado_por = actor
            pais.save()

        self.stdout.write(self.style.SUCCESS("Seed de paises concluida."))

    def _get_actor(self):
        user_model = get_user_model()
        existing_superuser = user_model.objects.filter(is_superuser=True).order_by("id").first()
        if existing_superuser:
            return existing_superuser

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
