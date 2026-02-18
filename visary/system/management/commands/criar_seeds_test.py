from django.core.management.base import BaseCommand
from django.core.management import call_command


COMMANDS = [
    ("criar_superuser_admin",                       "Superusuario admin"),
    ("seed_test_assessores",                        "Assessores extras (Camila, Rafael)"),
    ("seed_test_parceiro",                          "Parceiros indicadores de teste"),
    ("seed_test_infra",                             "Infraestrutura: paises, vistos e formularios reais"),
    # Clientes - cenarios individuais
    ("seed_ana_oliveira_eua_b1b2",                  "Ana Oliveira - EUA B1/B2, pago, form completo"),
    ("seed_carlos_mendes_eua_f1",                   "Carlos Mendes - EUA F1, pendente, form 50%"),
    ("seed_beatriz_costa_eua_j1",                   "Beatriz Costa - EUA J1, cancelado, sem form"),
    ("seed_roberto_lima_canada_trv",                "Roberto Lima - Canada TRV, pago, form completo"),
    ("seed_fernanda_santos_canada_estudo",          "Fernanda Santos - Canada Estudo, pendente, form 40%"),
    ("seed_patricia_rocha_aus_visitante",           "Patricia Rocha - AUS Visitante, pago, form completo"),
    ("seed_marcos_alves_aus_estudante",             "Marcos Alves - AUS Estudante, pendente, form 30%"),
    # Clientes - cenarios com familia
    ("seed_lucia_ferreira_eua_b1b2_familia",        "Lucia Ferreira + conjuge - EUA B1/B2 R$800 pago"),
    ("seed_thiago_souza_canada_trv_familia",        "Thiago Souza + 2 filhos - Canada TRV R$1200 pago, etapas"),
    ("seed_renata_silva_aus_visitante_familia",     "Renata Silva + conjuge - AUS Visitante R$800, parceiro, processo"),
    # Clientes - com processo e etapas
    ("seed_amanda_nunes_eua_f1_processo",           "Amanda Nunes - EUA F1, processo 0%, sem financeiro"),
    ("seed_diego_castro_canada_estudo_processo",    "Diego Castro - Canada Estudo, processo 30%, pendente"),
    ("seed_julia_martins_aus_estudante_completo",   "Julia Martins - AUS Estudante, processo 100%, pago"),
    # Clientes assessores extras (Camila e Rafael)
    ("seed_vera_lima_canada_trv_camila",            "Vera Lima - Canada TRV, pago, Camila"),
    ("seed_eduardo_faria_eua_b1b2_rafael",          "Eduardo Faria + esposa - EUA B1/B2, pago, Rafael, parceiro"),
]


class Command(BaseCommand):
    help = "Executa todos os seeds de teste em sequencia."

    def handle(self, *args, **options):
        erros = []
        for cmd, descricao in COMMANDS:
            self.stdout.write(f"[seed] {descricao}")
            try:
                call_command(cmd)
            except SystemExit:
                erros.append(cmd)
                self.stderr.write(self.style.ERROR(f"  Falhou: {cmd}"))
            except Exception as exc:
                erros.append(cmd)
                self.stderr.write(self.style.ERROR(f"  Falhou: {cmd} -- {exc}"))

        self.stdout.write("")
        if erros:
            self.stderr.write(self.style.ERROR(f"Seeds com erro: {', '.join(erros)}"))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(
            f"Todos os {len(COMMANDS)} seeds executados com sucesso."
        ))
