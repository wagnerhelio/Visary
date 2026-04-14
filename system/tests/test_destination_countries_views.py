from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from system.models import ConsultancyUser, DestinationCountry, Profile

User = get_user_model()


class DestinationCountriesViewsTests(TestCase):
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
            email="raquel.paises@visary.test",
            profile=self.profile,
            password="!",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username=self.consultant.email,
            email=self.consultant.email,
            password="senha-segura-123",
            is_staff=True,
        )
        self.canada = DestinationCountry.objects.create(
            name="Canada",
            iso_code="CAN",
            is_active=True,
            created_by=self.user,
        )
        self.australia = DestinationCountry.objects.create(
            name="Australia",
            iso_code="AUS",
            is_active=True,
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def test_home_destination_countries_renders_registered_countries(self):
        response = self.client.get(reverse("system:home_destination_countries"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Países mais recentes")
        self.assertContains(response, "Australia")
        self.assertContains(response, "Canada")

    def test_list_destination_countries_renders_registered_countries(self):
        response = self.client.get(reverse("system:list_destination_countries"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<td>Australia</td>")
        self.assertContains(response, "<td>Canada</td>")

    def test_home_destination_countries_filters_by_template_iso_parameter(self):
        response = self.client.get(
            reverse("system:home_destination_countries"),
            {"codigo_iso": "CAN"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Canada")
        self.assertNotContains(response, "Australia")
        self.assertEqual(response.context["applied_filters_dict"]["iso_code"], "CAN")

    def test_list_destination_countries_filters_by_legacy_iso_parameter(self):
        response = self.client.get(
            reverse("system:list_destination_countries"),
            {"iso_code": "CAN"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<td>Canada</td>")
        self.assertNotContains(response, "<td>Australia</td>")
