from django.core.management.base import BaseCommand
from system.models import UsuarioConsultoria, Perfil


ASSESSORES = [
    {
        "nome": "Camila Borges",
        "email": "camila.borges@visary.com.br",
        "senha": "Borges1",
        "perfil": "Atendente",
    },
    {
        "nome": "Rafael Teixeira",
        "email": "rafael.teixeira@visary.com.br",
        "senha": "Teixeira1",
        "perfil": "Administrador",
    },
]


class Command(BaseCommand):
    help = "Cria assessores adicionais de teste (Camila Borges e Rafael Teixeira)."

    def handle(self, *args, **options):
        for dados in ASSESSORES:
            perfil = Perfil.objects.filter(nome=dados["perfil"]).first()
            if not perfil:
                self.stderr.write(self.style.ERROR(
                    f"Perfil '{dados['perfil']}' nao encontrado. Execute migrate primeiro."
                ))
                continue

            usuario, created = UsuarioConsultoria.objects.get_or_create(
                email=dados["email"],
                defaults={
                    "nome": dados["nome"],
                    "perfil": perfil,
                    "ativo": True,
                },
            )
            usuario.nome = dados["nome"]
            usuario.perfil = perfil
            usuario.ativo = True
            usuario.set_password(dados["senha"])
            usuario.save()

            acao = "criado" if created else "atualizado"
            self.stdout.write(self.style.SUCCESS(f"Assessor {dados['nome']} {acao}."))
