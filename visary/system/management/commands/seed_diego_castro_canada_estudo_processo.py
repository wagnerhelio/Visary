import datetime
from django.core.management.base import BaseCommand
from system.management.commands._seed_helpers import (
    get_admin_user, get_assessor,
    criar_cliente,
    obter_ou_criar_viagem, adicionar_cliente_viagem,
    criar_financeiro, criar_processo, criar_etapas_processo,
)
from consultancy.models import StatusFinanceiro


class Command(BaseCommand):
    help = "Diego Castro - Estudo Canada Study Permit, processo aberto, financeiro pendente."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("juliana.lopes@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor juliana.lopes@visary.com.br nao encontrado."))
                raise SystemExit(1)

            diego = criar_cliente(
                assessor, admin, "Diego Henrique Castro",
                "diego_castro_canada_estudo",
                datetime.date(1999, 10, 7),
                email="diego.castro@hotmail.com",
                telefone="(62) 98811-1122",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Canadá",
                "Estudante - Study Permit",
                datetime.date(2027, 1, 10),
                datetime.date(2028, 1, 9),
                valor=400.00,
            )
            adicionar_cliente_viagem(viagem, diego)
            criar_financeiro(viagem, diego, assessor, admin, 400.00, StatusFinanceiro.PENDENTE)
            processo = criar_processo(viagem, diego, assessor, admin)
            criar_etapas_processo(processo, proporcao_concluidas=0.3)

            self.stdout.write(self.style.SUCCESS("Diego Castro (Canada Estudo processo pendente) criado."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
