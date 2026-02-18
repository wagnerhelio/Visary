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
    help = "Ana Oliveira - Turismo EUA B1/B2, financeiro pago, formulario completo."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("yan.hmachado@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor yan.hmachado@visary.com.br nao encontrado."))
                raise SystemExit(1)

            ana = criar_cliente(
                assessor, admin, "Ana Luiza Oliveira",
                "ana_oliveira_eua_b1b2",
                datetime.date(1988, 4, 12),
                email="ana.oliveira@gmail.com",
                telefone="(62) 98801-1100",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Estados Unidos",
                "B1 / B2 (Turismo, Negócios ou Estudos Recreativos)",
                datetime.date(2026, 8, 10),
                datetime.date(2026, 8, 25),
                valor=400.00,
            )
            adicionar_cliente_viagem(viagem, ana)
            criar_financeiro(viagem, ana, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            preencher_formulario(viagem, ana, admin, proporcao=1.0)

            self.stdout.write(self.style.SUCCESS("Ana Oliveira (EUA B1/B2 pago, form completo) criada."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
