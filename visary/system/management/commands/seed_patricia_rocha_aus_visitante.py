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
    help = "Patricia Rocha - Turismo Australia Visitante, financeiro pago, formulario completo."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("raquel.fleury@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor raquel.fleury@visary.com.br nao encontrado."))
                raise SystemExit(1)

            patricia = criar_cliente(
                assessor, admin, "Patricia Helena Rocha",
                "patricia_rocha_aus_visitante",
                datetime.date(1983, 3, 17),
                email="patricia.rocha@gmail.com",
                telefone="(62) 98806-6600",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Austrália",
                "Visto de Visitante",
                datetime.date(2026, 11, 20),
                datetime.date(2026, 12, 5),
                valor=400.00,
            )
            adicionar_cliente_viagem(viagem, patricia)
            criar_financeiro(viagem, patricia, assessor, admin, 400.00, StatusFinanceiro.PAGO)
            preencher_formulario(viagem, patricia, admin, proporcao=1.0)

            self.stdout.write(self.style.SUCCESS("Patricia Rocha (Australia Visitante pago, form completo) criada."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
