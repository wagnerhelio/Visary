import datetime
from django.core.management.base import BaseCommand
from system.management.commands._seed_helpers import (
    get_admin_user, get_assessor,
    criar_cliente, criar_dependente,
    obter_ou_criar_viagem, adicionar_cliente_viagem,
    criar_financeiro, criar_processo, criar_etapas_processo, preencher_formulario,
)
from consultancy.models import StatusFinanceiro


class Command(BaseCommand):
    help = "Thiago Souza + 2 filhos - Canada TRV, financeiro pago R$1200, form completo."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("raquel.fleury@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor raquel.fleury@visary.com.br nao encontrado."))
                raise SystemExit(1)

            thiago = criar_cliente(
                assessor, admin, "Thiago Rodrigues Souza",
                "thiago_souza_canada_trv",
                datetime.date(1982, 6, 14),
                email="thiago.souza@outlook.com",
                telefone="(62) 98809-9900",
            )
            sofia = criar_dependente(
                thiago, assessor, admin,
                "Sofia Rodrigues Souza",
                "sofia_souza_filha",
                datetime.date(2010, 3, 8),
            )
            pedro = criar_dependente(
                thiago, assessor, admin,
                "Pedro Rodrigues Souza",
                "pedro_souza_filho",
                datetime.date(2013, 11, 22),
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Canadá",
                "Temporary Resident Visa - TRV",
                datetime.date(2027, 2, 10),
                datetime.date(2027, 2, 25),
                valor=1200.00,
            )
            adicionar_cliente_viagem(viagem, thiago)
            adicionar_cliente_viagem(viagem, sofia)
            adicionar_cliente_viagem(viagem, pedro)
            criar_financeiro(viagem, thiago, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            criar_financeiro(viagem, sofia, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            criar_financeiro(viagem, pedro, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            processo = criar_processo(viagem, thiago, assessor, admin)
            criar_etapas_processo(processo, proporcao_concluidas=0.5)
            preencher_formulario(viagem, thiago, admin, proporcao=1.0)
            preencher_formulario(viagem, sofia, admin, proporcao=0.5)
            preencher_formulario(viagem, pedro, admin, proporcao=0.5)

            self.stdout.write(self.style.SUCCESS("Thiago Souza + filhos Sofia e Pedro (Canada TRV R$1200 pago) criados."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
