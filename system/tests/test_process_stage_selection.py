from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from system.models import (
    ConsultancyClient,
    ConsultancyUser,
    DestinationCountry,
    Process,
    ProcessStage,
    ProcessStatus,
    Profile,
    Trip,
    TripClient,
    TripProcessStatus,
    VisaType,
)

User = get_user_model()


class CreateProcessStageSelectionTests(TestCase):
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
            email="raquel.processos@visary.test",
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
            name="Canada",
            iso_code="CAN",
            is_active=True,
            created_by=self.user,
        )
        self.visa_type = VisaType.objects.create(
            destination_country=self.country,
            name="Turismo",
            description="",
            is_active=True,
            created_by=self.user,
        )
        self.client_obj = ConsultancyClient.objects.create(
            assigned_advisor=self.consultant,
            first_name="Cliente",
            last_name="Unico",
            cpf="333.333.333-33",
            birth_date=date(1990, 1, 1),
            nationality="Brasileira",
            phone="(11) 99999-9999",
            email="cliente.processo@example.test",
            password="!",
            created_by=self.user,
        )
        self.trip = Trip.objects.create(
            assigned_advisor=self.consultant,
            destination_country=self.country,
            visa_type=self.visa_type,
            planned_departure_date=date(2026, 8, 1),
            planned_return_date=date(2026, 8, 20),
            advisory_fee=500,
            created_by=self.user,
        )
        TripClient.objects.create(
            trip=self.trip,
            client=self.client_obj,
            visa_type=self.visa_type,
            role="primary",
        )
        self.status_triagem = ProcessStatus.objects.create(
            visa_type=self.visa_type,
            name="Triagem",
            default_deadline_days=2,
            order=1,
            is_active=True,
        )
        self.status_documentos = ProcessStatus.objects.create(
            visa_type=self.visa_type,
            name="Documentos",
            default_deadline_days=5,
            order=2,
            is_active=True,
        )
        self.client.force_login(self.user)

    def _create_process_url(self):
        return (
            reverse("system:create_process")
            + f"?client_id={self.client_obj.pk}&trip_id={self.trip.pk}"
        )

    def _post_process(self, selected_stages=None):
        data = {
            "trip_hidden": self.trip.pk,
            "client": self.client_obj.pk,
            "notes": "",
            "assigned_advisor": self.consultant.pk,
        }
        if selected_stages is not None:
            data["selected_stages"] = [str(stage.pk) for stage in selected_stages]
        return self.client.post(self._create_process_url(), data)

    def test_create_process_renders_stage_checkboxes_from_trip_visa_type(self):
        response = self.client.get(self._create_process_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_selected_stages_0"')
        self.assertContains(response, 'id="id_selected_stages_1"')
        self.assertContains(response, "Triagem")
        self.assertContains(response, "Documentos")

    def test_create_process_with_only_trip_id_prefills_primary_client(self):
        response = self.client.get(
            reverse("system:create_process"),
            {"trip_id": self.trip.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["preselected_client"])
        self.assertContains(response, 'id="id_client"')
        self.assertNotContains(response, 'id="busca-cliente-input"')

    def test_api_process_status_returns_visa_type_stages_when_trip_has_no_specific_statuses(self):
        response = self.client.get(
            reverse("system:api_process_status"),
            {"trip_id": self.trip.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["name"] for item in response.json()],
            ["Triagem", "Documentos"],
        )

    def test_create_process_with_partial_stage_selection_creates_only_selected_stage(self):
        response = self._post_process(selected_stages=[self.status_documentos])

        self.assertEqual(response.status_code, 302)
        process = Process.objects.get(trip=self.trip, client=self.client_obj)
        self.assertEqual(
            list(process.stages.values_list("status__name", flat=True)),
            ["Documentos"],
        )

    def test_create_process_without_explicit_stage_selection_creates_all_available_stages(self):
        response = self._post_process(selected_stages=None)

        self.assertEqual(response.status_code, 302)
        process = Process.objects.get(trip=self.trip, client=self.client_obj)
        self.assertEqual(
            list(process.stages.values_list("status__name", flat=True)),
            ["Triagem", "Documentos"],
        )

    def test_trip_specific_statuses_take_precedence_over_visa_type_fallback(self):
        TripProcessStatus.objects.filter(
            trip=self.trip,
            status=self.status_triagem,
        ).update(is_active=False)

        response = self.client.get(
            reverse("system:api_process_status"),
            {"trip_id": self.trip.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in response.json()], ["Documentos"])
