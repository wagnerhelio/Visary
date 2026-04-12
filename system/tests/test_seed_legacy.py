from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from system.management.commands.seed_legacy import Command, parse_decimal, parse_decimal_strict


class SeedLegacyHelpersTests(SimpleTestCase):
    def test_parse_decimal_with_dot_decimal_separator(self):
        self.assertEqual(parse_decimal("1234.56"), Decimal("1234.56"))

    def test_parse_decimal_strict_rejeita_texto_invalido(self):
        self.assertIsNone(parse_decimal_strict("abc123"))
        self.assertEqual(parse_decimal_strict("1234.56"), Decimal("1234.56"))

    def test_build_process_groups_ignora_referencias_orfas(self):
        legacy = {
            "processos": [{"id": 1}, {"id": 2}],
            "processo_clientes": [
                {"id_processo_cliente": 1, "id_processo_principal": 999},
                {"id_processo_cliente": 888, "id_processo_principal": 2},
            ],
        }

        groups = Command()._build_process_groups(legacy)

        self.assertEqual(groups[1], 1)
        self.assertEqual(groups[2], 2)
        self.assertNotIn(888, groups)

    def test_resolve_assessor_for_cliente_row_por_email(self):
        command = Command()
        default = SimpleNamespace(pk=10, nome="Default")
        yan = SimpleNamespace(pk=20, nome="Yan Machado")

        by_email = {"yan.hmachado@visary.com.br": yan}
        by_name = {"yan machado": yan}
        row = {
            "responsavel_email": "YAN.HMACHADO@VISARY.COM.BR",
            "responsavel_name": "YAN MACHADO",
        }

        resolved = command._resolve_advisor_for_client_row(row, default, by_email, by_name)

        self.assertEqual(resolved.pk, yan.pk)

    def test_parse_legacy_percentage_limits_range(self):
        command = Command()
        self.assertEqual(command._parse_legacy_percentage("150"), 100)
        self.assertEqual(command._parse_legacy_percentage("-10"), 0)
        self.assertEqual(command._parse_legacy_percentage("42%"), 42)

    def test_extract_answer_value_fallback_por_nome_campo_exato(self):
        command = Command()
        context = {
            "cliente": {"nome_mae": "Maria Silva"},
            "processo": {},
            "passaportes": {},
            "dados_escolas": {},
            "dados_financeiros": {},
        }

        answer = command._extract_answer_value("Nome Mãe", context)

        self.assertEqual(answer, "Maria Silva")

    def test_extract_answer_value_nao_confunde_rg_com_orgao_emissor(self):
        command = Command()
        context = {
            "cliente": {"rg": "5285578", "orgao_emissor": None},
            "processo": {},
            "passaportes": {"orgao_emissor": "SR/PF/GO"},
            "dados_escolas": {},
            "dados_financeiros": {},
        }

        answer = command._extract_answer_value("Órgão Emissor", context)

        self.assertEqual(answer, "SR/PF/GO")

    def test_extract_answer_value_nao_faz_match_parcial_perigoso(self):
        command = Command()
        context = {
            "cliente": {"rg": "5285578"},
            "processo": {},
            "passaportes": {},
            "dados_escolas": {},
            "dados_financeiros": {},
        }

        answer = command._extract_answer_value("Cargo", context)

        self.assertIsNone(answer)

    def test_collect_legacy_partner_links_usa_cliente_parceiro_do_processo(self):
        command = Command()
        legacy = {
            "processos": [
                {"cliente_id": 10, "parceiro_id": 2},
                {"cliente_id": 11, "parceiro_id": 3},
                {"cliente_id": 10, "parceiro_id": 2},
                {"cliente_id": 12, "parceiro_id": None},
            ]
        }

        links = command._collect_legacy_partner_links(legacy)

        self.assertEqual(links, {10: 2, 11: 3})

    def test_legacy_cronograma_maps_ordena_por_atualizacao(self):
        command = Command()
        legacy = {
            "situacao_processos": [
                {"id": 1, "nome": "Preencher ficha cadastral"},
                {"id": 2, "nome": "Enviar documento para avaliacao"},
            ],
            "cronograma_processos": [
                {"id": 20, "processo_id": 7, "situacao_id": 2, "updated_at": "2026-03-10 12:00:00", "created_at": "2026-03-10 12:00:00"},
                {"id": 10, "processo_id": 7, "situacao_id": 1, "updated_at": "2026-03-09 12:00:00", "created_at": "2026-03-09 12:00:00"},
            ],
        }

        situacao_by_id, cronograma_by_process = command._legacy_cronograma_maps(legacy)

        self.assertEqual(situacao_by_id[1], "preencher ficha cadastral")
        self.assertEqual([int(item["id"]) for item in cronograma_by_process[7]], [10, 20])
