from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from system.models import (
    ConsultancyClient,
    ConsultancyUser,
    DestinationCountry,
    Process,
    Profile,
    Trip,
    TripClient,
    VisaForm,
    VisaType,
)

User = get_user_model()


class ScopedVsGlobalListingsTests(TestCase):
    def setUp(self):
        self.perfil_atendente = Profile.objects.create(
            name="Atendente Teste",
            can_create=False,
            can_view=True,
            can_update=False,
            can_delete=False,
            is_active=True,
        )

        self.assessor_a = ConsultancyUser.objects.create(
            name="Assessor A",
            email="assessor.a@visary.test",
            profile=self.perfil_atendente,
            password="!",
            is_active=True,
        )
        self.assessor_a.set_password("x")
        self.assessor_a.save(update_fields=["password", "updated_at"])

        self.assessor_b = ConsultancyUser.objects.create(
            name="Assessor B",
            email="assessor.b@visary.test",
            profile=self.perfil_atendente,
            password="!",
            is_active=True,
        )
        self.assessor_b.set_password("x")
        self.assessor_b.save(update_fields=["password", "updated_at"])

        self.auth_user_a = User.objects.create_user(
            username=self.assessor_a.email,
            email=self.assessor_a.email,
            password="senha-segura-123",
        )
        self.auth_user_b = User.objects.create_user(
            username=self.assessor_b.email,
            email=self.assessor_b.email,
            password="senha-segura-123",
        )

        self.cliente_a = self._criar_cliente(
            nome="Cliente",
            sobrenome="Assessor A",
            cpf="111.111.111-11",
            assessor=self.assessor_a,
            criado_por=self.auth_user_a,
        )
        self.cliente_b = self._criar_cliente(
            nome="Cliente",
            sobrenome="Assessor B",
            cpf="222.222.222-22",
            assessor=self.assessor_b,
            criado_por=self.auth_user_b,
        )

        self.pais = DestinationCountry.objects.create(
            name="Canada",
            iso_code="CAN",
            is_active=True,
            created_by=self.auth_user_a,
        )
        self.tipo_visto = VisaType.objects.create(
            destination_country=self.pais,
            name="Turismo",
            description="",
            is_active=True,
            created_by=self.auth_user_a,
        )
        VisaForm.objects.create(visa_type=self.tipo_visto, is_active=True)

        self.viagem_a = Trip.objects.create(
            assigned_advisor=self.assessor_a,
            destination_country=self.pais,
            visa_type=self.tipo_visto,
            planned_departure_date=date(2026, 6, 1),
            planned_return_date=date(2026, 6, 20),
            advisory_fee=1000,
            created_by=self.auth_user_a,
        )
        TripClient.objects.create(
            trip=self.viagem_a,
            client=self.cliente_a,
            visa_type=self.tipo_visto,
            role="primary",
        )

        self.viagem_b = Trip.objects.create(
            assigned_advisor=self.assessor_b,
            destination_country=self.pais,
            visa_type=self.tipo_visto,
            planned_departure_date=date(2026, 7, 1),
            planned_return_date=date(2026, 7, 20),
            advisory_fee=1500,
            created_by=self.auth_user_b,
        )
        TripClient.objects.create(
            trip=self.viagem_b,
            client=self.cliente_b,
            visa_type=self.tipo_visto,
            role="primary",
        )

        Process.objects.create(
            trip=self.viagem_a,
            client=self.cliente_a,
            assigned_advisor=self.assessor_a,
            created_by=self.auth_user_a,
        )
        Process.objects.create(
            trip=self.viagem_b,
            client=self.cliente_b,
            assigned_advisor=self.assessor_b,
            created_by=self.auth_user_b,
        )

    def _criar_cliente(self, nome, sobrenome, cpf, assessor, criado_por):
        return ConsultancyClient.objects.create(
            assigned_advisor=assessor,
            first_name=nome,
            last_name=sobrenome,
            cpf=cpf,
            birth_date=date(1990, 1, 1),
            nationality="Brasileira",
            phone="(11) 99999-9999",
            email=f"{cpf.replace('.', '').replace('-', '')}@email.test",
            password="!",
            created_by=criado_por,
        )

    def test_home_clientes_mostra_apenas_clientes_vinculados_ao_assessor(self):
        self.client.force_login(self.auth_user_a)

        response = self.client.get(reverse("system:home_clients"))

        self.assertEqual(response.status_code, 200)
        nomes = {item["client"].full_name for item in response.context["clients_with_status"]}
        self.assertIn(self.cliente_a.full_name, nomes)
        self.assertNotIn(self.cliente_b.full_name, nomes)

    def test_listar_clientes_exibe_todos_os_clientes_independente_do_assessor(self):
        self.client.force_login(self.auth_user_a)

        response = self.client.get(reverse("system:list_clients_view"))

        self.assertEqual(response.status_code, 200)
        nomes = {item["client"].full_name for item in response.context["clients_with_status"]}
        self.assertIn(self.cliente_a.full_name, nomes)
        self.assertIn(self.cliente_b.full_name, nomes)

    def test_listar_viagens_exibe_viagens_de_todos_os_assessores(self):
        self.client.force_login(self.auth_user_a)

        response = self.client.get(reverse("system:list_trips"))

        self.assertEqual(response.status_code, 200)
        viagens_ids = {item["trip"].pk for item in response.context["trips_with_info"]}
        self.assertIn(self.viagem_a.pk, viagens_ids)
        self.assertIn(self.viagem_b.pk, viagens_ids)

    def test_listar_processos_exibe_processos_de_todos_os_assessores(self):
        self.client.force_login(self.auth_user_a)

        response = self.client.get(reverse("system:list_processes"))

        self.assertEqual(response.status_code, 200)
        processos_clientes = {processo.client_id for processo in response.context["processes"]}
        self.assertIn(self.cliente_a.pk, processos_clientes)
        self.assertIn(self.cliente_b.pk, processos_clientes)

    def test_listar_formularios_exibe_clientes_de_todos_os_assessores(self):
        self.client.force_login(self.auth_user_a)

        response = self.client.get(reverse("system:list_forms"))

        self.assertEqual(response.status_code, 200)
        clientes_ids = {
            cliente_info["client"].pk
            for item in response.context["form_responses"]
            for cliente_info in item["clients"]
        }
        self.assertIn(self.cliente_a.pk, clientes_ids)
        self.assertIn(self.cliente_b.pk, clientes_ids)
