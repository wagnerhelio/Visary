import datetime
from django.core.management.base import BaseCommand
from system.management.commands._seed_helpers import (
    get_admin_user, get_assessor,
    criar_cliente,
    obter_ou_criar_viagem, adicionar_cliente_viagem,
    criar_financeiro, criar_processo, criar_etapas_processo, preencher_formulario,
)
from consultancy.models import StatusFinanceiro


class Command(BaseCommand):
    help = "Julia Martins - Estudo Australia Estudante, processo, form completo, financeiro pago."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("raquel.fleury@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor raquel.fleury@visary.com.br nao encontrado."))
                raise SystemExit(1)

            julia = criar_cliente(
                assessor, admin, "Julia Carolina Martins",
                "julia_martins_aus_estudante",
                datetime.date(1996, 4, 25),
                email="julia.martins@gmail.com",
                telefone="(62) 98812-2233",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Austrália",
                "Visto de Estudante",
                datetime.date(2027, 2, 15),
                datetime.date(2027, 12, 15),
                valor=400.00,
            )
            adicionar_cliente_viagem(viagem, julia)
            criar_financeiro(viagem, julia, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            processo = criar_processo(viagem, julia, assessor, admin)
            criar_etapas_processo(processo, proporcao_concluidas=1.0)
            preencher_formulario(viagem, julia, admin, proporcao=1.0)

            self.stdout.write(self.style.SUCCESS("Julia Martins (Australia Estudante pago, processo, form completo) criada."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
