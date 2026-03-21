import json
import re
import unicodedata
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from system.models import PaisDestino, TipoVisto


class Command(BaseCommand):
    help = "Popula tipos de visto a partir de static/tipos_visto_ini"

    def add_arguments(self, parser):
        parser.add_argument("--nome", help="Nome de um tipo de visto especifico")

    def handle(self, *args, **options):
        call_command("seed_paises")

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
        countries = {self._normalize(pais.nome): pais for pais in PaisDestino.objects.all()}
        filtro_nome = (options.get("nome") or "").strip()

        for item in payload:
            nome = item["nome"].strip()
            if filtro_nome and nome != filtro_nome:
                continue

            pais_nome = item["pais"].strip()
            pais = countries.get(self._normalize(pais_nome))
            if not pais:
                raise CommandError(f"Pais nao encontrado: {pais_nome}")

            tipo, _ = TipoVisto.objects.get_or_create(
                pais_destino=pais,
                nome=nome,
                defaults={
                    "descricao": item.get("descricao", ""),
                    "ativo": item.get("ativo", True),
                    "criado_por": actor,
                },
            )
            tipo.descricao = item.get("descricao", "")
            tipo.ativo = item.get("ativo", True)
            tipo.criado_por = actor
            tipo.save()

        self.stdout.write(self.style.SUCCESS("Seed de tipos de visto concluida."))

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

    def _normalize(self, value):
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = text.encode("ascii", "ignore").decode("ascii")
        text = text.lower().strip()
        return re.sub(r"[^a-z0-9]+", "", text)
