import json
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from system.models import Partner


class Command(BaseCommand):
    help = "Popula parceiros a partir de static/parceiros_ini"

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Email de um parceiro especifico")

    def handle(self, *args, **options):
        seed_dir = Path(settings.BASE_DIR) / "static" / "parceiros_ini"
        if not seed_dir.exists():
            raise CommandError(f"Diretorio de seed nao encontrado: {seed_dir}")

        payload = []
        for seed_path in sorted(seed_dir.glob("*.json")):
            data = json.loads(seed_path.read_text(encoding="utf-8"))
            payload.extend(data if isinstance(data, list) else [data])
        if not payload:
            raise CommandError("Nenhum parceiro encontrado em static/parceiros_ini.")

        raw_passwords = os.environ.get("SYSTEM_SEED_PARTNER_PASSWORDS")
        if not raw_passwords:
            raise CommandError("Defina SYSTEM_SEED_PARTNER_PASSWORDS no .env.")

        try:
            passwords = json.loads(raw_passwords)
        except json.JSONDecodeError as exc:
            raise CommandError("SYSTEM_SEED_PARTNER_PASSWORDS deve ser JSON valido.") from exc

        if not isinstance(passwords, dict):
            raise CommandError("SYSTEM_SEED_PARTNER_PASSWORDS deve ser um objeto JSON email->senha.")

        normalized_passwords = {
            str(email).strip().lower(): str(password)
            for email, password in passwords.items()
            if str(password).strip()
        }

        actor = self._get_actor()
        filtro_email = (options.get("email") or "").strip().lower()

        for item in payload:
            email = item["email"].strip().lower()
            if filtro_email and email != filtro_email:
                continue
            if email not in normalized_passwords:
                raise CommandError(f"Senha nao encontrada para parceiro: {email}")

            partner, _ = Partner.objects.get_or_create(
                email=email,
                defaults={
                    "nome_responsavel": item["nome_responsavel"],
                    "nome_empresa": item.get("nome_empresa", ""),
                    "cpf": item.get("cpf", ""),
                    "cnpj": item.get("cnpj", ""),
                    "senha": "placeholder",
                    "telefone": item.get("telefone", ""),
                    "segmento": item.get("segmento", "outros"),
                    "cidade": item.get("cidade", ""),
                    "estado": item.get("estado", ""),
                    "ativo": item.get("ativo", True),
                    "criado_por": actor,
                },
            )
            partner.nome_responsavel = item["nome_responsavel"]
            partner.nome_empresa = item.get("nome_empresa", "")
            partner.cpf = item.get("cpf", "")
            partner.cnpj = item.get("cnpj", "")
            partner.telefone = item.get("telefone", "")
            partner.segmento = item.get("segmento", "outros")
            partner.cidade = item.get("cidade", "")
            partner.estado = item.get("estado", "")
            partner.ativo = item.get("ativo", True)
            partner.criado_por = actor
            partner.set_password(normalized_passwords[email])
            partner.save()

        self.stdout.write(self.style.SUCCESS("Seed de parceiros concluida."))

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
