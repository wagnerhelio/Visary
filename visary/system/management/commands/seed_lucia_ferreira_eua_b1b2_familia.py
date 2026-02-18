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
    help = "Lucia Ferreira + conjuge - Turismo EUA B1/B2, financeiro pago R$800, form completo."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("juliana.lopes@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor juliana.lopes@visary.com.br nao encontrado."))
                raise SystemExit(1)

            lucia = criar_cliente(
                assessor, admin, "Lucia Maria Ferreira",
                "lucia_ferreira_eua_b1b2",
                datetime.date(1987, 8, 30),
                email="lucia.ferreira@gmail.com",
                telefone="(62) 98808-8800",
            )
            bruno = criar_dependente(
                lucia, assessor, admin,
                "Bruno Henrique Ferreira",
                "bruno_ferreira_conjuge",
                datetime.date(1985, 12, 5),
                email="bruno.ferreira@gmail.com",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Estados Unidos",
                "B1 / B2 (Turismo, Negócios ou Estudos Recreativos)",
                datetime.date(2026, 12, 15),
                datetime.date(2026, 12, 30),
                valor=800.00,
            )
            adicionar_cliente_viagem(viagem, lucia)
            adicionar_cliente_viagem(viagem, bruno)
            criar_financeiro(viagem, lucia, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            criar_financeiro(viagem, bruno, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            preencher_formulario(viagem, lucia, admin, proporcao=1.0)
            preencher_formulario(viagem, bruno, admin, proporcao=1.0)

            self.stdout.write(self.style.SUCCESS("Lucia Ferreira + conjuge Bruno (EUA B1/B2 R$800 pago) criados."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
