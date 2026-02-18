import datetime
from django.core.management.base import BaseCommand
from system.management.commands._seed_helpers import (
    get_admin_user, get_assessor,
    criar_cliente, criar_dependente,
    obter_ou_criar_viagem, adicionar_cliente_viagem,
    criar_financeiro, criar_processo, preencher_formulario,
)
from consultancy.models import StatusFinanceiro


class Command(BaseCommand):
    help = "Beatriz Costa - Intercambio EUA J1, financeiro cancelado, sem formulario."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("raquel.fleury@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor raquel.fleury@visary.com.br nao encontrado."))
                raise SystemExit(1)

            beatriz = criar_cliente(
                assessor, admin, "Beatriz Aparecida Costa",
                "beatriz_costa_eua_j1",
                datetime.date(1995, 11, 20),
                email="beatriz.costa@outlook.com",
                telefone="(62) 98803-3300",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Estados Unidos",
                "J1 (visto de intercambio)",
                datetime.date(2026, 7, 15),
                datetime.date(2026, 12, 20),
                valor=400.00,
            )
            adicionar_cliente_viagem(viagem, beatriz)
            criar_financeiro(viagem, beatriz, assessor, admin, 400.00, StatusFinanceiro.CANCELADO)

            self.stdout.write(self.style.SUCCESS("Beatriz Costa (EUA J1 cancelado, sem form) criada."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
