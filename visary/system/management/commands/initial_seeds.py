from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Executa todas as seeds iniciais na ordem padrao do sistema."

    def handle(self, *args, **options):
        pipeline = [
            ("seed_modulos", "modulos"),
            ("seed_perfis", "perfis"),
            ("seed_usuarios_consultoria", "usuarios_consultoria"),
            ("seed_paises", "paises_destino"),
            ("seed_tipos_visto", "tipos_visto"),
            ("seed_status_processo", "status_processo"),
            ("seed_formularios_visto", "formularios_visto"),
            ("seed_etapas_cliente", "etapas_cliente"),
            ("seed_parceiros", "parceiros"),
        ]

        for command_name, label in pipeline:
            self.stdout.write(f"Iniciando seed: {label}...")
            call_command(command_name)
            self.stdout.write(self.style.SUCCESS(f"Seed concluida: {label}"))

        self.stdout.write(self.style.SUCCESS("Todas as seeds iniciais foram executadas."))
