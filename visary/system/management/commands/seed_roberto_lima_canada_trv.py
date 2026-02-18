import datetime
from django.core.management.base import BaseCommand
from system.management.commands._seed_helpers import (
    get_admin_user, get_assessor,
    criar_cliente,
    obter_ou_criar_viagem, adicionar_cliente_viagem,
    criar_financeiro, preencher_formulario,
)
from consultancy.models import StatusFinanceiro


class Command(BaseCommand):
    help = "Roberto Lima - Visita Canada TRV, financeiro pago, formulario completo."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("yan.hmachado@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor yan.hmachado@visary.com.br nao encontrado."))
                raise SystemExit(1)

            roberto = criar_cliente(
                assessor, admin, "Roberto Augusto Lima",
                "roberto_lima_canada_trv",
                datetime.date(1979, 2, 28),
                email="roberto.lima@yahoo.com.br",
                telefone="(62) 98804-4400",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Canadá",
                "Temporary Resident Visa - TRV",
                datetime.date(2026, 10, 3),
                datetime.date(2026, 10, 18),
                valor=400.00,
            )
            adicionar_cliente_viagem(viagem, roberto)
            criar_financeiro(viagem, roberto, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            preencher_formulario(viagem, roberto, admin, proporcao=1.0)

            self.stdout.write(self.style.SUCCESS("Roberto Lima (Canada TRV pago, form completo) criado."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
