from datetime import date
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from system.models import (
    ConsultancyClient,
    ConsultancyUser,
    DestinationCountry,
    Profile,
    TripClient,
    VisaType,
)

User = get_user_model()


class CreateTripViewTests(TestCase):
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
            email="raquel.test@visary.test",
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
            cpf="111.111.111-11",
            birth_date=date(1990, 1, 1),
            nationality="Brasileira",
            phone="(11) 99999-9999",
            email="cliente.unico@example.test",
            password="!",
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def test_api_visa_types_accepts_pais_alias(self):
        response = self.client.get(
            reverse("system:api_visa_types"),
            {"pais": self.country.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"id": self.visa_type.pk, "name": "Turismo"}])

    def test_api_visa_types_accepts_pais_id_alias(self):
        response = self.client.get(
            reverse("system:api_visa_types"),
            {"pais_id": self.country.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"id": self.visa_type.pk, "name": "Turismo"}])

    def test_create_trip_accepts_clientes_alias_for_preselected_primary_client(self):
        response = self.client.get(
            reverse("system:create_trip"),
            {"clientes": str(self.client_obj.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["preselected_clients"], [self.client_obj.pk])
        self.assertEqual(response.context["trip_members"][0]["client"], self.client_obj)
        self.assertEqual(response.context["trip_members"][0]["role"], "primary")

    def test_create_trip_with_single_client_saves_client_as_primary(self):
        response = self.client.post(
            reverse("system:create_trip"),
            {
                "assigned_advisor": self.consultant.pk,
                "advisory_fee": "500.00",
                "clients": [self.client_obj.pk],
                "destination_country": self.country.pk,
                "visa_type": self.visa_type.pk,
                "planned_departure_date": "2026-06-01",
                "planned_return_date": "2026-06-20",
                "notes": "",
                "action": "save",
            },
        )

        self.assertEqual(response.status_code, 302)
        trip_client = TripClient.objects.get(client=self.client_obj)
        self.assertEqual(trip_client.role, "primary")
        self.assertIsNone(trip_client.trip_primary_client)
        self.assertEqual(trip_client.visa_type, self.visa_type)

    def test_save_and_create_process_redirects_with_primary_client_and_trip(self):
        dependent = ConsultancyClient.objects.create(
            assigned_advisor=self.consultant,
            first_name="Dependente",
            last_name="Cliente",
            cpf="222.222.222-22",
            birth_date=date(1992, 2, 2),
            nationality="Brasileira",
            phone="(11) 98888-7777",
            email="dependente.cliente@example.test",
            password="!",
            created_by=self.user,
            primary_client=self.client_obj,
        )

        response = self.client.post(
            reverse("system:create_trip"),
            {
                "assigned_advisor": self.consultant.pk,
                "advisory_fee": "500.00",
                "clients": [self.client_obj.pk, dependent.pk],
                "destination_country": self.country.pk,
                "visa_type": self.visa_type.pk,
                "planned_departure_date": "2026-06-01",
                "planned_return_date": "2026-06-20",
                "notes": "",
                "action": "save_and_create_process",
            },
        )

        self.assertEqual(response.status_code, 302)
        parsed = urlparse(response.url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.path, reverse("system:create_process"))
        self.assertEqual(query.get("trip_id"), [str(TripClient.objects.get(client=self.client_obj).trip_id)])
        self.assertEqual(query.get("client_id"), [str(self.client_obj.pk)])
