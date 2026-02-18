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
    help = "Vera Lima - Canada TRV, assessora Camila, pago, form completo."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("camila.borges@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor camila.borges@visary.com.br nao encontrado."))
                raise SystemExit(1)

            vera = criar_cliente(
                assessor, admin, "Vera Lucia Lima",
                "vera_lima_canada_trv_camila",
                datetime.date(1975, 6, 30),
                email="vera.lima@gmail.com",
                telefone="(62) 98815-5566",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Canadá",
                "Temporary Resident Visa - TRV",
                datetime.date(2026, 8, 20),
                datetime.date(2026, 9, 5),
                valor=400.00,
            )
            adicionar_cliente_viagem(viagem, vera)
            criar_financeiro(viagem, vera, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            preencher_formulario(viagem, vera, admin, proporcao=1.0)

            self.stdout.write(self.style.SUCCESS("Vera Lima (Canada TRV pago, Camila) criada."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
