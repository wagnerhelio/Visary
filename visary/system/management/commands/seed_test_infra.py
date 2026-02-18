from django.core.management.base import BaseCommand

from system.management.commands._seed_helpers import (
    get_admin_user,
    seed_formulario_para_visto,
)
from consultancy.models import PaisDestino, TipoVisto


PAISES_VISTOS_FORMULARIOS = [
    {
        "pais": "Austrália",
        "codigo_iso": "AUS",
        "vistos": [
            {
                "nome": "Visto de Visitante",
                "formulario_json": "FORMULARIO_AUSTRALIA_VISITANTE.json",
            },
            {
                "nome": "Visto de Estudante",
                "formulario_json": "FORMULARIO_AUSTRALIA_ESTUDANTE.json",
            },
        ],
    },
    {
        "pais": "Canadá",
        "codigo_iso": "CAN",
        "vistos": [
            {
                "nome": "Temporary Resident Visa - TRV",
                "formulario_json": "FORMULARIO_CANADA_TRV.json",
            },
            {
                "nome": "Estudante - Study Permit",
                "formulario_json": "FORMULARIO_CANADA_ESTUDANTE.json",
            },
        ],
    },
    {
        "pais": "Estados Unidos",
        "codigo_iso": "USA",
        "vistos": [
            {
                "nome": "B1 / B2 (Turismo, Negócios ou Estudos Recreativos)",
                "formulario_json": "FORMULARIO_EUA_B1_B2.json",
            },
            {
                "nome": "F1 (visto oficial de estudante)",
                "formulario_json": "FORMULARIO_EUA_F1.json",
            },
            {
                "nome": "J1 (visto de intercambio)",
                "formulario_json": "FORMULARIO_EUA_J1.json",
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Cria paises, vistos e formularios reais de teste (AUS, CAN, EUA)."

    def handle(self, *args, **options):
        admin = get_admin_user()

        for bloco_pais in PAISES_VISTOS_FORMULARIOS:
            pais, pais_criado = PaisDestino.objects.get_or_create(
                nome=bloco_pais["pais"],
                defaults={
                    "codigo_iso": bloco_pais["codigo_iso"],
                    "ativo": True,
                    "criado_por": admin,
                },
            )
            acao_pais = "criado" if pais_criado else "existente"
            self.stdout.write(f"  Pais {pais.nome} ({acao_pais})")

            for bloco_visto in bloco_pais["vistos"]:
                tipo_visto, visto_criado = TipoVisto.objects.get_or_create(
                    pais_destino=pais,
                    nome=bloco_visto["nome"],
                    defaults={
                        "ativo": True,
                        "criado_por": admin,
                    },
                )
                acao_visto = "criado" if visto_criado else "existente"
                self.stdout.write(f"    Visto '{tipo_visto.nome}' ({acao_visto})")

                try:
                    seed_formulario_para_visto(tipo_visto, bloco_visto["formulario_json"])
                    self.stdout.write(f"      Formulario carregado: {bloco_visto['formulario_json']}")
                except FileNotFoundError:
                    self.stderr.write(self.style.ERROR(
                        f"      Arquivo nao encontrado: {bloco_visto['formulario_json']}"
                    ))
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"      Erro ao carregar formulario: {exc}"))

        self.stdout.write(self.style.SUCCESS("Infraestrutura de teste criada com sucesso."))
