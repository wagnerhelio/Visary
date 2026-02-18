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
    help = "Carlos Mendes - Estudo EUA F1, financeiro pendente, formulario metade."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("juliana.lopes@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor juliana.lopes@visary.com.br nao encontrado."))
                raise SystemExit(1)

            carlos = criar_cliente(
                assessor, admin, "Carlos Eduardo Mendes",
                "carlos_mendes_eua_f1",
                datetime.date(2001, 9, 3),
                email="carlos.mendes@hotmail.com",
                telefone="(62) 98802-2200",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Estados Unidos",
                "F1 (visto oficial de estudante)",
                datetime.date(2026, 9, 5),
                datetime.date(2027, 6, 30),
                valor=400.00,
            )
            adicionar_cliente_viagem(viagem, carlos)
            criar_financeiro(viagem, carlos, assessor, admin, 400.00, StatusFinanceiro.PENDENTE)
            preencher_formulario(viagem, carlos, admin, proporcao=0.5)

            self.stdout.write(self.style.SUCCESS("Carlos Mendes (EUA F1 pendente, form 50%) criado."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
