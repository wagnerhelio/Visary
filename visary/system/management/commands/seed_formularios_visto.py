import json
import re
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from system.models import (
    EtapaFormularioVisto,
    FormularioVisto,
    OpcaoSelecao,
    PerguntaFormulario,
    TipoVisto,
)

STAGES_MAP = {
    "B1 / B2 (Turismo, Neg\u00f3cios ou Estudos Recreativos)": [
        (1, "Dados Pessoais"),
        (2, "Dados da Viagem"),
        (3, "Contato Brasil"),
        (4, "Passaporte"),
        (5, "Contato EUA / Acompanhante"),
        (6, "Parente nos EUA"),
        (7, "Dados do Cônjuge"),
        (8, "Dados dos Pais"),
        (9, "Ocupação Atual"),
        (10, "Empregos Anteriores"),
        (11, "Informações Educacionais"),
        (12, "Idioma e Experiência"),
        (13, "Perguntas de Segurança"),
        (14, "Comentários Adicionais"),
        (15, "Agendamento"),
    ],
    "F1 (visto oficial de estudante)": [
        (1, "Dados Pessoais"),
        (2, "Endereço Brasil"),
        (3, "Contato Brasil"),
        (4, "Dados da Viagem"),
        (5, "Redes Sociais"),
        (6, "Custeio da Viagem"),
        (7, "Dados da Escola"),
        (8, "Acompanhantes"),
        (9, "Empregos e Estudos Anteriores"),
        (10, "Comentários Adicionais"),
        (11, "Contato nos EUA (1)"),
        (12, "Contato nos EUA (2)"),
        (13, "Agendamento"),
        (14, "Declaração"),
    ],
    "J1 (visto de intercâmbio)": [
        (1, "Dados Pessoais"),
        (2, "Endereço Brasil"),
        (3, "Contato Brasil"),
        (4, "Dados da Viagem"),
        (5, "Redes Sociais"),
        (6, "Custeio da Viagem"),
        (7, "Dados da Escola"),
        (8, "Acompanhantes"),
        (9, "Empregos e Estudos Anteriores"),
        (10, "Comentários Adicionais"),
        (11, "Contato nos EUA (1)"),
        (12, "Contato nos EUA (2)"),
        (13, "Agendamento"),
        (14, "Declaração"),
    ],
    "Estudante - Study Permit": [
        (1, "Dados Pessoais"),
        (2, "Cônjuge / Estado Civil"),
        (3, "Perguntas de Segurança"),
        (4, "Passaporte"),
        (5, "Contato Brasil"),
        (6, "Dados da Viagem e Escola"),
        (7, "Estudos Anteriores"),
        (8, "Ocupação Atual"),
        (9, "Ocupações Anteriores"),
        (10, "Saúde"),
        (11, "Detalhes de Segurança"),
        (12, "Dados da Mãe"),
        (13, "Dados do Pai"),
        (14, "Dados dos Filhos"),
        (15, "Viagem e Idiomas"),
    ],
    "Temporary Resident Visa - TRV": [
        (1, "Dados Pessoais"),
        (2, "Cônjuge"),
        (3, "Perguntas de Segurança"),
        (4, "Passaporte"),
        (5, "Contato Brasil"),
        (6, "Dados da Viagem"),
        (7, "Estudos Anteriores"),
        (8, "Ocupação Atual"),
        (9, "Atividade Últimos 10 Anos"),
        (10, "Ocupações Anteriores"),
        (11, "Saúde e Vistos"),
        (12, "Visto Negado Outro País"),
        (13, "Detalhes de Segurança"),
        (14, "Dados da Mãe"),
        (15, "Dados do Pai"),
        (16, "Dados dos Filhos"),
        (17, "Viagem e Idiomas"),
    ],
    "Visto de Estudante": [
        (1, "Aplicação"),
        (2, "Dados Pessoais"),
        (3, "Cônjuge"),
        (4, "Documentos de Identidade"),
        (5, "Endereço Brasil"),
        (6, "Família no Brasil"),
        (7, "Parentes"),
        (8, "Vistos Anteriores"),
        (9, "Dados da Viagem"),
        (10, "Estudos e Passaporte"),
        (11, "Dados da Escola"),
        (12, "Contato Emergencial"),
        (13, "Inglês"),
        (14, "Estudos de Inglês"),
        (15, "Trabalho Atual"),
        (16, "Custeio"),
        (17, "Renda e Fundos"),
        (18, "Saúde"),
        (19, "Saúde Detalhada"),
        (20, "Criminal e Imigração"),
        (21, "Militar"),
        (22, "Declarações"),
        (23, "Pagamento"),
    ],
    "Visto de Visitante": [
        (1, "Dados Pessoais"),
        (2, "Cônjuge"),
        (3, "Endereço Brasil"),
        (4, "Passaporte"),
        (5, "Perguntas de Segurança"),
        (6, "Passaporte e Nacionalidade"),
        (7, "Ocupação Atual"),
        (8, "Custeio da Viagem"),
        (9, "Dados da Viagem"),
        (10, "Visitas Anteriores"),
        (11, "Estudos"),
        (12, "Família no Brasil"),
        (13, "Filhos"),
        (14, "Viagens Anteriores"),
        (15, "Saúde"),
        (16, "Saúde Detalhada"),
        (17, "Responsável Legal (1)"),
        (18, "Responsável Legal (2)"),
        (19, "Declarações"),
    ],
}


class Command(BaseCommand):
    help = "Popula formularios de visto a partir de static/forms_ini"

    def add_arguments(self, parser):
        parser.add_argument("--tipo-visto", help="Nome exato do tipo de visto")
        parser.add_argument("--arquivo", help="Nome do arquivo JSON em static/forms_ini")

    def handle(self, *args, **options):
        call_command("seed_tipos_visto")

        forms_dir = Path(settings.BASE_DIR) / "static" / "forms_ini"
        if not forms_dir.exists():
            raise CommandError(f"Diretorio nao encontrado: {forms_dir}")

        types_by_name = {
            self._normalize(tipo.nome): tipo for tipo in TipoVisto.objects.select_related("pais_destino")
        }

        filtro_tipo = (options.get("tipo_visto") or "").strip()
        filtro_arquivo = (options.get("arquivo") or "").strip()

        files = sorted(forms_dir.glob("*.json"))
        if filtro_arquivo:
            files = [arquivo for arquivo in files if arquivo.name == filtro_arquivo]
            if not files:
                raise CommandError(f"Arquivo nao encontrado em forms_ini: {filtro_arquivo}")

        for json_file in files:
            payload = json.loads(json_file.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                continue

            for form_item in payload:
                tipo_nome = form_item.get("tipo_visto", "").strip()
                if filtro_tipo and tipo_nome != filtro_tipo:
                    continue

                tipo = types_by_name.get(self._normalize(tipo_nome))
                if not tipo:
                    raise CommandError(f"Tipo de visto nao encontrado para formulario: {tipo_nome}")

                formulario, _ = FormularioVisto.objects.get_or_create(tipo_visto=tipo)
                formulario.ativo = True
                formulario.save(update_fields=["ativo", "atualizado_em"])

                stages = STAGES_MAP.get(tipo_nome, [])
                etapas_existentes = {
                    e.ordem: e for e in EtapaFormularioVisto.objects.filter(formulario=formulario)
                }

                for ordem, nome in stages:
                    etapa, created = EtapaFormularioVisto.objects.get_or_create(
                        formulario=formulario,
                        ordem=ordem,
                        defaults={"nome": nome},
                    )
                    if not created and etapa.nome != nome:
                        etapa.nome = nome
                        etapa.save(update_fields=["nome"])

                stage_map = {
                    e.ordem: e for e in EtapaFormularioVisto.objects.filter(formulario=formulario)
                }

                for pergunta_item in form_item.get("perguntas", []):
                    etapa_ordem = pergunta_item.get("etapa")
                    etapa_obj = stage_map.get(etapa_ordem) if etapa_ordem else None

                    pergunta, _ = PerguntaFormulario.objects.get_or_create(
                        formulario=formulario,
                        ordem=pergunta_item["ordem"],
                    )
                    pergunta.pergunta = pergunta_item["pergunta"]
                    pergunta.tipo_campo = pergunta_item["tipo_campo"]
                    pergunta.obrigatorio = pergunta_item.get("obrigatorio", False)
                    pergunta.ativo = pergunta_item.get("ativo", True)
                    pergunta.regra_exibicao = pergunta_item.get("regra_exibicao")
                    pergunta.etapa = etapa_obj
                    pergunta.save()

                    if pergunta.tipo_campo != "selecao":
                        continue

                    for ordem, texto in enumerate(pergunta_item.get("opcoes", []), start=1):
                        opcao, _ = OpcaoSelecao.objects.get_or_create(pergunta=pergunta, ordem=ordem)
                        opcao.texto = texto
                        opcao.ativo = True
                        opcao.save()

        self.stdout.write(self.style.SUCCESS("Seed de formularios de visto concluida."))

    def _normalize(self, value):
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = text.encode("ascii", "ignore").decode("ascii")
        text = text.lower().strip()
        return re.sub(r"[^a-z0-9]+", "", text)
