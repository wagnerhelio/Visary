from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from system.models import (
    ConsultancyClient,
    ConsultancyUser,
    DestinationCountry,
    FormAnswer,
    FormQuestion,
    Profile,
    Trip,
    TripClient,
    VisaForm,
    VisaFormStage,
    VisaType,
)

User = get_user_model()


class TripFormReplicationTests(TestCase):
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
            name="Consultor Replicação",
            email="consultor.replicacao@test.com",
            profile=self.profile,
            password="!",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username=self.consultant.email,
            email=self.consultant.email,
            password="SenhaForte123!",
        )
        self.country = DestinationCountry.objects.create(
            name="Estados Unidos",
            iso_code="USA",
            is_active=True,
            created_by=self.user,
        )
        self.visa_type = VisaType.objects.create(
            destination_country=self.country,
            name="B1 / B2 (Turismo, Negócios ou Estudos Recreativos)",
            description="",
            is_active=True,
            created_by=self.user,
        )
        self.form = VisaForm.objects.create(visa_type=self.visa_type, is_active=True)
        self.stage = VisaFormStage.objects.create(form=self.form, name="Dados da Viagem", order=2)
        self.question = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage,
            question="Objetivo detalhado da viagem",
            field_type="text",
            is_required=False,
            order=1,
            is_active=True,
        )

        self.primary_client = ConsultancyClient.objects.create(
            assigned_advisor=self.consultant,
            first_name="Cliente",
            last_name="Principal",
            cpf="100.200.300-40",
            birth_date=date(1990, 1, 1),
            nationality="Brasileira",
            phone="(11) 90000-0001",
            email="principal@test.com",
            password="!",
            created_by=self.user,
        )
        self.dependent_client = ConsultancyClient.objects.create(
            assigned_advisor=self.consultant,
            first_name="Cliente",
            last_name="Dependente",
            cpf="100.200.300-41",
            birth_date=date(1995, 1, 1),
            nationality="Brasileira",
            phone="(11) 90000-0002",
            email="dependente@test.com",
            password="!",
            created_by=self.user,
            primary_client=self.primary_client,
        )
        self.trip = Trip.objects.create(
            assigned_advisor=self.consultant,
            destination_country=self.country,
            visa_type=self.visa_type,
            planned_departure_date=date(2026, 10, 10),
            planned_return_date=date(2026, 10, 20),
            advisory_fee=1000,
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

        FormAnswer.objects.create(
            trip=self.trip,
            client=self.primary_client,
            question=self.question,
            answer_text="Dados da viagem do cliente principal",
        )

        self.client.force_login(self.user)

    def test_replicate_primary_answers_to_dependent(self):
        response = self.client.post(
            reverse("system:edit_client_form", args=[self.trip.pk, self.dependent_client.pk]),
            {
                "action": "replicate_primary",
                "stage_token": f"stage:{self.stage.pk}",
            },
        )

        self.assertEqual(response.status_code, 302)
        dependent_answer = FormAnswer.objects.get(
            trip=self.trip,
            client=self.dependent_client,
            question=self.question,
        )
        self.assertEqual(dependent_answer.answer_text, "Dados da viagem do cliente principal")
