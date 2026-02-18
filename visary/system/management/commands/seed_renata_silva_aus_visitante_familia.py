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
    help = "Renata Silva + conjuge - AUS Visitante, pago R$800, form completo, processo 50%, com parceiro."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("camila.borges@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor camila.borges@visary.com.br nao encontrado."))
                raise SystemExit(1)

            parceiro = criar_partner(
                admin,
                "Gustavo Henrique Prado",
                "Intercâmbio Global Ltda",
                "partner_gustavo_prado",
                "gustavo.prado@intercambioglobal.com.br",
                "(11) 3322-5500",
            )

            renata = criar_cliente(
                assessor, admin, "Renata Aparecida Silva",
                "renata_silva_aus_visitante",
                datetime.date(1985, 3, 17),
                email="renata.silva@gmail.com",
                telefone="(62) 98813-3344",
                parceiro=parceiro,
            )
            marcelo = criar_dependente(
                renata, assessor, admin,
                "Marcelo Rodrigues Silva",
                "marcelo_silva_conjuge_aus",
                datetime.date(1983, 9, 4),
                email="marcelo.silva@gmail.com",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Austrália",
                "Visto de Visitante",
                datetime.date(2026, 11, 10),
                datetime.date(2026, 11, 30),
                valor=800.00,
            )
            adicionar_cliente_viagem(viagem, renata)
            adicionar_cliente_viagem(viagem, marcelo)
            criar_financeiro(viagem, renata, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            criar_financeiro(viagem, marcelo, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            processo = criar_processo(viagem, renata, assessor, admin)
            criar_etapas_processo(processo, proporcao_concluidas=0.5)
            preencher_formulario(viagem, renata, admin, proporcao=1.0)
            preencher_formulario(viagem, marcelo, admin, proporcao=0.7)

            self.stdout.write(self.style.SUCCESS(
                "Renata Silva + conjuge Marcelo (AUS Visitante R$800 pago, processo 50%, parceiro) criados."
            ))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
