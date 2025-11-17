from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = "Cria ou atualiza o superusuário 'admin' com senha 'admin' (não interativo)."

    def handle(self, *args, **options):
        username = 'admin'
        email = 'admin@admin.com'
        password = 'admin'

        try:
            user, created = User.objects.get_or_create(username=username, defaults={
                'email': email
            })

            user.email = email
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()

            if created:
                self.stdout.write(self.style.SUCCESS("Superusuário 'admin' criado com sucesso."))
            else:
                self.stdout.write(self.style.SUCCESS("Superusuário 'admin' atualizado com sucesso."))

        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro ao criar/atualizar superusuário: {exc}"))
            raise SystemExit(1)

