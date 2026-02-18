import datetime
from django.core.management.base import BaseCommand
from system.management.commands._seed_helpers import (
    get_admin_user, get_assessor,
    criar_cliente,
    obter_ou_criar_viagem, adicionar_cliente_viagem,
    criar_processo, criar_etapas_processo,
)
from consultancy.models import StatusFinanceiro


class Command(BaseCommand):
    help = "Amanda Nunes - Estudo EUA F1, processo aberto, sem financeiro, sem formulario."

    def handle(self, *args, **options):
        try:
            admin = get_admin_user()
            assessor = get_assessor("yan.hmachado@visary.com.br")
            if not assessor:
                self.stderr.write(self.style.ERROR("Assessor yan.hmachado@visary.com.br nao encontrado."))
                raise SystemExit(1)

            amanda = criar_cliente(
                assessor, admin, "Amanda Cristina Nunes",
                "amanda_nunes_eua_f1",
                datetime.date(2002, 1, 19),
                email="amanda.nunes@gmail.com",
                telefone="(62) 98810-0011",
            )
            viagem = obter_ou_criar_viagem(
                assessor, admin,
                "Estados Unidos",
                "F1 (visto oficial de estudante)",
                datetime.date(2027, 3, 1),
                datetime.date(2028, 5, 31),
                valor=400.00,
            )
            adicionar_cliente_viagem(viagem, amanda)
            processo = criar_processo(viagem, amanda, assessor, admin)
            criar_etapas_processo(processo, proporcao_concluidas=0.0)

            self.stdout.write(self.style.SUCCESS("Amanda Nunes (EUA F1 com processo, sem financeiro) criada."))
        except SystemExit:
            raise
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Erro: {exc}"))
            raise SystemExit(1)
