from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Executa todas as seeds iniciais na ordem padrao do sistema."

    def handle(self, *args, **options):
        pipeline = [
            ("seed_modules", "modules"),
            ("seed_profiles", "profiles"),
            ("seed_consultancy_users", "consultancy_users"),
            ("seed_countries", "destination_countries"),
            ("seed_visa_types", "visa_types"),
            ("seed_process_status", "process_status"),
            ("seed_visa_forms", "visa_forms"),
            ("seed_client_steps", "client_steps"),
            ("seed_partners", "partners"),
        ]

        for command_name, label in pipeline:
            self.stdout.write(f"Iniciando seed: {label}...")
            call_command(command_name)
            self.stdout.write(self.style.SUCCESS(f"Seed concluida: {label}"))

        self.stdout.write(self.style.SUCCESS("Todas as seeds iniciais foram executadas."))
