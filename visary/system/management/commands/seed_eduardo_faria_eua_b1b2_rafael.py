import datetime
from django.core.management.base import BaseCommand
from system.management.commands._seed_helpers import (
    get_admin_user, get_assessor,
    criar_cliente, criar_dependente,
    obter_ou_criar_viagem, adicionar_cliente_viagem,
    criar_financeiro, criar_processo, criar_etapas_processo, preencher_formulario,
    criar_partner,
)
from consultancy.models import StatusFinanceiro


class Command(BaseCommand):
    help = "Eduardo Faria + esposa - EUA B1/B2, assessor Rafael, pago, dependente com processo proprio."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("rafael.teixeira@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor rafael.teixeira@visary.com.br nao encontrado."))
                raise SystemExit(1)

            parceiro = criar_partner(
                admin,
                "Isabela Moura",
                "Estudar no Exterior ME",
                "partner_isabela_moura",
                "isabela.moura@estudarnoexterior.com.br",
                "(21) 2233-7700",
                "Consultoria educacional",
            )

            eduardo = criar_cliente(
                assessor, admin, "Eduardo Augusto Faria",
                "eduardo_faria_eua_b1b2",
                datetime.date(1980, 11, 20),
                email="eduardo.faria@outlook.com",
                telefone="(11) 98814-4455",
                parceiro=parceiro,
            )
            patricia_dep = criar_dependente(
                eduardo, assessor, admin,
                "Patricia Gomes Faria",
                "patricia_faria_esposa_dep",
                datetime.date(1982, 4, 6),
                email="patricia.faria@outlook.com",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Estados Unidos",
                "B1 / B2 (Turismo, Negócios ou Estudos Recreativos)",
                datetime.date(2026, 7, 4),
                datetime.date(2026, 7, 18),
                valor=800.00,
            )
            adicionar_cliente_viagem(viagem, eduardo)
            adicionar_cliente_viagem(viagem, patricia_dep)
            criar_financeiro(viagem, eduardo, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            criar_financeiro(viagem, patricia_dep, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            processo_principal = criar_processo(viagem, eduardo, assessor, admin)
            criar_etapas_processo(processo_principal, proporcao_concluidas=0.7)
            processo_dep = criar_processo(viagem, patricia_dep, assessor, admin)
            criar_etapas_processo(processo_dep, proporcao_concluidas=0.3)
            preencher_formulario(viagem, eduardo, admin, proporcao=1.0)
            preencher_formulario(viagem, patricia_dep, admin, proporcao=0.6)

            self.stdout.write(self.style.SUCCESS(
                "Eduardo Faria + esposa Patricia (EUA B1/B2 pago, ambos com processo, Rafael) criados."
            ))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
