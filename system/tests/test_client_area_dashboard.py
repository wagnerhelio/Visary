from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from system.models import (
    ConsultancyClient,
    ConsultancyUser,
    DestinationCountry,
    FormQuestion,
    FormAnswer,
    SelectOption,
    Profile,
    Trip,
    TripClient,
    VisaForm,
    VisaFormStage,
    VisaType,
)

User = get_user_model()


class ClientAreaDashboardTests(TestCase):
    def setUp(self):
        self.profile = Profile.objects.create(
            name="Administrador Teste",
            can_create=True,
            can_view=True,
            can_update=True,
            can_delete=True,
            is_active=True,
        )
        self.consultant = ConsultancyUser.objects.create(
            name="Raquel Fleury",
            email="raquel.cliente.area@visary.test",
            profile=self.profile,
            password="!",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username=self.consultant.email,
            email=self.consultant.email,
            password="senha-segura-123",
        )
        self.country = DestinationCountry.objects.create(
            name="Australia",
            iso_code="AUS",
            is_active=True,
            created_by=self.user,
        )
        self.visa_type = VisaType.objects.create(
            destination_country=self.country,
            name="Visitante",
            description="",
            is_active=True,
            created_by=self.user,
        )
        self.visa_form = VisaForm.objects.create(
            visa_type=self.visa_type,
            is_active=True,
        )
        self.stage = VisaFormStage.objects.create(
            form=self.visa_form,
            name="Dados iniciais",
            order=1,
            is_active=True,
        )
        FormQuestion.objects.create(
            form=self.visa_form,
            stage=self.stage,
            question="Nome completo",
            field_type="text",
            is_required=True,
            order=1,
            is_active=True,
        )
        self.stage_two = VisaFormStage.objects.create(
            form=self.visa_form,
            name="Documentos",
            order=2,
            is_active=True,
        )
        FormQuestion.objects.create(
            form=self.visa_form,
            stage=self.stage_two,
            question="Número do passaporte",
            field_type="text",
            is_required=True,
            order=2,
            is_active=True,
        )
        FormQuestion.objects.create(
            form=self.visa_form,
            stage=self.stage,
            question="CPF",
            field_type="text",
            is_required=True,
            order=10,
            is_active=True,
        )

        self.primary_client = ConsultancyClient.objects.create(
            assigned_advisor=self.consultant,
            first_name="Cliente",
            last_name="Principal",
            cpf="123.456.789-00",
            birth_date=date(1990, 1, 1),
            nationality="Brasileira",
            phone="(11) 99999-0000",
            email="cliente.principal@example.test",
            password="!",
            created_by=self.user,
        )
        self.dependent_client = ConsultancyClient.objects.create(
            assigned_advisor=self.consultant,
            first_name="Cliente",
            last_name="Dependente",
            cpf="987.654.321-00",
            birth_date=date(2010, 5, 10),
            nationality="Brasileira",
            phone="(11) 98888-0000",
            email="cliente.dependente@example.test",
            password="!",
            created_by=self.user,
            primary_client=self.primary_client,
        )

        self.trip = Trip.objects.create(
            assigned_advisor=self.consultant,
            destination_country=self.country,
            visa_type=self.visa_type,
            planned_departure_date=date(2026, 4, 14),
            planned_return_date=date(2026, 4, 20),
            advisory_fee=500,
            created_by=self.user,
        )
        TripClient.objects.create(
            trip=self.trip,
            client=self.primary_client,
            visa_type=self.visa_type,
            role="primary",
        )
        TripClient.objects.create(
            trip=self.trip,
            client=self.dependent_client,
            visa_type=self.visa_type,
            role="dependent",
            trip_primary_client=self.primary_client,
        )

        session = self.client.session
        session["client_id"] = self.primary_client.pk
        session.save()

    def test_dashboard_shows_full_name_cpf_and_role_for_trip_members(self):
        response = self.client.get(reverse("system:client_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.primary_client.full_name)
        self.assertContains(response, self.dependent_client.full_name)
        self.assertContains(response, f"CPF: {self.primary_client.cpf}")
        self.assertContains(response, f"CPF: {self.dependent_client.cpf}")
        self.assertContains(response, "Principal")
        self.assertContains(response, "Dependente")
        self.assertContains(response, "Etapa atual: Dados iniciais")
        self.assertContains(response, "Pendentes no total: 2 de 3")
        self.assertContains(response, "Dados iniciais (Atual)")
        self.assertContains(response, "Documentos")
        self.assertContains(response, "1 pendente(s) de 2")
        self.assertContains(response, "1 pendente(s) de 1")

    def test_dashboard_hides_empty_stages_and_hides_spouse_stage_when_single(self):
        married_stage = VisaFormStage.objects.create(
            form=self.visa_form,
            name="Dados do Cônjuge",
            order=3,
            is_active=True,
        )
        civil_status = FormQuestion.objects.create(
            form=self.visa_form,
            stage=self.stage,
            question="Estado Civil",
            field_type="select",
            is_required=True,
            order=20,
            is_active=True,
        )
        opt_single = SelectOption.objects.create(question=civil_status, text="Solteiro(a)", order=1, is_active=True)
        SelectOption.objects.create(question=civil_status, text="Casado(a)", order=2, is_active=True)
        FormQuestion.objects.create(
            form=self.visa_form,
            stage=married_stage,
            question="Nome do cônjuge",
            field_type="text",
            is_required=False,
            order=21,
            is_active=True,
            display_rule={"type": "show_if", "question_order": 20, "value": ["Casado(a)"]},
        )
        FormAnswer.objects.create(
            trip=self.trip,
            client=self.primary_client,
            question=civil_status,
            answer_select=opt_single,
        )

        response = self.client.get(reverse("system:client_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Dados do Cônjuge")

    def test_dashboard_links_each_member_form_with_client_id(self):
        response = self.client.get(reverse("system:client_dashboard"))

        self.assertContains(
            response,
            f"{reverse('system:client_view_form', args=[self.trip.pk])}?client_id={self.primary_client.pk}",
        )
        self.assertContains(
            response,
            f"{reverse('system:client_view_form', args=[self.trip.pk])}?client_id={self.dependent_client.pk}",
        )

    def test_client_view_form_prefills_selected_dependent(self):
        question = FormQuestion.objects.create(
            form=self.visa_form,
            stage=self.stage,
            question="Nome",
            field_type="text",
            is_required=True,
            order=3,
            is_active=True,
        )

        response = self.client.get(
            reverse("system:client_view_form", args=[self.trip.pk]),
            {"client_id": self.dependent_client.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form_client"], self.dependent_client)
        answer = FormAnswer.objects.get(
            trip=self.trip,
            client=self.dependent_client,
            question=question,
        )
        self.assertEqual(answer.answer_text, "Cliente")

    def test_client_save_answer_persists_for_selected_dependent(self):
        question = FormQuestion.objects.create(
            form=self.visa_form,
            stage=self.stage,
            question="Observação do dependente",
            field_type="text",
            is_required=False,
            order=3,
            is_active=True,
        )

        response = self.client.post(
            reverse("system:client_save_answer", args=[self.trip.pk]),
            {
                "client_id": self.dependent_client.pk,
                "stage_token": f"stage:{self.stage.pk}",
                f"question_{question.pk}": "Resposta do dependente",
                "next_action": "save",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            FormAnswer.objects.filter(
                trip=self.trip,
                client=self.dependent_client,
                question=question,
                answer_text="Resposta do dependente",
            ).exists()
        )

    def test_client_view_form_renders_wizard_stepper_links_and_hides_breadcrumb(self):
        response = self.client.get(
            reverse("system:client_view_form", args=[self.trip.pk]),
            {"client_id": self.primary_client.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="client-form-wizard"')
        self.assertContains(response, 'class="etapas-navegacao"')
        self.assertContains(
            response,
            f'?client_id={self.primary_client.pk}&stage=stage%3A{self.stage.pk}',
        )
        self.assertContains(
            response,
            f'?client_id={self.primary_client.pk}&stage=stage%3A{self.stage_two.pk}',
        )
        self.assertNotContains(response, " › ")
