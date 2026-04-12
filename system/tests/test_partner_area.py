from datetime import date
import unittest

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from system.models import ConsultancyClient, ConsultancyUser, Partner, Profile

User = get_user_model()


class PartnerAreaTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        required = {
            "system_profile",
            "system_consultancyuser",
            "system_partner",
            "system_consultancyclient",
        }
        available = set(connection.introspection.table_names())
        if not required.issubset(available):
            raise unittest.SkipTest("Tabelas do app system indisponíveis no ambiente de teste.")

    def setUp(self):
        self.profile = Profile.objects.create(
            name="Atendente Teste",
            can_create=False,
            can_view=True,
            can_update=False,
            can_delete=False,
            is_active=True,
        )
        self.advisor = ConsultancyUser.objects.create(
            name="Assessor Teste",
            email="assessor.partner@test.com",
            profile=self.profile,
            password="!",
            is_active=True,
        )
        self.advisor.set_password("unused")
        self.advisor.save(update_fields=["password", "updated_at"])

        self.auth_user = User.objects.create_user(
            username="admin.partner@test.com",
            email="admin.partner@test.com",
            password="SenhaForte123!",
        )

        self.partner_a = Partner.objects.create(
            contact_name="Parceiro A",
            company_name="Empresa A",
            email="parceiro.a@test.com",
            password="!",
            created_by=self.auth_user,
            is_active=True,
        )
        self.partner_a.set_password("PartnerA@123")
        self.partner_a.save(update_fields=["password", "updated_at"])

        self.partner_b = Partner.objects.create(
            contact_name="Parceiro B",
            company_name="Empresa B",
            email="parceiro.b@test.com",
            password="!",
            created_by=self.auth_user,
            is_active=True,
        )
        self.partner_b.set_password("PartnerB@123")
        self.partner_b.save(update_fields=["password", "updated_at"])

        self.cliente_partner_a = self._criar_cliente(
            first_name="Cliente",
            last_name="Parceiro A",
            cpf="123.456.789-01",
            parceiro=self.partner_a,
        )
        self._criar_cliente(
            first_name="Cliente",
            last_name="Parceiro B",
            cpf="123.456.789-02",
            parceiro=self.partner_b,
        )

    def _criar_cliente(self, first_name, last_name, cpf, parceiro):
        return ConsultancyClient.objects.create(
            assigned_advisor=self.advisor,
            first_name=first_name,
            last_name=last_name,
            cpf=cpf,
            birth_date=date(1990, 1, 1),
            nationality="Brasileira",
            phone="(11) 99999-0000",
            email=f"{cpf.replace('.', '').replace('-', '')}@mail.test",
            password="!",
            created_by=self.auth_user,
            referring_partner=parceiro,
        )

    def test_login_de_parceiro_redireciona_para_dashboard(self):
        response = self.client.post(
            reverse("system:login"),
            {
                "identifier": "parceiro.a@test.com",
                "password": "PartnerA@123",
                "remember_me": "on",
            },
        )

        self.assertRedirects(response, reverse("system:partner_dashboard"))
        self.assertEqual(self.client.session.get("partner_id"), self.partner_a.pk)

    def test_dashboard_parceiro_exibe_apenas_clientes_vinculados(self):
        session = self.client.session
        session["partner_id"] = self.partner_a.pk
        session["partner_name"] = self.partner_a.contact_name
        session.save()

        response = self.client.get(reverse("system:partner_dashboard"))

        self.assertEqual(response.status_code, 200)
        items = list(response.context["clients_with_status"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["client"].pk, self.cliente_partner_a.pk)

    def test_dashboard_parceiro_exibe_link_visualizar_cliente(self):
        session = self.client.session
        session["partner_id"] = self.partner_a.pk
        session["partner_name"] = self.partner_a.contact_name
        session.save()

        response = self.client.get(reverse("system:partner_dashboard"))

        url = reverse("system:partner_view_client", args=[self.cliente_partner_a.pk])
        self.assertContains(response, url)

    def test_dashboard_parceiro_sem_sessao_redireciona_para_login(self):
        response = self.client.get(reverse("system:partner_dashboard"))
        self.assertRedirects(response, reverse("system:login"))
