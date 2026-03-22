from datetime import date
import unittest

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from system.models import ClienteConsultoria, Partner, Perfil, UsuarioConsultoria


User = get_user_model()


class PartnerAreaTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tabelas_necessarias = {
            "system_perfil",
            "system_usuarioconsultoria",
            "system_partner",
            "system_clienteconsultoria",
        }
        tabelas_disponiveis = set(connection.introspection.table_names())
        if not tabelas_necessarias.issubset(tabelas_disponiveis):
            raise unittest.SkipTest("Tabelas do app system indisponíveis no ambiente de teste.")

    def setUp(self):
        self.perfil = Perfil.objects.create(
            nome="Atendente Teste",
            pode_criar=False,
            pode_visualizar=True,
            pode_atualizar=False,
            pode_excluir=False,
            ativo=True,
        )
        self.assessor = UsuarioConsultoria.objects.create(
            nome="Assessor Teste",
            email="assessor.partner@test.com",
            senha="hash",
            perfil=self.perfil,
            ativo=True,
        )
        self.auth_user = User.objects.create_user(
            username="admin.partner@test.com",
            email="admin.partner@test.com",
            password="SenhaForte123!",
        )

        self.partner_a = Partner.objects.create(
            nome_responsavel="Parceiro A",
            nome_empresa="Empresa A",
            email="parceiro.a@test.com",
            senha="",
            criado_por=self.auth_user,
            ativo=True,
        )
        self.partner_a.set_password("PartnerA@123")
        self.partner_a.save(update_fields=["senha", "atualizado_em"])

        self.partner_b = Partner.objects.create(
            nome_responsavel="Parceiro B",
            nome_empresa="Empresa B",
            email="parceiro.b@test.com",
            senha="",
            criado_por=self.auth_user,
            ativo=True,
        )
        self.partner_b.set_password("PartnerB@123")
        self.partner_b.save(update_fields=["senha", "atualizado_em"])

        self.cliente_partner_a = self._criar_cliente(
            nome="Cliente do Parceiro A",
            cpf="123.456.789-01",
            parceiro=self.partner_a,
        )
        self._criar_cliente(
            nome="Cliente do Parceiro B",
            cpf="123.456.789-02",
            parceiro=self.partner_b,
        )

    def _criar_cliente(self, nome, cpf, parceiro):
        return ClienteConsultoria.objects.create(
            assessor_responsavel=self.assessor,
            nome=nome,
            cpf=cpf,
            data_nascimento=date(1990, 1, 1),
            nacionalidade="Brasileira",
            telefone="(11) 99999-0000",
            email=f"{cpf.replace('.', '').replace('-', '')}@mail.test",
            senha="hash",
            criado_por=self.auth_user,
            parceiro_indicador=parceiro,
        )

    def test_login_de_parceiro_redireciona_para_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {
                "identifier": "parceiro.a@test.com",
                "password": "PartnerA@123",
                "remember_me": "on",
            },
        )

        self.assertRedirects(response, reverse("system:parceiro_dashboard"))
        self.assertEqual(self.client.session.get("partner_id"), self.partner_a.pk)

    def test_dashboard_parceiro_exibe_apenas_clientes_vinculados(self):
        session = self.client.session
        session["partner_id"] = self.partner_a.pk
        session["partner_nome"] = self.partner_a.nome_responsavel
        session.save()

        response = self.client.get(reverse("system:parceiro_dashboard"))

        self.assertEqual(response.status_code, 200)
        familias = list(response.context["familias"])
        self.assertEqual(len(familias), 1)
        self.assertEqual(familias[0]["principal"]["cliente"].pk, self.cliente_partner_a.pk)
        self.assertIn("status_viagem", familias[0]["principal"])
        self.assertIn("status_processo", familias[0]["principal"])
        self.assertIn("status_formulario", familias[0]["principal"])

    def test_dashboard_parceiro_exibe_link_visualizar_cliente(self):
        session = self.client.session
        session["partner_id"] = self.partner_a.pk
        session["partner_nome"] = self.partner_a.nome_responsavel
        session.save()

        response = self.client.get(reverse("system:parceiro_dashboard"))

        self.assertContains(
            response,
            reverse("system:parceiro_visualizar_cliente", args=[self.cliente_partner_a.pk]),
        )

    def test_dashboard_parceiro_sem_sessao_redireciona_para_login(self):
        response = self.client.get(reverse("system:parceiro_dashboard"))
        self.assertRedirects(response, reverse("login"))
