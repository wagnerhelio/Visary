from django.core.management.base import BaseCommand

from system.management.commands._seed_helpers import (
    criar_partner,
    get_admin_user,
)


PARCEIROS = [
    {
        "nome_responsavel": "Gustavo Henrique Prado",
        "nome_empresa": "Intercâmbio Global Ltda",
        "cpf_seed": "partner_gustavo_prado",
        "email": "gustavo.prado@intercambioglobal.com.br",
        "telefone": "(11) 3322-5500",
        "segmento": "Agência de intercâmbio",
    },
    {
        "nome_responsavel": "Isabela Moura",
        "nome_empresa": "Estudar no Exterior ME",
        "cpf_seed": "partner_isabela_moura",
        "email": "isabela.moura@estudarnoexterior.com.br",
        "telefone": "(21) 2233-7700",
        "segmento": "Consultoria educacional",
    },
]


class Command(BaseCommand):
    help = "Cria parceiros indicadores de teste."

    def handle(self, *args, **options):
        admin = get_admin_user()
        for dados in PARCEIROS:
            partner = criar_partner(
                admin,
                dados["nome_responsavel"],
                dados["nome_empresa"],
                dados["cpf_seed"],
                dados["email"],
                dados["telefone"],
                dados["segmento"],
            )
            self.stdout.write(self.style.SUCCESS(
                f"Parceiro '{partner.nome_empresa}' criado/atualizado."
            ))
