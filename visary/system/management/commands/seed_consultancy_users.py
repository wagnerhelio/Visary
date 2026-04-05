import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from system.models import ConsultancyUser, Profile


class Command(BaseCommand):
    help = "Popula usuarios da consultoria a partir de system_users.json"

    def handle(self, *args, **options):
        call_command("seed_profiles")

        users_dir = Path(settings.BASE_DIR) / "static" / "usuarios_consultoria_ini"
        if not users_dir.exists():
            raise CommandError(f"Diretorio de seed nao encontrado: {users_dir}")

        users_seed = []
        for users_path in sorted(users_dir.glob("*.json")):
            payload = json.loads(users_path.read_text(encoding="utf-8"))
            users_seed.extend(payload if isinstance(payload, list) else [payload])
        if not users_seed:
            raise CommandError("Nenhum usuario encontrado em static/usuarios_consultoria_ini.")

        passwords_raw = os.environ.get("SYSTEM_SEED_USERS_PASSWORDS")
        if not passwords_raw:
            raise CommandError("Defina SYSTEM_SEED_USERS_PASSWORDS no .env.")

        try:
            passwords = json.loads(passwords_raw)
        except json.JSONDecodeError as exc:
            raise CommandError("SYSTEM_SEED_USERS_PASSWORDS deve ser JSON valido.") from exc

        if not isinstance(passwords, dict):
            raise CommandError("SYSTEM_SEED_USERS_PASSWORDS deve ser um objeto JSON email->senha.")

        normalized_passwords = {
            str(email).strip().lower(): str(pw)
            for email, pw in passwords.items()
            if str(pw).strip()
        }

        profiles_by_name = {p.name: p for p in Profile.objects.all()}

        for item in users_seed:
            email = item["email"].strip().lower()
            profile_name = item["perfil"]

            if profile_name not in profiles_by_name:
                raise CommandError(f"Perfil nao encontrado para usuario: {profile_name}")
            if email not in normalized_passwords:
                raise CommandError(f"Senha nao encontrada em SYSTEM_SEED_USERS_PASSWORDS para: {email}")

            profile = profiles_by_name[profile_name]
            user_obj, _ = ConsultancyUser.objects.get_or_create(
                email=email,
                defaults={
                    "name": item["nome"],
                    "profile": profile,
                    "is_active": True,
                    "password": "placeholder",
                },
            )
            user_obj.name = item["nome"]
            user_obj.profile = profile
            user_obj.is_active = True
            user_obj.set_password(normalized_passwords[email], commit=False)
            user_obj.save()

        self.stdout.write(self.style.SUCCESS("Seed de usuarios da consultoria concluida."))
