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
    help = "Fernanda Santos - Estudo Canada Study Permit, financeiro pendente, sem formulario."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("juliana.lopes@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor juliana.lopes@visary.com.br nao encontrado."))
                raise SystemExit(1)

            fernanda = criar_cliente(
                assessor, admin, "Fernanda Cristina Santos",
                "fernanda_santos_canada_estudo",
                datetime.date(2000, 7, 8),
                email="fernanda.santos@gmail.com",
                telefone="(62) 98805-5500",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Canadá",
                "Estudante - Study Permit",
                datetime.date(2026, 9, 1),
                datetime.date(2027, 8, 31),
                valor=400.00,
            )
            adicionar_cliente_viagem(viagem, fernanda)
            criar_financeiro(viagem, fernanda, assessor, admin, 400.00, StatusFinanceiro.PENDENTE)
            preencher_formulario(viagem, fernanda, admin, proporcao=0.4)

            self.stdout.write(self.style.SUCCESS("Fernanda Santos (Canada Estudo pendente, form 40%) criada."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
