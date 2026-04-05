from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Cria ou atualiza o superusuario 'admin' com senha 'admin' (nao interativo)."

    def handle(self, *args, **options):
        username = "admin"
        email = "admin@admin.com"
        password = "admin"

        user, created = User.objects.get_or_create(
            username=username, defaults={"email": email}
        )
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS("Superusuario 'admin' criado com sucesso."))
        else:
            self.stdout.write(self.style.SUCCESS("Superusuario 'admin' atualizado com sucesso."))
