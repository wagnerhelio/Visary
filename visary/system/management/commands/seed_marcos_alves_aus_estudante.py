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
    help = "Marcos Alves - Estudo Australia Estudante, financeiro pendente, formulario 30%."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("yan.hmachado@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor yan.hmachado@visary.com.br nao encontrado."))
                raise SystemExit(1)

            marcos = criar_cliente(
                assessor, admin, "Marcos Antonio Alves",
                "marcos_alves_aus_estudante",
                datetime.date(1998, 5, 22),
                email="marcos.alves@gmail.com",
                telefone="(62) 98807-7700",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Austrália",
                "Visto de Estudante",
                datetime.date(2027, 1, 20),
                datetime.date(2027, 7, 20),
                valor=400.00,
            )
            adicionar_cliente_viagem(viagem, marcos)
            criar_financeiro(viagem, marcos, assessor, admin, 400.00, StatusFinanceiro.PENDENTE)
            preencher_formulario(viagem, marcos, admin, proporcao=0.3)

            self.stdout.write(self.style.SUCCESS("Marcos Alves (Australia Estudante pendente, form 30%) criado."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
